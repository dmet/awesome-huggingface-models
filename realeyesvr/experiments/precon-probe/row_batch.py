"""Deterministic row segmentation + batching for wide schedule tables.

Ported from realeyesvr/hf-spaces/realeyesvr-test-lab/row_segmentation.py.
That version gates on a row-count estimate supplied by a local PaddleOCR
reviewer -- precon-probe has no such reviewer (staying API-only, no GPU),
so this version relies only on the text-baseline / horizontal-rule
detection, which never needed the row count in the first place. Tables
where neither detector finds a confident structure return no crops; the
caller falls back to a single flat call in that case.
"""
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class RowCrop:
    row_index: int
    image: Image.Image


def segment_rows(image: Image.Image, *, header_fraction: float = 0.0,
                  footer_fraction: float = 0.0) -> list[RowCrop]:
    """Split a ruled or unruled schedule table image into per-row bands.

    header_fraction/footer_fraction trim a known header/footer strip before
    detection -- leave at 0 for an already-cropped table with no header row
    baked into the image.
    """
    bounds = _detect_text_row_bounds(image, header_fraction, footer_fraction)
    if not bounds:
        bounds = _detect_rule_bounds(image, header_fraction, footer_fraction)
    if not bounds:
        return []
    return _crops_from_bounds(image, _normalize_bounds(bounds))


def _normalize_bounds(bounds: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Split bands the detector merged by mistake back into even sub-bands.

    Real schedule rows vary in height (wrapped comment text breaks the
    uniform-spacing assumption the baseline detector relies on), so a band
    more than ~1.8x the median height is very likely several rows merged
    into one, not one genuinely tall row. Splitting it evenly won't always
    land on the true sub-boundaries, but it reliably keeps every batch small
    -- which is the property that actually matters for completion length,
    even when it costs some row-boundary precision.
    """
    heights = [bottom - top for top, bottom in bounds]
    if not heights:
        return bounds
    median = sorted(heights)[len(heights) // 2]
    if median <= 0:
        return bounds
    normalized: list[tuple[int, int]] = []
    for top, bottom in bounds:
        height = bottom - top
        pieces = max(1, round(height / median)) if height > median * 1.8 else 1
        if pieces == 1:
            normalized.append((top, bottom))
            continue
        step = height / pieces
        normalized.extend(
            (round(top + i * step), round(top + (i + 1) * step)) for i in range(pieces)
        )
    return normalized


def group_rows(rows: list[RowCrop], group_size: int = 4) -> list[list[RowCrop]]:
    """Combine adjacent rows so one model call reads a small, readable batch."""
    if group_size < 1:
        raise ValueError("group_size must be positive")
    return [rows[index: index + group_size] for index in range(0, len(rows), group_size)]


def stack_rows(rows: list[RowCrop]) -> Image.Image:
    """Stack equally wide row crops with thin separators for one model call."""
    if not rows:
        raise ValueError("At least one row crop is required")
    width = max(row.image.width for row in rows)
    separator = 6
    height = sum(row.image.height for row in rows) + separator * (len(rows) - 1)
    stacked = Image.new("RGB", (width, height), "white")
    y_offset = 0
    for row in rows:
        band = row.image.convert("RGB")
        stacked.paste(band, (0, y_offset))
        y_offset += band.height + separator
    return stacked


def _crops_from_bounds(image: Image.Image, bounds: list[tuple[int, int]]) -> list[RowCrop]:
    width, height = image.size
    crops: list[RowCrop] = []
    for index, (top_bound, bottom_bound) in enumerate(bounds):
        top = max(0, top_bound - 1)
        bottom = min(height, bottom_bound + 1)
        band = image.crop((0, top, width, bottom))
        target_height = max(160, band.height * 4)
        enlarged = band.resize((width * 2, target_height), Image.Resampling.LANCZOS)
        crops.append(RowCrop(index + 1, enlarged))
    return crops


def _detect_rule_bounds(image: Image.Image, header_fraction: float,
                         footer_fraction: float) -> list[tuple[int, int]]:
    grayscale = image.convert("L")
    width, height = grayscale.size
    line_rows = [
        y for y in range(height)
        if sum(grayscale.getpixel((x, y)) < 180 for x in range(width)) >= width * 0.8
    ]
    centers = _line_centers(line_rows)
    if len(centers) < 3:
        return []
    data_top = round(height * header_fraction) - 3
    data_bottom = round(height * (1 - footer_fraction))
    return [
        (upper, lower) for upper, lower in zip(centers, centers[1:])
        if upper >= data_top and lower <= data_bottom
    ]


def _detect_text_row_bounds(image: Image.Image, header_fraction: float,
                             footer_fraction: float) -> list[tuple[int, int]]:
    """Infer row bands from repeated horizontal text baselines in an unruled table."""
    grayscale = image.convert("L")
    width, height = grayscale.size
    data_top = round(height * header_fraction)
    data_bottom = round(height * (1 - footer_fraction))
    identifier_width = max(1, round(width * 0.2))
    threshold = max(20, round(identifier_width * 0.08))
    active = [
        y for y in range(data_top, data_bottom)
        if sum(grayscale.getpixel((x, y)) < 180 for x in range(identifier_width)) >= threshold
    ]
    groups: list[list[int]] = []
    for y in active:
        if not groups or y > groups[-1][-1] + 1:
            groups.append([y])
        else:
            groups[-1].append(y)
    centers = [round(sum(group) / len(group)) for group in groups if len(group) >= 2]
    if len(centers) < 2:
        return []
    bounds: list[tuple[int, int]] = []
    for index, center in enumerate(centers):
        top = data_top if index == 0 else round((centers[index - 1] + center) / 2)
        bottom = data_bottom if index == len(centers) - 1 else round((center + centers[index + 1]) / 2)
        bounds.append((top, bottom))
    return bounds


def _line_centers(rows: list[int]) -> list[int]:
    groups: list[list[int]] = []
    for row in rows:
        if not groups or row > groups[-1][-1] + 1:
            groups.append([row])
        else:
            groups[-1].append(row)
    return [round(sum(group) / len(group)) for group in groups]
