# ⚖️ CodeJudge — LLM-as-a-Judge for Automated Code Auditing

CodeJudge audits Python code with a **panel of LLM judge agents** running fully
locally on your GPU (via [Ollama](https://ollama.com)). It combines classic static
analysis (Bandit + Pylint) with LLM reasoning: the static tools find candidate
problems fast, and the LLM judges decide which ones are real, find what the tools
miss, score the code against a rubric and propose a fixed version.

No code ever leaves your machine.

## Features

- **Multi-agent judge panel** – Security, Performance and Code Quality agents, each with its own rubric
- **Hybrid engine** – every Bandit/Pylint warning is verified by an LLM *Verification Judge* (real issue vs. false alarm)
- **Chief Judge** – executive verdict, top risks and a complete auto-fixed file
- **Rubric scorecard** – 1–10 per category, weighted overall score and letter grade
- **Auto-fix diff** – side-by-side view of the original vs. fixed code
- **Annotated code view** – problem lines highlighted by severity
- **Model manager** – pick a local model and load it into GPU memory with live progress and VRAM stats
- **Audit history & analytics** – stored in SQLite
- **PDF reports** – one-click export of any audit
- **100% local & reproducible** – temperature 0, fixed seed, strict JSON-schema outputs

## Architecture

```
            Python file
                │
                ▼
   ┌──────────────────────────┐
   │ Static analysis layer    │   Bandit (security, CWE) + Pylint (bugs)
   └────────────┬─────────────┘
                ▼
   ┌────────────┬──────────────┬──────────────┐
   │ Security   │ Performance  │ Code Quality │   specialist judge agents
   │ Agent      │ Agent        │ Agent        │   (rubric score + issues)
   └────────────┴──────┬───────┴──────────────┘
                       ▼
   ┌──────────────────────────┐
   │ Verification Judge       │   true / false positive for each static warning
   └────────────┬─────────────┘
                ▼
   ┌──────────────────────────┐
   │ Chief Judge              │   verdict, top risks, fixed code
   └────────────┬─────────────┘
                ▼
   Deterministic scoring: 0.5·Security + 0.25·Quality + 0.25·Performance
   (a critical vulnerability caps the grade at D)
```

All agents use the same local LLM. What makes them different agents is their
system prompt, their rubric and the JSON schema their verdict must follow
(see `core/agents.py`).

## Project structure

```
server.py              FastAPI app: model loading, audit stream, history, PDF
core/
  config.py            settings + model catalog
  ollama_client.py     Ollama HTTP API wrapper (structured JSON outputs)
  analyzers.py         Bandit + Pylint runner
  agents.py            judge prompts, rubrics and JSON schemas
  pipeline.py          the audit pipeline (streams progress events)
  storage.py           SQLite audit history
  report.py            PDF report generator
  gpu.py               GPU stats via nvidia-smi
static/                frontend (HTML + Tailwind + vanilla JS)
samples/               demo files: vulnerable, buggy, false-alarm bait, clean
```

## Setup

Requirements: Python 3.11+, [Ollama](https://ollama.com/download), optionally an NVIDIA GPU.

```bash
git clone https://github.com/barunaniket/codejudge.git
cd codejudge
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh
```

Open http://localhost:8000, choose a model (e.g. `qwen2.5-coder:7b`) and click
**Load into GPU**. The first load downloads the model (~4.7 GB).

## Demo walkthrough

1. **Models** – load `qwen2.5-coder:7b`; watch it stream into VRAM.
2. **Audit** – pick *Sql Injection Api* from the sample menu → **Run audit**.
   Watch the six pipeline stages complete live.
3. Review the grade, the Chief Judge verdict and the per-agent scorecards.
4. Open **Static verification** – each Bandit warning has a judge verdict.
5. Load *False Alarm Bait* – Bandit raises 5 warnings, the judge rejects all of them as false alarms.
6. Open **Auto-fix diff** → *Load fix into editor* → run again to verify the fix.
7. **History** – analytics across audits; download any report as PDF.

## Tech stack

FastAPI · Ollama · Qwen2.5-Coder · Bandit · Pylint · SQLite · fpdf2 · Tailwind CSS
