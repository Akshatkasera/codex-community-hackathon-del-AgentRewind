# AgentRewind

AgentRewind is a multi-agent debugger for failed LLM workflows. It loads a bad trace, asks OpenAI to identify the root-cause step, lets you rewrite that step, replays the downstream agents from the fork point, and then turns the fix into a reusable regression eval.

## Stack

- Backend: FastAPI + Pydantic + OpenAI Python SDK
- Frontend: Vite + React + TypeScript
- UI direction: minimalist dark cyberpunk terminal with scientific-instrument accents

## Project Layout

- `backend/` FastAPI API, demo traces, diagnosis/replay/eval engines
- `frontend/` React app with the three-panel debugger UI

## Setup

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

## Architecture

### Diagnosis engine

`backend/app/diagnosis_engine.py` sends the full trace to OpenAI with a structured JSON contract. The model returns the root-cause step, failure category, confidence score, and a concrete fix recommendation.

### Replay engine

`backend/app/replay_engine.py` rewrites the chosen step, then simulates each subsequent agent using the updated upstream context. It judges whether the new output is better than the original answer and reports the cost delta.

### Eval generator

`backend/app/eval_generator.py` converts the original failure and the successful fork into a regression-test spec with positive and negative assertions.

## Demo Traces

- `refund_policy_bug.json` stale policy retrieval
- `code_review_failure.json` hallucinated Redis API
- `research_contradiction.json` ignored contradiction between weak web evidence and stronger trial data

## Mock Mode

Set `AGENTREWIND_USE_MOCK_LLM=true` in `backend/.env` if you want to iterate on the UI without making OpenAI requests.
