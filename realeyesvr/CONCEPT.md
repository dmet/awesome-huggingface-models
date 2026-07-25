# RealEyesVR — Concept

## The short version

Construction drawings contain valuable project data, but most of it remains trapped in PDF tables. RealEyesVR explores how visual AI can read that information, ordinary software can check it, and a focused review process can turn it into trusted, queryable records.

## The problem

Door schedules, equipment schedules, finish schedules, panelboards, and hardware groups are used throughout a project. Teams repeatedly search, read, copy, and rebuild this information in spreadsheets and models. That takes time, introduces transcription errors, and disconnects each copied value from the drawing that established it.

## The proposed workflow

1. Record the drawing package, sheet, title, revision, and page.
2. Use Qwen 3.5 as the first visual gate to find and read useful schedules.
3. Convert the candidate output into a consistent construction-data schema.
4. Apply deterministic checks for data types, units, allowed values, duplicates, missing references, and impossible combinations.
5. Send uncertain records through a targeted second-model or human review.
6. Store verified records in a data twin while retaining their source sheet and location.

## The intended result

The data twin is a structured layer alongside the drawings and BIM model. It can support questions such as:

- How many hollow-metal doors use a given hardware group?
- What changed between drawing revisions?
- Which equipment records are missing electrical requirements?
- Where do schedules and BIM records disagree?

## Current status

This is an independent research project, not a finished commercial product. Recent testing indicates that Qwen 3.5 can serve as the initial visual gate, followed by deterministic processing and targeted Claude review. Current work focuses on making those results measurable and repeatable across projects and schedule types.

## RealEyesVR Test Lab

The planned Test Lab is a small, working example hosted as a Hugging Face Gradio Space. Authenticated Hugging Face users will be able to upload one safe schedule image, run Qwen using shared ZeroGPU capacity, and inspect the structured result.

The first test case will focus only on door and frame schedules. It will show:

- Extracted schedule rows
- Schema-validation warnings
- Source evidence
- Raw and downloadable JSON
- Model, prompt, and schema versions
- Processing time
- A simple usefulness and correction feedback step

The Test Lab will not be presented as a production service. It is intended to test whether the extraction and validation concepts remain useful with different users, drawings, queues, and document conditions.

Uploads will be processed on Hugging Face infrastructure. Visitors will be instructed to use only public, synthetic, personally owned, or otherwise authorized documents. Confidential employer or client drawings will not be appropriate test inputs.

## Principles

- Benchmark each pipeline stage separately.
- Preserve source evidence for every value.
- Do not infer data that is not clearly present.
- Use AI for visual judgment and code for deterministic checks.
- Escalate uncertainty instead of hiding it.
- Treat the schema and verified evaluation set as longer-lived assets than any individual model.
