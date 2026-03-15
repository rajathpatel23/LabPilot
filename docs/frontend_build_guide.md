# Frontend Build Guide (API-Driven)

This document defines what the frontend should build and how it should connect to backend APIs.

## 1) Backend base setup

- API base URL (local): `http://localhost:8000`
- Health check: `GET /health`
- Start backend:

```bash
cd /Users/rajatpatel/research/nebius_ai_hack/LabPilot
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

## 2) Product navigation (screens)

Use this navigation order for the MVP:

1. **Home / Workspace**
   - show quick links to conversations, training, experiments, evaluations

2. **Conversations (Threaded Copilot)**
   - list saved threads
   - open thread and continue chat
   - run next-action recommendation in thread context

3. **Model Training**
   - submit training job form
   - show training runs table
   - open run details with metrics

4. **Experiment Simulation**
   - run strategy simulation (random / greedy / adaptive / contextual_linucb)
   - show run result summary
   - open run detail and timeline

5. **Artifacts / Output Explorer**
   - browse saved recommendation payloads, reasoning outputs, benchmark JSONs

## 3) Core user stories to support

### A) Train model and inspect quality
- user submits dataset + target + features
- app shows MAE, R2, train/test sizes

### B) Ask for next best action in a thread
- user asks in chat
- backend runs agent flow
- app shows:
  - top recommendation
  - reasoning text
  - trace/tool steps
  - fallback option

### C) Run simulation and compare policies
- user launches run
- app displays:
  - best yield
  - steps completed
  - strategy

### D) Inspect what was saved
- app can reopen conversation, training runs, and experiment runs later

### E) Minimal evaluation snapshot (not a full page)
- show only a compact summary card inside Home or Experiment page:
  - best strategy by threshold hit rate
  - best strategy by mean best yield
  - latest benchmark artifact path

## 4) API contracts to integrate

## Dataset upload

### Upload dataset file
`POST /api/datasets/upload` (multipart form-data)

Form field:
- `file`: CSV/XLSX file

Response:
```json
{
  "filename": "my_experiments.csv",
  "stored_path": "data/uploads/<generated_name>.csv",
  "size_bytes": 12345
}
```

### List uploaded datasets
`GET /api/datasets`

## Conversations

### Create conversation
`POST /api/conversations`

Request:
```json
{ "title": "Suzuki optimization thread" }
```

### List conversations
`GET /api/conversations`

### Get conversation with messages
`GET /api/conversations/{conversation_id}`

### Post message and trigger agent run
`POST /api/conversations/{conversation_id}/messages`

Request:
```json
{
  "content": "Recommend top-5 next experiments for current campaign.",
  "data_path": "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx",
  "model_path": "artifacts/surrogate_suzuki.joblib",
  "top_k": 5,
  "use_llm": true,
  "use_tavily": true
}
```

Response includes assistant message + metadata:
- recommendation payload
- reasoning payload
- agent trace

## Training

### Create training run
`POST /api/training/runs`

Request:
```json
{
  "dataset_path": "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx",
  "target_column": "Product_Yield_PCT_Area_UV",
  "features": [
    "Reactant_1_Short_Hand",
    "Reactant_1_eq",
    "Reactant_1_mmol",
    "Reactant_2_Name",
    "Reactant_2_eq",
    "Catalyst_1_Short_Hand",
    "Catalyst_1_eq",
    "Ligand_Short_Hand",
    "Ligand_eq",
    "Reagent_1_Short_Hand",
    "Reagent_1_eq",
    "Solvent_1_Short_Hand"
  ],
  "output_name": "surrogate_suzuki"
}
```

### List training runs
`GET /api/training/runs`

### Get training run detail
`GET /api/training/runs/{run_id}`

## Experiment runs

### Create simulation run
`POST /api/experiments/runs`

Request:
```json
{
  "strategy": "contextual_linucb",
  "dataset_path": "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx",
  "model_path": "artifacts/surrogate_suzuki.joblib",
  "budget": 20,
  "n_init": 3,
  "seed": 42,
  "reward_mode": "improvement",
  "beta": 0.8,
  "linucb_alpha": 1.0,
  "linucb_lambda": 1.0
}
```

### List experiment runs
`GET /api/experiments/runs`

### Get experiment run detail
`GET /api/experiments/runs/{run_id}`

## Direct recommendation endpoint (non-chat)

### Get next recommendation with reasoning
`POST /api/recommendations/next`

Request:
```json
{
  "data_path": "data/uploads/<your_file>.csv",
  "model_path": "artifacts/<your_model>.joblib",
  "top_k": 5,
  "use_llm": true
}
```

## 5) UI components to build

### Conversation page
- left panel: thread list
- center: chat timeline
- right panel: metadata viewer (recommendation JSON / trace)

### Training page
- form: dataset, target, features
- table: runs, status, metrics
- details card: MAE / R2 / artifact paths

### Experiment page
- form: strategy + budget + seed
- table: runs
- detail graph:
  - best-so-far over steps
  - observed yield per step

### Minimal evaluation widget (recommended)
- no separate evaluation page required for MVP
- optional chart: one best-yield comparison image
- required text metrics:
  - threshold hit rate (latest holdout run)
  - best yield mean (latest holdout run)
  - quick interpretation sentence

## 6) What to visualize explicitly

For business understanding, always surface:

- **Best yield** by strategy
- **Threshold hit rate** by strategy
- **Average step-to-threshold**
- **Top-5 recommendation card**:
  - predicted yield
  - uncertainty
  - why now
  - backup option

## 7) Thread persistence behavior

- every user submit creates one `user` message
- backend run creates one `assistant` message with attached metadata
- threads are reopenable; context persists by `conversation_id`
- display `updated_at` and latest message preview in thread list

## 8) Suggested frontend tech shape

- Next.js + TypeScript
- React Query (or SWR) for API state
- lightweight charting (Recharts / Plotly)
- JSON viewer component for metadata panel

## 9) Acceptance criteria

Frontend is “ready” when:
- can create and continue threads
- can trigger and display recommendation + reasoning
- can start training and experiment runs
- can reopen saved runs and threads
- can show one compact evaluation snapshot (optional chart + 2 metrics)

