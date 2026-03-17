# LabPilot

LabPilot is an AI copilot for experiment optimization in R&D labs.  
It helps scientists decide the **next best experiment** by combining:

- a surrogate model trained on historical experiment data,
- adaptive decision policies (random/greedy/UCB/contextual LinUCB),
- literature evidence and explanation layers for trust and interpretability.

## Why this project exists

Lab optimization is expensive and slow when done by trial-and-error. Teams need to:

- reduce experiment cycles to reach target yield faster,
- justify why a recommendation is reasonable (not a black-box guess),
- keep a traceable thread of decisions and outcomes.

LabPilot is built as a decision-support loop, not a generic chatbot:

1. Ingest data
2. Train a surrogate model
3. Recommend next experiment
4. Submit observed result
5. Adapt model/session and continue

## What is in this repo

- `backend/` - FastAPI service, SQLite persistence, orchestration logic
- `modeling/` - shared modeling components and utilities
- `scripts/` - organized CLI entrypoints (`training/`, `workflows/`, `analysis/`, `benchmarks/`, `demos/`)
- `labpilot_frontend/` - React/Vite frontend (embedded in this repo)
- `docs/` - PRD, build guide, modeling quickstart, progress notes
- `prompts/` - LLM prompt templates for reasoning outputs

## Core capabilities

- Dataset upload (`.csv`, `.xlsx`, `.xls`)
- Surrogate model training (RandomForest-based)
- Next-experiment recommendation (top-k ranked candidates + uncertainty)
- Session loop with `submit-result` and follow-up recommendation
- Conversation threads with metadata-rich responses
- Literature search (Tavily) + literature relevance explanation
- Fair evaluation snapshot and comparison suite runs

## Tech stack and tools

### Backend and modeling
- Python, FastAPI, SQLAlchemy/SQLite
- pandas, scikit-learn, joblib, matplotlib
- RandomForest surrogate + uncertainty estimate
- UCB/adaptive/greedy/random/contextual LinUCB policies

### Agentic and reasoning tools
- Nebius Token Factory (LLM reasoning/classification)
- Tavily API (literature retrieval and citation snippets)

### Frontend
- React + Vite + TypeScript
- Wouter routing
- Recharts for evaluation visualizations

## High-level architecture

1. **Modeling layer** predicts yield and uncertainty from condition vectors.
2. **Policy layer** ranks candidate experiments (exploit vs explore tradeoff).
3. **Reasoning layer** explains recommendation intent and follow-up decision rule.
4. **Evidence layer** adds literature support when requested/triggered.
5. **App layer** stores sessions, runs, and threaded conversation history.

## End-to-end flow (product)

1. Upload dataset from UI (`Input` page quick-start or API)
2. Trigger training run
3. Create conversation + session linked to trained model
4. Ask chat for recommendation or literature review
5. Submit observed yield/conditions
6. Receive updated follow-up recommendation in the same thread

## API highlights

- `POST /api/datasets/upload`
- `POST /api/training/runs`
- `POST /api/conversations`
- `POST /api/conversations/{id}/messages`
- `POST /api/sessions`
- `POST /api/sessions/{id}/next`
- `POST /api/sessions/{id}/submit-result`
- `POST /api/recommendations/next`
- `POST /api/recommendations/next_with_evidence`
- `POST /api/literature/explain`
- `GET /api/evaluation/snapshot`
- `POST /api/evaluation/compare-suite`

## Local setup

### 1) Python backend

```bash
cd /Users/rajatpatel/research/nebius_ai_hack/LabPilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

Swagger: `http://127.0.0.1:8010/docs`

### 2) Frontend

```bash
cd /Users/rajatpatel/research/nebius_ai_hack/LabPilot/labpilot_frontend
npm install --legacy-peer-deps
npm run dev
```

## Environment variables

Create `LabPilot/.env` (not committed) for optional integrations:

- `NEBIUS_API_KEY`
- `NEBIUS_API_BASE` (optional override)
- `TAVILY_API_KEY`
- `INTENT_MODE` (`rules`, `llm`, `hybrid`)
- `TAVILY_AUTO_UNCERTAINTY_THRESHOLD`

## Evaluation philosophy

LabPilot emphasizes **fair, defensible claims**:

- holdout-first reporting for generalization,
- multi-run comparisons across strategies,
- random baseline included,
- clear methodology and artifact traceability in the UI.

## Documentation index

- [Docs home](docs/README.md)
- [Product requirements (PRD)](docs/prd.md)
- [Focus and build order](docs/focus.md)
- [Available tooling and role boundaries](docs/available_tooling.md)
- [Frontend build guide](docs/frontend_build_guide.md)
- [Modeling quickstart](docs/modeling_quickstart.md)
- [LLM reasoning approach](docs/llm_reasoning_approach.md)
- [Bandit policy approach](docs/bandit_policy_approach.md)
- [Dataset notes](docs/dataset.md)
- [Progress so far](docs/progress_so_far.md)
