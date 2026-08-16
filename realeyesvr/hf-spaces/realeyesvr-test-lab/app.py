import os
import time
import traceback

import gradio as gr
from mock_data import build_mock_extraction
from pydantic import ValidationError
from schema import DoorScheduleExtraction

IS_HUGGING_FACE_SPACE = bool(os.getenv("SPACE_ID"))
APP_VERSION = "0.7.3"

if IS_HUGGING_FACE_SPACE:
    import spaces
    from qwen_extraction import QwenDoorScheduleExtractor
    from schema_review import (
        PaddleScheduleReviewer,
        ScheduleReview,
        review_from_payload,
        review_to_payload,
    )

    EXTRACTOR = QwenDoorScheduleExtractor()
    REVIEWER = PaddleScheduleReviewer()

    @spaces.GPU(duration=180)
    def run_qwen_extraction(document_path: str, review_payload: dict[str, object]):
        """Request a ZeroGPU allocation only for Qwen generation work."""
        try:
            review = review_from_payload(review_payload)
            return {"ok": True, "result": EXTRACTOR.extract(document_path, review).model_dump()}
        except Exception as error:
            traceback.print_exc()
            return {
                "ok": False,
                "error_type": type(error).__name__,
                "error": str(error),
                "detail": repr(error),
            }


CSS = """
.gradio-container { max-width: 1180px !important; }
.lab-banner { border-left: 4px solid #ed6a35; padding: 12px 16px; background: #fff3ec; }
.privacy-note { border: 1px solid #d6d1c7; padding: 12px 16px; }
"""


def run_extraction(
    document_path: str | None,
    authorized_upload: bool,
    profile: gr.OAuthProfile | None,
):
    """Run Qwen in Spaces; retain a deterministic local-development fallback."""
    if IS_HUGGING_FACE_SPACE and profile is None:
        return (
            "### Sign in required\nUse the Hugging Face sign-in button before running a test.",
            None,
            None,
        )

    if not authorized_upload:
        return (
            "### Authorization required\nConfirm that the test document is safe and authorized for cloud processing.",
            None,
            None,
        )

    if document_path is None:
        return (
            "### Document required\nUpload one PDF, JPG, or PNG schedule document.",
            None,
            None,
        )

    extension = os.path.splitext(document_path)[1].lower()
    if extension not in {".jpg", ".jpeg", ".png"}:
        return (
            "### Unsupported file\nFor the first Qwen test, use a JPG, JPEG, or PNG schedule image.",
            None,
            None,
        )

    started = time.perf_counter()
    source_filename = os.path.basename(document_path)

    try:
        if IS_HUGGING_FACE_SPACE:
            try:
                review = REVIEWER.review(document_path)
            except Exception as error:
                review = ScheduleReview(
                    reviewer_id="PaddleOCR/PP-StructureV3 (fallback)",
                    observed_columns=(),
                    estimated_rows=None,
                    transcript="No preload transcript was available; inspect the image independently.",
                    warnings=(f"Preload review failed: {type(error).__name__}: {error}",),
                )
            qwen_response = run_qwen_extraction(document_path, review_to_payload(review))
            if not qwen_response["ok"]:
                raise ValueError(
                    f"Qwen {qwen_response['error_type']}: "
                    f"{qwen_response['error']} ({qwen_response['detail']})"
                )
            extraction = DoorScheduleExtraction.model_validate(qwen_response["result"])
        else:
            extraction = build_mock_extraction(source_filename)
        result = extraction.model_dump(mode="json")
    except (ValidationError, ValueError) as error:
        return (
            "### Extraction could not be validated\n"
            "Qwen did not return a result that matches the door-schedule schema. "
            "Try a clearer schedule image or review the validation details.",
            None,
            {
                "valid": False,
                "error_type": type(error).__name__,
                "errors": str(error),
            },
        )

    elapsed = time.perf_counter() - started
    username = profile.username if profile is not None else "local tester"
    mode = "Qwen extraction" if IS_HUGGING_FACE_SPACE else "Local simulation"
    status = (
        f"### {mode} complete\n"
        f"Signed in as **{username}** · schema validation passed · {len(result['doors'])} rows · "
        f"{elapsed:.1f}s"
    )
    validation = {
        "valid": True,
        "schema_version": result["schema_version"],
        "warnings": [
            "Results require source-drawing verification.",
            "Do not use this result for construction decisions.",
        ],
    }
    return status, result, validation


with gr.Blocks(title="RealEyesVR Test Lab", css=CSS, theme=gr.themes.Base()) as demo:
    gr.Markdown(
        """
        # RealEyesVR Test Lab
        ### Construction drawings, made usable.

        <div class="lab-banner">
        <strong>Research prototype:</strong> Qwen reads one schedule image and the
        result is then checked against the door-schedule schema.
        </div>
        """
    )

    with gr.Row():
        if IS_HUGGING_FACE_SPACE:
            gr.LoginButton("Sign in with Hugging Face", logout_value="Sign out ({})")
        else:
            gr.Markdown("**Local development:** Hugging Face sign-in is bypassed.")
        gr.Markdown("**Test type:** Door and frame schedule · **Model:** Qwen 3.5 9B")
        gr.Markdown(f"**Test Lab version:** {APP_VERSION}")

    gr.Markdown(
        """
        <div class="privacy-note">
        <strong>Use safe documents only.</strong> Do not upload confidential,
        employer, client, personal, or restricted information. PDF and image files
        are processed on Hugging Face infrastructure.
        </div>
        """
    )

    with gr.Row():
        with gr.Column(scale=5):
            document = gr.File(
                type="filepath",
                file_types=[".jpg", ".jpeg", ".png"],
                file_count="single",
                label="One door-schedule image",
            )
            authorized = gr.Checkbox(
                label="I am authorized to use this document for cloud-based testing.",
                value=False,
            )
            run_button = gr.Button("Run Qwen extraction", variant="primary")

        with gr.Column(scale=7):
            status = gr.Markdown("Sign in, upload a safe image, and confirm authorization.")
            with gr.Tab("Structured result"):
                result = gr.JSON(label="Door schedule JSON")
            with gr.Tab("Validation"):
                validation = gr.JSON(label="Schema checks and warnings")

    run_button.click(
        fn=run_extraction,
        inputs=[document, authorized],
        outputs=[status, result, validation],
        api_name="run_extraction",
    )

    gr.Markdown(
        """
        ---
        **Research prototype:** Results require verification against the source drawing.
        This application does not provide professional construction advice.
        """
    )


if __name__ == "__main__":
    demo.launch()
