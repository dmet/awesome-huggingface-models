from schema import DoorScheduleExtraction


def build_mock_extraction(source_filename: str) -> DoorScheduleExtraction:
    """Return deterministic sample data while the real Qwen backend is disabled."""
    return DoorScheduleExtraction.model_validate(
        {
            "record_type": "door_schedule",
            "schema_version": "1.0",
            "model_id": "simulation/no-model",
            "prompt_version": "door-schedule-v0.1-mock",
            "source_filename": source_filename,
            "extraction_confidence": "Medium",
            "doors": [
                {
                    "door_number": "101A",
                    "panel_count": 1,
                    "width_inches": 36,
                    "height_inches": 84,
                    "thickness_inches": 1.75,
                    "material": "HM",
                    "hardware_group": "HW-1",
                    "frame_type": "KD",
                    "fire_rating": "20 min",
                    "label_required": True,
                    "glazing": None,
                    "threshold": None,
                    "closer": None,
                    "remarks": "SIMULATED ROW — NOT READ FROM THE IMAGE",
                    "floor_level": "Level 1",
                },
                {
                    "door_number": "102",
                    "panel_count": 1,
                    "width_inches": 36,
                    "height_inches": 84,
                    "thickness_inches": 1.75,
                    "material": "WD",
                    "hardware_group": "HW-3",
                    "frame_type": "KD",
                    "fire_rating": None,
                    "label_required": False,
                    "glazing": None,
                    "threshold": None,
                    "closer": None,
                    "remarks": "SIMULATED ROW — NOT READ FROM THE IMAGE",
                    "floor_level": "Level 1",
                },
            ],
        }
    )
