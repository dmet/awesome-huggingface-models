"""Deterministic first-pass row segmentation for wide schedule images."""

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class ScheduleRowCrop:
    row_index: int
    image: Image.Image


def segment_schedule_rows(
    image: Image.Image,
    row_count: int | None,
    *,
    header_fraction: float = 0.115,
    footer_fraction: float = 0.055,
    minimum_rows: int = 2,
) -> list[ScheduleRowCrop]:
    """Split a ruled schedule into data-row bands.

    Horizontal rules are preferred when they can be detected from the image.
    The reviewer row count remains a fallback, not a source of geometry.
    """
    if row_count is None or row_count < minimum_rows:
        return []

    bounds = _detect_text_row_bounds(image)
    if not bounds:
        bounds = _detect_horizontal_rule_bounds(image, row_count)
    if bounds:
        return _crops_from_bounds(image, bounds)

    width, height = image.size
    data_top = round(height * header_fraction)
    data_bottom = round(height * (1 - footer_fraction))
    if data_bottom <= data_top or data_bottom - data_top < row_count:
        return []

    row_height = (data_bottom - data_top) / row_count
    return _crops_from_bounds(
        image,
        [(round(data_top + index * row_height), round(data_top + (index + 1) * row_height))
         for index in range(row_count)],
    )


def group_schedule_rows(rows: list[ScheduleRowCrop], group_size: int = 3) -> list[list[ScheduleRowCrop]]:
    """Combine adjacent rows so one Qwen call can extract a small, readable batch."""
    if group_size < 1:
        raise ValueError("group_size must be positive")
    return [rows[index : index + group_size] for index in range(0, len(rows), group_size)]


def stack_row_crops(rows: list[ScheduleRowCrop]) -> Image.Image:
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


def _crops_from_bounds(image: Image.Image, bounds: list[tuple[int, int]]) -> list[ScheduleRowCrop]:
    width, height = image.size
    crops: list[ScheduleRowCrop] = []
    for index, (top_bound, bottom_bound) in enumerate(bounds):
        top = max(0, top_bound - 1)
        bottom = min(height, bottom_bound + 1)
        band = image.crop((0, top, width, bottom))
        # Preserve the full record width, but give small schedule text enough
        # vertical pixels for the vision processor to retain it.
        target_height = max(160, band.height * 8)
        enlarged = band.resize((width * 2, target_height), Image.Resampling.LANCZOS)
        crops.append(ScheduleRowCrop(index + 1, enlarged))
    return crops


def _detect_horizontal_rule_bounds(image: Image.Image, expected_rows: int) -> list[tuple[int, int]]:
    grayscale = image.convert("L")
    width, height = grayscale.size
    # Full-width ruled lines are much denser than a row of small characters.
    line_rows = [
        y
        for y in range(height)
        if sum(grayscale.getpixel((x, y)) < 180 for x in range(width)) >= width * 0.8
    ]
    centers = _line_centers(line_rows)
    if len(centers) < 3:
        return []

    expected_height = height * (1 - 0.115 - 0.055) / expected_rows
    data_top = round(height * 0.115) - 3
    valid_gaps = [
        (upper, lower)
        for upper, lower in zip(centers, centers[1:])
        if upper >= data_top and expected_height * 0.55 <= lower - upper <= expected_height * 1.6
    ]
    if len(valid_gaps) < 2:
        return []
    return valid_gaps


def _detect_text_row_bounds(image: Image.Image) -> list[tuple[int, int]]:
    """Infer row bands from repeated horizontal text baselines in an unruled table."""
    grayscale = image.convert("L")
    width, height = grayscale.size
    data_top = round(height * 0.115)
    data_bottom = round(height * (1 - 0.055))
    # Use the left fifth of the schedule, where row identifiers live. This
    # avoids treating wrapped plan-note text at the right edge as extra rows.
    identifier_width = max(1, round(width * 0.2))
    threshold = max(20, round(identifier_width * 0.08))
    active = [
        y
        for y in range(data_top, data_bottom)
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
