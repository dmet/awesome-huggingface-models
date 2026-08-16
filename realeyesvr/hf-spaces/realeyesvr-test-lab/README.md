---
title: RealEyesVR Test Lab
emoji: 🏗️
colorFrom: gray
colorTo: red
sdk: gradio
sdk_version: 5.49.1
python_version: 3.12
app_file: app.py
pinned: false
license: mit
hf_oauth: true
hf_oauth_expiration_minutes: 480
models:
- Qwen/Qwen3.5-9B
---

# RealEyesVR Test Lab

An early, source-linked construction schedule extraction experiment.

## Current mode — 0.7.3

The preload-guided release accepts one JPG or PNG door-schedule image. An
open-source PP-StructureV3 reviewer first identifies the table transcript,
observed columns, and estimated row count. Qwen then verifies that fallible
review against the source image and extracts source-aligned fields before the
result is validated against schema 1.1. When the reviewer estimates more than
one data row, the app detects horizontal rules, splits the schedule into row
bands, and asks Qwen to extract adjacent row batches of up to four records. The document review
runs on CPU before the GPU request, leaving ZeroGPU time for Qwen inference only.

The reviewer is advisory: Qwen is instructed to correct it when its transcript
or detected structure conflicts with the image. Review failures degrade to the
image-only Qwen path and are returned as extraction warnings.

PDF rendering, source-location evidence, deterministic business normalization,
and evaluation benchmarks are not included in this prototype. Every value must still be
verified against the source drawing.

## Privacy

Do not upload confidential, client, employer, personal, or otherwise restricted
documents. Use public, synthetic, personally owned, or explicitly authorized
test data only.

Uploads and results are not intentionally persisted by this application.
