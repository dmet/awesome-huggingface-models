"""Qwen-backed door-schedule extraction for the Hugging Face Space runtime."""

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from row_segmentation import group_schedule_rows, segment_schedule_rows, stack_row_crops
from schema import DoorRecord, DoorScheduleExtraction
from schema_review import ScheduleReview

MODEL_ID = "Qwen/Qwen3.5-9B"
PROMPT_VERSION = "door-schedule-v0.7.3"

PROMPT = """You are extracting a construction door and frame schedule from one image.
An open-source document reviewer inspected the image first. Its report appears below.
Use that report as a fallible map of the table, not as ground truth. Verify every header,
row, and value against the image. Extract columns the reviewer missed when visible.
Read only values visibly supported by the schedule. Do not guess or fill in missing
values. Extract every visible schedule row. Return exactly one JSON object, with
no Markdown and no explanation.

The object must have this shape:
{
  "record_type": "door_schedule",
  "schema_version": "1.1",
  "model_id": "Qwen/Qwen3.5-9B",
  "prompt_version": "door-schedule-v0.7.3",
  "source_filename": "original filename",
  "extraction_confidence": "High, Medium, or Low",
  "extraction_warnings": ["text"],
  "doors": [
    {
      "door_number": "text",
      "door_type": "source text or null",
      "swing": "source text or null",
      "panel_count": "integer or null; only infer 2 when the source explicitly says Pair",
      "width_inches": "number or null",
      "height_inches": "number or null",
      "thickness_inches": "number or null",
      "material": "exact door material text or null",
      "finish": "exact door finish text or null",
      "hardware_group": "text or null",
      "frame_material": "exact frame material text or null",
      "frame_type": "text or null",
      "frame_trim": "text or null",
      "card_reader_required": "true, false, or null",
      "plan_notes": "text or null",
      "fire_rating": "20 min, 45 min, 60 min, 90 min, 3 hr, or null",
      "label_required": true,
      "glazing": "text or null",
      "threshold": "text or null",
      "closer": "text or null",
      "remarks": "text or null",
      "floor_level": "text or null"
    }
  ]
}

If no schedule can be read, return an empty doors array and Low confidence.
Use inches for normalized dimensions. Preserve source abbreviations such as SCWD.
Do not map Card Reader to label_required. Always include door_number. For every
other field, omit it when unknown or not visibly supported; do not use null as a
placeholder and do not invent a value.

PRELOAD REVIEW
{review_context}
"""

ROW_BATCH_INSTRUCTION = """The image contains exactly {batch_count} adjacent horizontal
schedule-row bands, in top-to-bottom order. They correspond to original source row-band
numbers: {source_row_bands}. Extract exactly one door record for every readable band, in
top-to-bottom order. Each record must include source_row_band set to its original source
row-band number. Do not combine rows and do not silently omit a band: if a band is
unreadable, return a minimal record with its source_row_band and a best-effort door_number.
Return an empty doors array only when none of the {batch_count} bands contain a door row."""


def build_row_batch_prompt(review_context: str, source_row_bands: list[int]) -> str:
    """Build a batch-specific instruction so Qwen knows the exact expected rows."""
    return PROMPT.replace(
        "Extract every visible schedule row.",
        ROW_BATCH_INSTRUCTION.format(
            batch_count=len(source_row_bands),
            source_row_bands=", ".join(str(index) for index in source_row_bands),
        ),
    ).replace("{review_context}", review_context)


def parse_json_object(response: str) -> dict[str, Any]:
    """Return the first JSON object in a model response.

    ``JSONDecoder.raw_decode`` is deliberately used instead of slicing from the
    first ``{`` to the last ``}``: models sometimes add a short explanation after
    a valid object, and that explanation can itself contain braces.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
    cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError(
        "Qwen did not return a JSON object "
        f"(generated {len(response.strip())} non-whitespace characters)."
    )


def normalize_extraction_result(result: dict[str, Any]) -> dict[str, Any]:
    """Wrap Qwen's occasional single door response in the schedule envelope."""
    if "doors" not in result and "door_number" in result:
        confidence = result.pop("extraction_confidence", "Low")
        return {"extraction_confidence": confidence, "doors": [result]}
    return result


class QwenDoorScheduleExtractor:
    """Load Qwen once at Space startup, then perform GPU-scoped extraction."""

    def __init__(self) -> None:
        import torch
        from transformers import AutoModelForMultimodalLM, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
        ).to("cuda")

    def extract(self, document_path: str, review: ScheduleReview) -> DoorScheduleExtraction:
        try:
            image = Image.open(document_path).convert("RGB")
        except (OSError, ValueError) as error:
            raise ValueError(f"Could not read the uploaded image: {error}") from error

        prompt = PROMPT.replace("{review_context}", review.prompt_context())
        row_crops = segment_schedule_rows(image, review.estimated_rows)

        if row_crops:
            doors: list[DoorRecord] = []
            row_warnings: list[str] = [
                f"Extracted {len(row_crops)} image-rule-guided row bands in batches of four."
            ]
            seen_door_numbers: set[str] = set()
            for batch_index, batch in enumerate(group_schedule_rows(row_crops, group_size=4), start=1):
                expected_bands = [row.row_index for row in batch]
                row_prompt = build_row_batch_prompt(review.prompt_context(), expected_bands)
                try:
                    row_result = self._generate_json(stack_row_crops(batch), row_prompt)
                    candidates = row_result.get("doors", [])
                    if len(candidates) != len(batch):
                        row_warnings.append(
                            f"Row batch {batch_index}: expected {len(batch)} records for source bands "
                            f"{expected_bands}, received {len(candidates)}."
                        )
                    returned_bands: set[int] = set()
                    for candidate_index, candidate in enumerate(candidates[: len(batch)], start=1):
                        try:
                            door = DoorRecord.model_validate(candidate)
                        except ValueError as error:
                            row_warnings.append(
                                f"Row batch {batch_index}, record {candidate_index}: schema validation failed: {error}."
                            )
                            continue
                        if door.source_row_band is None:
                            row_warnings.append(
                                f"Row batch {batch_index}, door {door.door_number!r}: missing source_row_band."
                            )
                        elif door.source_row_band not in expected_bands:
                            row_warnings.append(
                                f"Row batch {batch_index}, door {door.door_number!r}: source_row_band "
                                f"{door.source_row_band} is outside expected bands {expected_bands}."
                            )
                        else:
                            returned_bands.add(door.source_row_band)
                        if door.door_number in seen_door_numbers:
                            row_warnings.append(
                                f"Row batch {batch_index}: duplicate door number {door.door_number!r} skipped."
                            )
                            continue
                        seen_door_numbers.add(door.door_number)
                        doors.append(door)
                    missing_bands = [band for band in expected_bands if band not in returned_bands]
                    if missing_bands:
                        row_warnings.append(
                            f"Row batch {batch_index}: no validated record identified source bands {missing_bands}."
                        )
                except ValueError as error:
                    row_warnings.append(f"Row batch {batch_index}: {error}")
            result: dict[str, Any] = {
                "extraction_confidence": "Low",
                "doors": [door.model_dump(mode="json") for door in doors],
                "extraction_warnings": row_warnings,
            }
        else:
            result = self._generate_json(image, prompt)

        result["model_id"] = MODEL_ID
        result["prompt_version"] = PROMPT_VERSION
        result["source_filename"] = Path(document_path).name
        result["schema_version"] = "1.1"
        result["preload_reviewer"] = review.reviewer_id
        result["observed_columns"] = list(review.observed_columns)
        result["estimated_source_rows"] = review.estimated_rows
        result.setdefault("extraction_warnings", []).extend(review.warnings)
        try:
            return DoorScheduleExtraction.model_validate(result)
        except ValueError as error:
            raise ValueError(f"Qwen JSON failed schema validation: {error}") from error

    def _generate_json(self, image: Image.Image, prompt: str) -> dict[str, Any]:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        try:
            inputs = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                # Qwen3.5 thinks by default.  With a bounded generation budget,
                # its reasoning can consume the entire completion before it emits
                # the requested JSON.  The model's chat template renders an empty
                # think block for this setting, so decoding begins with the answer.
                enable_thinking=False,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self.model.device)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Could not prepare the image for Qwen: {error}") from error

        try:
            generated = self.model.generate(
                **inputs,
                max_new_tokens=700,
                do_sample=False,
            )
            completion = self.processor.decode(
                generated[0][inputs["input_ids"].shape[-1] :],
                skip_special_tokens=True,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise ValueError(f"Qwen generation failed: {error}") from error

        try:
            return normalize_extraction_result(parse_json_object(completion))
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Qwen response was not usable JSON: {error}") from error
