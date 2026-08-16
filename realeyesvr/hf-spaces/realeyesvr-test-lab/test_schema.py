from pydantic import ValidationError

from mock_data import build_mock_extraction
from qwen_extraction import build_row_batch_prompt, normalize_extraction_result, parse_json_object
from row_segmentation import ScheduleRowCrop, group_schedule_rows, segment_schedule_rows, stack_row_crops
from schema import DoorRecord
from schema_review import (
    MAX_REVIEW_CHARS,
    ScheduleReview,
    compile_review,
    review_from_payload,
    review_to_payload,
)


def test_mock_extraction_matches_schema():
    result = build_mock_extraction("sample.png")
    assert result.record_type == "door_schedule"
    assert result.source_filename == "sample.png"
    assert len(result.doors) == 2
    assert result.doors[0].door_number == "101A"
    assert result.schema_version == "1.1"
    assert result.preload_reviewer == "local/mock-reviewer"


def test_invalid_fire_rating_is_rejected():
    try:
        DoorRecord(
            door_number="101",
            panel_count=1,
            width_inches=36,
            height_inches=84,
            material="HM",
            fire_rating="30 min",
        )
    except ValidationError:
        return
    raise AssertionError("Invalid fire rating should fail validation")


def test_qwen_json_parser_ignores_braces_after_a_valid_object():
    response = '```json\n{"doors": []}\n```\nValidation note: {not JSON}'
    assert parse_json_object(response) == {"doors": []}


def test_qwen_json_parser_reports_empty_completion_size():
    try:
        parse_json_object("")
    except ValueError as error:
        assert "generated 0 non-whitespace characters" in str(error)
        return
    raise AssertionError("An empty Qwen completion must be rejected")


def test_single_qwen_door_is_wrapped_in_the_schedule_envelope():
    result = normalize_extraction_result({"door_number": "101", "material": "AL"})
    assert result == {
        "extraction_confidence": "Low",
        "doors": [{"door_number": "101", "material": "AL"}],
    }


def test_row_batch_prompt_declares_exact_source_bands():
    prompt = build_row_batch_prompt("review evidence", [9, 10, 11, 12])
    assert "exactly 4 adjacent" in prompt
    assert "9, 10, 11, 12" in prompt
    assert "source_row_band" in prompt


def test_source_row_band_is_optional_but_must_be_positive():
    assert DoorRecord(door_number="101", source_row_band=3).source_row_band == 3
    try:
        DoorRecord(door_number="101", source_row_band=0)
    except ValidationError:
        return
    raise AssertionError("source_row_band must be positive")


def test_schedule_rows_are_segmented_and_upscaled():
    from PIL import Image

    rows = segment_schedule_rows(Image.new("RGB", (100, 310)), 18)
    assert len(rows) == 18
    assert rows[0].row_index == 1
    assert rows[-1].row_index == 18
    assert rows[0].image.size == (200, 160)


def test_schedule_segmentation_requires_a_meaningful_row_count():
    from PIL import Image

    assert segment_schedule_rows(Image.new("RGB", (100, 100)), None) == []
    assert segment_schedule_rows(Image.new("RGB", (100, 100)), 1) == []


def test_row_crops_are_batched_and_stacked_in_source_order():
    from PIL import Image

    rows = [ScheduleRowCrop(index, Image.new("RGB", (20, 10))) for index in range(1, 5)]
    batches = group_schedule_rows(rows, group_size=3)
    assert [[row.row_index for row in batch] for batch in batches] == [[1, 2, 3], [4]]
    assert stack_row_crops(batches[0]).size == (20, 42)


def test_preload_review_compiles_observed_columns_and_row_count():
    review = compile_review(
        """
| Door Number | Door Material | Frame Material | Card Reader |
|---|---|---|---|
| 101 | AL | AL | Yes |
| 102 | SCWD | WI | No |
"""
    )
    assert review.observed_columns == (
        "Door Number",
        "Door Material",
        "Frame Material",
        "Card Reader",
    )
    assert review.estimated_rows == 2


def test_reviewer_context_is_bounded_and_declared_untrusted():
    review = ScheduleReview("reviewer", ("Door Number",), 18, "x" * (MAX_REVIEW_CHARS + 50))
    context = review.prompt_context()
    assert "untrusted evidence" in context
    assert len(context) < MAX_REVIEW_CHARS + 300


def test_review_payload_round_trip_preserves_cpu_review_evidence():
    review = ScheduleReview("reviewer", ("Door",), 2, "source text", ("warning",))
    assert review_from_payload(review_to_payload(review)) == review
