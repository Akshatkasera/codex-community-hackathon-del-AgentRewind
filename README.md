# AgentRewind

AgentRewind is a multi-agent debugger for failed LLM workflows. It loads a bad trace, asks OpenAI to identify the root-cause step, lets you rewrite that step, replays the downstream agents from the fork point, and then turns the fix into a reusable regression eval.

It now includes nine deeper debugging capabilities:

- deterministic tool snapshots for replaying captured tool steps without resampling them
- contradiction detection across agent claims so consensus failures are explicit
- memory provenance links that show which earlier step introduced a fact carried into the final answer
- cross-trace failure clustering so recurring failure families are grouped together
- automatic repair suggestions that propose workflow, prompt, memory, or abstention fixes
- persistent memory corruption detection for bad facts that keep poisoning later steps
- uncertainty propagation so weak evidence does not silently become a confident answer
- versioned environment snapshots and replay audits so forked runs explain what was deterministic versus simulated
- automatic import adapters for LangGraph, CrewAI, AutoGen, OpenAI Agents, native AgentRewind traces, and generic JSON

## Stack

- Backend: FastAPI + Pydantic + OpenAI Python SDK
- Frontend: Vite + React + TypeScript
- UI direction: minimalist dark cyberpunk terminal with scientific-instrument accents

## Project Layout

- `backend/` FastAPI API, demo traces, diagnosis/replay/eval engines
- `frontend/` React app with the three-panel debugger UI

## Quick Start

Run AgentRewind from a single terminal:

```powershell
cd D:\AgentRewind
.\agentrewind.bat
```

The startup console will:

- print an `AGENTREWIND` banner
- ask for your OpenAI API key
- save that key into `backend/.env`
- install backend dependencies if the backend venv is missing or stale
- build the frontend when the UI sources changed
- start one FastAPI server that serves both the API and the web UI
- print the web link, usually `http://127.0.0.1:8000`

If port `8000` is busy, the launcher automatically picks the next free port.

You can also run the Python launcher directly:

```powershell
cd D:\AgentRewind
python start_agentrewind.py
```

Add `--open` if you want it to open the browser automatically after startup.

## Manual Setup

### Backend

```powershell
cd D:\AgentRewind\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload
```

The backend prefers `OPENAI_API_KEY` from `backend/.env`. If that is not set, it will try to extract a key from `C:\Users\aksha\Downloads\prompt.md`, which matches the file you provided. That fallback is convenient for the hackathon demo, but storing the key in `.env` is the safer long-term setup.

### Frontend

```powershell
cd D:\AgentRewind\frontend
npm install
npm run dev
```

The frontend expects the API at `http://localhost:8000`.

## Demo Flow

1. Open the app in the browser. The `Refund Policy Bug` trace loads by default.
2. Click the `KnowledgeRetriever` step in the left timeline.
3. The center panel shows the AI diagnosis for the failure and exposes the step input for editing.
4. Rewrite the failing retrieval prompt or tool instruction and click `Replay From This Point`.
5. AgentRewind simulates each downstream step, renders the forked branch in the timeline, and shows the new final answer against the original output.
6. Click `Generate Regression Eval` to convert the fix into JSON assertions you can reuse as a guardrail.

## Import Adapters

Use `Import External Trace` in the UI to paste or load a JSON export from:

- LangGraph
- CrewAI
- AutoGen
- OpenAI Agents
- AgentRewind native traces
- generic step/event/message JSON

The backend will auto-detect the framework when possible, normalize the export into the AgentRewind schema, store it under `backend/imported_traces`, and immediately make it available in the debugger timeline.

## Architecture

### Diagnosis engine

`backend/app/diagnosis_engine.py` sends the full trace to OpenAI with a structured JSON contract. The model returns the root-cause step, failure category, confidence score, and a concrete fix recommendation.

### Replay engine

`backend/app/replay_engine.py` rewrites the chosen step, then simulates each subsequent agent using the updated upstream context. If a downstream tool step has a captured snapshot, AgentRewind replays that step deterministically instead of resampling it. The replay report also includes remaining contradictions and provenance links for the forked branch.

### Eval generator

`backend/app/eval_generator.py` converts the original failure and the successful fork into a regression-test spec with positive and negative assertions.

### Trace analysis

`backend/app/analysis_engine.py` enriches every trace with:

- tool snapshots for deterministic replay
- contradiction findings between claims made by different agents
- provenance links showing how facts move from one step into later reasoning
- repair suggestions derived from the failure pattern
- persistent memory corruption issues
- per-step uncertainty signals and abstention recommendations
- versioned environment snapshots for replay accounting

### Cluster intelligence

`backend/app/cluster_engine.py` groups traces into recurring failure families. In the current demo set that means evidence-integrity failures are clustered separately from interface hallucinations, and the frontend surfaces those clusters so you can reason about repeated failure patterns instead of isolated incidents.

### Import adapters

`backend/app/import_adapters.py` detects common framework exports and converts them into `AgentTrace`. Each adapter preserves as much tool, memory, and version metadata as the source payload exposes, so the rest of the debugger can still run contradiction analysis, memory corruption detection, uncertainty scoring, clustering, and replay auditing on imported traces.

## Demo Traces

- `refund_policy_bug.json` stale policy retrieval
- `code_review_failure.json` hallucinated Redis API
- `research_contradiction.json` ignored contradiction between weak web evidence and stronger trial data

## Mock Mode

Set `AGENTREWIND_USE_MOCK_LLM=true` in `backend/.env` if you want to iterate on the UI without making OpenAI requests.
