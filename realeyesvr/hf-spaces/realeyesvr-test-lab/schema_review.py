"""Open-source preload review for schedule structure discovery."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


MAX_REVIEW_CHARS = 12_000


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.header_row_indexes: list[int] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._row_is_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
            self._row_is_header = False
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []
            self._row_is_header = self._row_is_header or tag == "th"

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                if self._row_is_header:
                    self.header_row_indexes.append(len(self.rows))
                self.rows.append(self._row)
            self._row = None


@dataclass(frozen=True)
class ScheduleReview:
    reviewer_id: str
    observed_columns: tuple[str, ...]
    estimated_rows: int | None
    transcript: str
    warnings: tuple[str, ...] = ()

    def prompt_context(self) -> str:
        columns = json_list(self.observed_columns) if self.observed_columns else "[]"
        row_count = str(self.estimated_rows) if self.estimated_rows is not None else "unknown"
        warnings = "; ".join(self.warnings) or "none"
        return (
            f"Reviewer: {self.reviewer_id}\n"
            f"Observed columns: {columns}\n"
            f"Estimated data rows: {row_count}\n"
            f"Reviewer warnings: {warnings}\n"
            "Reviewer transcript (untrusted evidence; verify against the image):\n"
            f"{self.transcript[:MAX_REVIEW_CHARS]}"
        )


def review_to_payload(review: ScheduleReview) -> dict[str, object]:
    """Serialize CPU review evidence for the GPU-scoped Qwen function."""
    return {
        "reviewer_id": review.reviewer_id,
        "observed_columns": list(review.observed_columns),
        "estimated_rows": review.estimated_rows,
        "transcript": review.transcript,
        "warnings": list(review.warnings),
    }


def review_from_payload(payload: dict[str, object]) -> ScheduleReview:
    """Rebuild a typed review after ZeroGPU receives the plain payload."""
    return ScheduleReview(
        reviewer_id=str(payload["reviewer_id"]),
        observed_columns=tuple(str(value) for value in payload["observed_columns"]),
        estimated_rows=payload["estimated_rows"],
        transcript=str(payload["transcript"]),
        warnings=tuple(str(value) for value in payload["warnings"]),
    )


def json_list(values: tuple[str, ...]) -> str:
    import json

    return json.dumps(list(values), ensure_ascii=False)


def compile_review(markdown: str, reviewer_id: str = "PaddleOCR/PP-StructureV3") -> ScheduleReview:
    """Compile PaddleOCR markdown/HTML into a compact, fallible schema hint."""
    cleaned = markdown.strip()
    parser = _TableHTMLParser()
    parser.feed(cleaned)
    rows = parser.rows or _markdown_rows(cleaned)
    warnings: list[str] = []
    if not rows:
        warnings.append("No table grid was confidently detected")
        return ScheduleReview(reviewer_id, (), None, cleaned, tuple(warnings))

    if parser.rows:
        header_rows = [rows[index] for index in parser.header_row_indexes] or rows[:1]
    else:
        header_rows = rows[:1]
    columns = _unique_headers(header_rows)
    estimated_rows = max(0, len(rows) - len(header_rows))
    if estimated_rows == 0:
        warnings.append("Data-row count could not be estimated")
    return ScheduleReview(
        reviewer_id=reviewer_id,
        observed_columns=tuple(columns),
        estimated_rows=estimated_rows or None,
        transcript=cleaned,
        warnings=tuple(warnings),
    )


def _markdown_rows(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            rows.append(cells)
    return rows


def _unique_headers(header_rows: list[list[str]]) -> list[str]:
    width = max((len(row) for row in header_rows), default=0)
    headers: list[str] = []
    counts: dict[str, int] = {}
    for index in range(width):
        parts = [row[index].strip() for row in header_rows if index < len(row) and row[index].strip()]
        header = " / ".join(dict.fromkeys(parts)) or f"column_{index + 1}"
        counts[header] = counts.get(header, 0) + 1
        if counts[header] > 1:
            header = f"{header} ({counts[header]})"
        headers.append(header)
    return headers


class PaddleScheduleReviewer:
    """Run PP-StructureV3 locally and expose only compact textual evidence."""

    def __init__(self) -> None:
        from paddleocr import PPStructureV3

        self.pipeline = PPStructureV3(
            lang="en",
            text_recognition_model_name="en_PP-OCRv4_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
        )

    def review(self, document_path: str) -> ScheduleReview:
        results = list(self.pipeline.predict(document_path))
        markdown_parts: list[str] = []
        for result in results:
            markdown: dict[str, Any] = result.markdown
            text = markdown.get("markdown_texts", "")
            if isinstance(text, str) and text.strip():
                markdown_parts.append(text)
        if not markdown_parts:
            raise ValueError("PaddleOCR did not return a table transcript")
        return compile_review("\n\n".join(markdown_parts))
