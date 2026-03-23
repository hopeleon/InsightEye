# InsightEye

[中文版](./README.md)

**InsightEye** is an interview decision-support prototype designed for smart-glasses and recruiter-assist scenarios.  
It transforms raw interview transcripts into a compact decision interface: candidate style, risk signals, and the next best follow-up questions.

The current implementation focuses on a **text-first MVP**:

- Input: full interview transcript with speaker markers
- Processing: transcript parsing, atomic NLP feature extraction, DISC-oriented behavioral inference
- Output: decision-first interview dashboard for human interviewers

This repository is not a generic analytics demo. It is structured as an **interview assistance system** whose primary goal is to reduce reading cost and accelerate interviewer judgment.

---

## What It Does

Given a transcript such as:

```text
面试官：请你介绍一个推进难度比较高的项目。
候选人：……
面试官：你当时是怎么判断方向正确的？
候选人：……
```

InsightEye can:

- parse interviewer vs. candidate turns
- infer likely interview topic and rough job context
- extract atomic language indicators from the candidate response
- estimate DISC behavioral tendencies
- surface risk signals such as low-detail answers or impression-management patterns
- recommend follow-up questions for the interviewer
- present the result in a decision-oriented interface instead of a raw analysis dump

---

## Product Positioning

InsightEye is designed as an **interview decision support layer**, not a personality diagnosis engine.

The system is intentionally framed around:

- **behavioral tendencies**
- **communication style**
- **evidence quality**
- **interview guidance**

It should not be interpreted as:

- a clinical personality assessment
- a deterministic hiring filter
- an automated replacement for interviewer judgment

---

## Current Scope

### Supported today

- Text-based transcript input
- Local rule-based parsing and DISC scoring
- Optional dual-model pipeline
  - `gpt-5-mini` for transcript parsing
  - `gpt-5.4` for final DISC-style analysis
- Decision-first frontend dashboard
- Sample library for positive / neutral / negative / disguised cases

### Planned next

- richer sample evaluation workflow
- confidence calibration across more roles
- better authenticity detection for “polished but low-information” answers
- streaming / async UX for long-running LLM analysis
- audio and multimodal extensions for smart-glasses scenarios

---

## System Architecture

The current pipeline is intentionally simple and inspectable.

```text
Interview Transcript
        ↓
Speaker Parsing / Turn Mapping
        ↓
Atomic NLP Feature Extraction
        ↓
DISC Knowledge + Prompt-Oriented Analysis
        ↓
Decision Layer
  - candidate style
  - risk
  - recommended next move
        ↓
Detailed Layer
  - D / I / S / C evidence
  - NLP features
  - raw LLM output
```

### Analysis strategy

The repository supports two analysis modes:

1. **Local rule mode**
   - always available
   - parses transcript and generates DISC-oriented analysis from local rules

2. **LLM-enhanced mode**
   - enabled when `local_settings.py` contains a valid API key
   - uses:
     - `gpt-5-mini` to structure transcript turns
     - `gpt-5.4` to generate final higher-level inference

The frontend always prioritizes a **decision layer** over raw explanation.

---

## Repository Structure

```text
InsightEye/
├─ app/
│  ├─ analysis.py          # main orchestration pipeline
│  ├─ config.py            # runtime configuration loading
│  ├─ disc_engine.py       # local DISC scoring logic
│  ├─ features.py          # atomic NLP feature extraction
│  ├─ knowledge.py         # YAML / prompt loading
│  ├─ server.py            # lightweight local HTTP server
│  └─ transcript.py        # speaker parsing and turn mapping
├─ knowledge/
│  └─ DISC.yaml            # DISC knowledge base
├─ prompts/
│  └─ disc_system_prompt.txt
├─ samples/
│  ├─ index.json           # sample library manifest
│  └─ *.txt                # curated interview transcript samples
├─ static/
│  ├─ index.html           # frontend shell
│  ├─ app.js               # dashboard rendering logic
│  └─ styles.css           # decision-oriented UI styling
├─ local_settings.py.example
├─ run_demo.py
├─ README.md
└─ README_EN.md
```

---

## Frontend Design Principle

The frontend is intentionally organized into **three information layers**:

### 1. Decision layer

Visible first. Answers within seconds:

- What kind of candidate style is this?
- Is there a risk?
- What should I ask next?

### 2. Key metrics layer

Compressed evidence only:

- DISC ranking
- authenticity / risk level
- structure / expression capability

### 3. Detailed layer

Collapsed by default:

- dimension-by-dimension evidence
- NLP indicators
- model output

This keeps the interface aligned with interviewer workflow rather than analytics vanity.

---

## Knowledge Base

The DISC inference layer is grounded in:

- `knowledge/DISC.yaml`
- `prompts/disc_system_prompt.txt`

The YAML file defines:

- dimension motives
- lexical and discourse cues
- false positive sources
- differentiating rules
- probe question recommendations

The prompt defines:

- output schema
- anti-overclaim constraints
- interview-specific inference rules
- JSON-only response contract

---

## Sample Library

The project includes a curated sample set to test behavior across multiple regimes:

- strong positive cases
- neutral baseline cases
- weak / ordinary candidates
- hollow long-form answers
- polished but low-information “disguised” cases

Examples:

- `sales_tob_key_account`
- `backend_order_refactor`
- `operations_growth_content`
- `sales_hollow_long_negative`
- `engineering_shallow_negative`
- `project_polished_low_info`

To add a new sample:

1. create a new `.txt` file under `samples/`
2. add an entry to `samples/index.json`

Recommended fields:

- `id`
- `title`
- `job_hint`
- `filename`
- `description`

---

## Running Locally

### 1. Configure local settings

Create `local_settings.py` from the example:

```python
OPENAI_API_KEY = ""
OPENAI_BASE_URL = "https://api.zhizengzeng.com/v1"
OPENAI_PARSER_MODEL = "gpt-5-mini"
OPENAI_ANALYSIS_MODEL = "gpt-5.4"
```

If no API key is provided, the app will fall back to local rule-based analysis.

### 2. Start the demo

```powershell
python run_demo.py
```

Then open:

```text
http://127.0.0.1:8000
```

---

## How It Works in Practice

### Local mode

- transcript parsing from `app/transcript.py`
- atomic features from `app/features.py`
- DISC heuristic scoring from `app/disc_engine.py`

### LLM mode

- transcript -> `gpt-5-mini` parser
- structured interview representation + local features -> `gpt-5.4`
- frontend prefers LLM analysis when available

This separation is deliberate:

- fast structure extraction
- slower but stronger higher-level judgment
- stable local fallback

---

## Decision Philosophy

InsightEye is optimized around **interviewer decisions**, not raw model output.

The interface should help the interviewer decide:

1. continue or slow down?
2. trust the current signal or verify it?
3. push execution detail, motivation, structure, or authenticity?

That is why the product emphasizes:

- concise style summary
- risk surfacing
- follow-up generation

and de-emphasizes:

- decorative charts
- repetitive explanation
- heavy technical internals in the main view

---

## Limitations

Current limitations are intentional and should be understood clearly:

- DISC inference is probabilistic, not diagnostic
- long transcripts may still contain self-presentation bias
- local feature extraction is lightweight and heuristic
- LLM output quality depends on transcript quality and API stability
- job inference is approximate unless explicit hints are provided

This repo should be treated as a **high-potential prototype**, not a production-grade hiring engine.

---

## Security Notes

Do **not** commit:

- `local_settings.py`
- API keys
- internal proprietary interview data

The repository already includes a `.gitignore` for local secrets and runtime artifacts.

---

## Suggested Next Milestones

### Product

- add “interview continuation recommendation” as a first-class output
- add comparative candidate review mode
- add structured interviewer notes

### Modeling

- benchmark sample library against expected DISC distributions
- improve handling of hollow but fluent answers
- better distinction between high-C and shallow technical talk

### Engineering

- async job execution for long LLM runs
- persistent run history
- exportable interview reports
- modular multi-model provider support

---

## License / Usage

This repository is currently best treated as an internal prototype / private project unless a separate license is added.

If you plan to open-source it publicly, add:

- a license
- redacted sample data policy
- clearer disclaimer around hiring usage and personality inference

---

## Summary

InsightEye is an early but serious attempt at building an **AI-native interview assistance interface**:

- transcript in
- style / risk / follow-up out
- optimized for fast human judgment

Its core value is not “more analysis”.  
Its core value is **better interview decisions with less reading cost**.

