from mock_data import build_mock_extraction
from pydantic import ValidationError
from schema import DoorRecord


def test_mock_extraction_matches_schema():
    result = build_mock_extraction("sample.png")
    assert result.record_type == "door_schedule"
    assert result.source_filename == "sample.png"
    assert len(result.doors) == 2
    assert result.doors[0].door_number == "101A"


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
