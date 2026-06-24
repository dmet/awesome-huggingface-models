import streamlit as st
from PIL import Image
import anthropic
import base64
import io
import os

st.set_page_config(
    page_title="Jobsite Photo Analyzer — RealEyesVR",
    page_icon="🏗️",
    layout="centered",
)

# ---- Styling ----
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #f4f6f8; }
  .block-container { max-width: 820px; padding-top: 2rem; }
  h1 { color: #0d1b2a; }
  .stButton > button {
    background: #f46b1e; color: white; border: none;
    font-weight: 700; border-radius: 8px; padding: 0.6rem 1.4rem;
  }
  .stButton > button:hover { background: #d95d10; }
  .result-box {
    background: white; border-radius: 10px; padding: 24px;
    border-left: 4px solid #f46b1e; margin-top: 16px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.07);
  }
  .tag-ahead  { color: #28a745; font-weight: 700; }
  .tag-behind { color: #dc3545; font-weight: 700; }
  .tag-on     { color: #f46b1e; font-weight: 700; }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 100px;
    font-size: 0.78rem; font-weight: 700; margin-bottom: 8px;
  }
  .badge-orange { background: #fff0e6; color: #f46b1e; border: 1px solid #f46b1e; }
</style>
""", unsafe_allow_html=True)

# ---- Header ----
st.markdown('<span class="badge badge-orange">Vision AI Demo</span>', unsafe_allow_html=True)
st.title("🏗️ Schedule vs. Jobsite Photo Analyzer")
st.markdown(
    "Upload a jobsite photo and describe what your schedule says should be done. "
    "The AI compares what it sees against your schedule and flags variances."
)
st.markdown("---")

# ---- Inputs ----
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("📷 Jobsite Photo")
    uploaded_file = st.file_uploader(
        "Upload a photo (JPG or PNG)",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
    )
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, use_container_width=True, caption="Uploaded photo")

with col2:
    st.subheader("📋 Schedule Notes")
    schedule_text = st.text_area(
        "Paste your schedule summary or key tasks for this area",
        height=180,
        placeholder=(
            "Example:\n"
            "Week 14 — Grid B3:\n"
            "- Concrete slab pour: COMPLETE\n"
            "- Formwork removal: IN PROGRESS\n"
            "- Steel erection at C1: NOT STARTED\n\n"
            "Week 14 — Site general:\n"
            "- Perimeter fencing: COMPLETE\n"
            "- Temporary power: COMPLETE"
        ),
        label_visibility="collapsed",
    )
    current_week = st.text_input(
        "Current project week / phase (optional)",
        placeholder="e.g. Week 14, Phase 2, Month 3",
    )

# ---- API Key ----
with st.expander("🔑 API Key (required)", expanded=not bool(os.environ.get("ANTHROPIC_API_KEY"))):
    st.markdown(
        "Get a free key at [console.anthropic.com](https://console.anthropic.com). "
        "Your key is used only for this request and is never stored."
    )
    user_api_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")

# ---- Analyze Button ----
st.markdown("---")
analyze = st.button("Analyze Photo Against Schedule", use_container_width=True)

if analyze:
    api_key = user_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    if not uploaded_file:
        st.error("Please upload a jobsite photo.")
        st.stop()
    if not schedule_text.strip():
        st.error("Please enter your schedule notes.")
        st.stop()
    if not api_key:
        st.error("Please enter your Anthropic API key.")
        st.stop()

    with st.spinner("Analyzing photo against schedule..."):
        # Encode image
        img_bytes = uploaded_file.getvalue()
        img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        media_type = "image/jpeg" if uploaded_file.name.lower().endswith((".jpg", ".jpeg")) else "image/png"

        week_context = f"Current project phase/week: {current_week}\n" if current_week else ""

        prompt = f"""You are a senior construction project manager reviewing a jobsite photo against the project schedule.

{week_context}SCHEDULE NOTES:
{schedule_text}

Analyze the uploaded jobsite photo carefully. Then provide a structured report with:

1. **WHAT I SEE** — Describe visible work-in-place: materials, structural elements, trades working, site conditions. Be specific about locations if identifiable.

2. **SCHEDULE COMPARISON** — For each scheduled item mentioned, assess:
   - Is it visible / confirmed in the photo?
   - Does it match the expected status (complete, in progress, not started)?
   - Any discrepancy between what the schedule says and what the photo shows?

3. **VARIANCES FLAGGED** — List any schedule vs. reality gaps with a severity (HIGH / MEDIUM / LOW).

4. **SUMMARY** — One paragraph: overall schedule health based on what you can observe, and recommended follow-up actions.

Be direct and use construction industry language. If the photo doesn't show enough detail to confirm a scheduled item, say so explicitly rather than guessing."""

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1200,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": img_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            result = response.content[0].text

            st.success("Analysis complete")
            st.markdown('<div class="result-box">', unsafe_allow_html=True)
            st.markdown(result)
            st.markdown('</div>', unsafe_allow_html=True)

            st.download_button(
                "⬇ Download Report",
                data=result,
                file_name="jobsite_analysis.md",
                mime="text/markdown",
            )

        except anthropic.AuthenticationError:
            st.error("Invalid API key. Please check and try again.")
        except Exception as e:
            st.error(f"Error: {e}")

# ---- Footer ----
st.markdown("---")
st.markdown(
    "<small>Powered by Claude Vision AI &nbsp;|&nbsp; "
    "[RealEyesVR](https://realeyesvr.com) &nbsp;|&nbsp; "
    "Your photo is not stored or used for training.</small>",
    unsafe_allow_html=True,
)
