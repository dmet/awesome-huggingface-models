import os
import time

import gradio as gr
from mock_data import build_mock_extraction
from pydantic import ValidationError

IS_HUGGING_FACE_SPACE = bool(os.getenv("SPACE_ID"))

if IS_HUGGING_FACE_SPACE:
    import spaces

    @spaces.GPU(duration=1)
    def zero_gpu_healthcheck() -> str:
        """Declare the GPU boundary required by ZeroGPU before Qwen is enabled."""
        return "ZeroGPU boundary is available."


CSS = """
.gradio-container { max-width: 1180px !important; }
.lab-banner { border-left: 4px solid #ed6a35; padding: 12px 16px; background: #fff3ec; }
.privacy-note { border: 1px solid #d6d1c7; padding: 12px 16px; }
"""


def run_mock_extraction(
    document_path: str | None,
    authorized_upload: bool,
    profile: gr.OAuthProfile | None,
):
    """Exercise the complete UI and validation path without allocating a GPU."""
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
    if extension not in {".pdf", ".jpg", ".jpeg", ".png"}:
        return (
            "### Unsupported file\nUse a PDF, JPG, JPEG, or PNG document.",
            None,
            None,
        )

    started = time.perf_counter()
    source_filename = os.path.basename(document_path)

    try:
        extraction = build_mock_extraction(source_filename)
        result = extraction.model_dump(mode="json")
    except ValidationError as error:
        return (
            "### Schema validation failed\nThe simulated result did not match the door-schedule schema.",
            None,
            {"errors": error.errors()},
        )

    elapsed = time.perf_counter() - started
    username = profile.username if profile is not None else "local tester"
    status = (
        "### Simulated extraction complete\n"
        f"Signed in as **{username}** · validation passed · {len(result['doors'])} sample rows · "
        f"{elapsed:.3f}s\n\n"
        "⚠️ **No AI inference occurred. These rows were not read from the uploaded image.**"
    )
    validation = {
        "valid": True,
        "schema_version": result["schema_version"],
        "warnings": [
            "Simulation mode is enabled.",
            "All returned door rows are fixtures for interface testing.",
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
        <strong>Interface test:</strong> This version validates the login, upload,
        schema, and result experience. Qwen inference is not enabled yet.
        </div>
        """
    )

    with gr.Row():
        if IS_HUGGING_FACE_SPACE:
            gr.LoginButton("Sign in with Hugging Face", logout_value="Sign out ({})")
        else:
            gr.Markdown("**Local development:** Hugging Face sign-in is bypassed.")
        gr.Markdown("**Test type:** Door and frame schedule · **Mode:** Simulated extraction")

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
                file_types=[".pdf", ".jpg", ".jpeg", ".png"],
                file_count="single",
                label="One door-schedule PDF or image",
            )
            authorized = gr.Checkbox(
                label="I am authorized to use this document for cloud-based testing.",
                value=False,
            )
            run_button = gr.Button("Run simulated extraction", variant="primary")

        with gr.Column(scale=7):
            status = gr.Markdown("Sign in, upload a safe image, and confirm authorization.")
            with gr.Tab("Structured result"):
                result = gr.JSON(label="Door schedule JSON")
            with gr.Tab("Validation"):
                validation = gr.JSON(label="Schema checks and warnings")

    run_button.click(
        fn=run_mock_extraction,
        inputs=[document, authorized],
        outputs=[status, result, validation],
        api_name="run_mock_extraction",
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
