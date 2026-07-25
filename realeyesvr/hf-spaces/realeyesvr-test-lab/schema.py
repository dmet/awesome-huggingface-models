from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Material = Literal["HM", "WD", "AL", "GL", "FRP", "Other"]
Confidence = Literal["High", "Medium", "Low"]


class DoorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    door_number: str = Field(min_length=1)
    panel_count: int = Field(ge=1)
    width_inches: float = Field(gt=0)
    height_inches: float = Field(gt=0)
    thickness_inches: float | None = Field(default=None, gt=0)
    material: Material
    hardware_group: str | None = None
    frame_type: str | None = None
    fire_rating: str | None = None
    label_required: bool | None = None
    glazing: str | None = None
    threshold: str | None = None
    closer: str | None = None
    remarks: str | None = None
    floor_level: str | None = None

    @field_validator("door_number")
    @classmethod
    def preserve_door_number_as_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("door_number cannot be blank")
        return cleaned

    @field_validator("fire_rating")
    @classmethod
    def validate_fire_rating(cls, value: str | None) -> str | None:
        allowed = {"20 min", "45 min", "60 min", "90 min", "3 hr"}
        if value is not None and value not in allowed:
            raise ValueError(f"fire_rating must be one of {sorted(allowed)}")
        return value


class DoorScheduleExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: Literal["door_schedule"] = "door_schedule"
    schema_version: Literal["1.0"] = "1.0"
    model_id: str
    prompt_version: str
    source_filename: str
    extraction_confidence: Confidence
    doors: list[DoorRecord]
