# Samples Library V2

This folder defines the next-generation interview sample system for InsightEye.
It is intentionally separated from the current demo-only `samples/*.txt` files.

## Goals

- Each case should contain at least 10 turns
- Each role should use a professional question outline
- Candidate quality must be separated into `strong / medium / weak / disguised`
- Each case must include expected DISC ranking, risk patterns, and follow-up directions
- Cases should be usable for evaluation, not just demo presentation

## Structure

```text
samples/library_v2/
- README.md
- manifest.json
- schema.json
- meta/
  - *.json
- transcripts/
  - *.txt
- templates/
  - case_meta.template.json
  - interview_outline.template.md
```

## File Pairing

Each case is composed of:

1. `transcripts/<case_id>.txt`
   Raw interviewer/candidate conversation for the runtime pipeline.

2. `meta/<case_id>.json`
   Structured labels for development and evaluation.

## Generation Rules

1. Generate the role-specific interview outline first.
2. Reuse the same outline across strong / medium / weak / disguised versions.
3. Do not use length as the only quality signal.
4. Every case must include expected findings and expected follow-up directions.

## Batch 1 Matrix

The first batch covers 16 baseline cases:

- ToB Sales
- Backend Engineering
- Product Manager
- Growth / Operations

Each role has 4 quality variants:

- `strong`
- `medium`
- `weak`
- `disguised`
