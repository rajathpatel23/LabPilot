# LabPilot Progress So Far

## 1) Repository and project setup

- Created project folder: `LabPilot`
- Initialized Git repository and pushed to GitHub:
  - `https://github.com/rajathpatel23/LabPilot`
- Added baseline project structure:
  - `modeling/` package for modeling logic
  - root scripts for training, simulation, recommendation, comparison, and EDA
  - `docs/` folder for planning and execution docs

## 2) Documentation completed

Moved and organized documentation under `docs/`:

- `docs/prd.md`: full PRD and architecture
- `docs/focus.md`: execution order (modeling first)
- `docs/available_tooling.md`: sponsor tooling strategy
- `docs/dataset.md`: dataset options and download guidance
- `docs/modeling_quickstart.md`: runnable command flow
- `docs/llm_reasoning_approach.md`: current LLM status + integration plan
- `docs/README.md`: docs index

Added this file:
- `docs/progress_so_far.md`: consolidated status report

## 3) Python environment and packaging

Implemented dev environment and package metadata:

- Virtual env: `.venv/`
- Dependency files:
  - `requirements.txt`
  - `pyproject.toml`
- Package metadata:
  - project name `labpilot`
  - editable install supported
- Root docs + hygiene:
  - `README.md`
  - `.gitignore` (includes `.venv`, `artifacts`, caches)

Current install command used:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . --no-build-isolation
```

## 4) Core modeling components built

### 4.1 Data loading utility

- `modeling/io_utils.py`
  - unified loader for `.csv` and `.xlsx`

### 4.2 Surrogate model module

- `modeling/surrogate.py`
  - preprocessing pipeline:
    - numeric: median imputation
    - categorical: frequent imputation + one-hot encoding
  - regressor: `RandomForestRegressor`
  - train/eval helper with `MAE`, `R2`
  - uncertainty estimation using per-tree prediction spread

### 4.3 Bandit policy module

- `modeling/bandit_policy.py`
  - `UCB1Bandit` (explicit reward-driven, non-contextual)
  - `LinearUCBBandit` (contextual LinUCB)

## 5) Executable scripts implemented

- `train_surrogate.py`
  - trains model from CSV/XLSX
  - supports explicit feature list
  - saves model + metadata

- `explore_data.py`
  - fast EDA summary:
    - shape, dtypes, missingness
    - target distribution
    - numeric correlations
    - categorical target summaries
  - writes JSON output to `artifacts/`

- `recommend_next.py`
  - loads trained model
  - ranks candidates using UCB
  - returns top-k candidates with:
    - predicted yield
    - uncertainty
    - exploit score
    - explore bonus
    - UCB score
    - rationale stub

- `simulate_optimization.py`
  - runs sequential optimization with budget
  - strategies:
    - `random`
    - `adaptive` (surrogate UCB)
    - `bandit_ucb` (explicit reward UCB1)
    - `contextual_linucb` (contextual reward learning)
  - reward modes:
    - `yield`
    - `improvement`
  - saves full step-wise history to JSON

- `compare_trajectories.py`
  - compares random vs adaptive trajectories
  - exports side-by-side CSV
  - prints:
    - final best uplift
    - trajectory AUC uplift
    - time-to-threshold

## 6) Data status

### 6.1 Sample data (toy)

- `data/reactions_sample.csv`
- Used to validate scripts and end-to-end flow quickly

### 6.2 Real benchmark data (downloaded)

- `data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx`
- Successfully downloaded and explored

EDA artifact:
- `artifacts/eda_suzuki.json`

Key Suzuki dataset facts:
- rows: `5760`
- columns: `16`
- inferred target: `Product_Yield_PCT_Area_UV`
- missingness present in some ligand/reagent columns (handled via imputation)

## 7) Real-data training completed

Trained surrogate on Suzuki with curated features (avoiding obvious leakage fields such as `Reaction_No` and alternate target).

Saved:
- `artifacts/surrogate_suzuki.joblib`
- `artifacts/surrogate_suzuki_meta.json`

Metrics:
- `MAE`: `9.0399`
- `R2`: `0.7871`
- train size: `4608`
- test size: `1152`

## 8) Real-data recommendation completed

Ran top-k recommendation on Suzuki using trained surrogate.

Output:
- ranked candidate experiment conditions
- score decomposition (exploit + explore)
- rationale stubs

This confirms model-driven next-experiment recommendation is working on real benchmark data.

## 9) Real-data simulation and benchmark results

Ran 20-step simulations on Suzuki:

- `random`: best yield `91.6885`
- `adaptive` (surrogate-UCB): best yield `100.0`
- `contextual_linucb`: best yield `94.4707`

Adaptive vs random comparison output:
- final uplift: `+8.3115` yield points (`+9.06%`)
- trajectory AUC uplift: `+158.0224`
- threshold (95) reached:
  - adaptive: step `4`
  - random: not reached

Artifacts:
- `artifacts/sim_suzuki_random.json`
- `artifacts/sim_suzuki_adaptive.json`
- `artifacts/sim_suzuki_contextual_linucb.json`
- `artifacts/suzuki_trajectory_comparison.csv`

## 10) LLM/reasoning integration status

Current status:
- No live Nebius LLM API call is wired into runtime yet.
- Reasoning is currently represented by structured score fields and rationale stubs.

Planned role for LLM:
- post-ranking explanation layer
- convert numeric ranking signals into scientist-facing recommendation reasoning
- keep optimizer numeric; LLM explains decisions

Reference:
- `docs/llm_reasoning_approach.md`

## 11) What is working right now

- End-to-end modeling pipeline on real benchmark data
- Train + evaluate surrogate
- Generate top-k next experiments
- Run sequential optimization strategies
- Show adaptive improvement vs random with measurable metrics

## 12) Known limitations

- Current evaluation shown is single-seed in the latest real-data run.
- Need multi-seed benchmarking for stronger statistical claim.
- LLM reasoning layer not yet connected to Nebius endpoint.
- Guardrails/literature (Tavily) not yet integrated into recommendation runtime.

## 13) Recommended immediate next steps

1. Add multi-seed benchmark script for `random`, `adaptive`, `contextual_linucb`.
2. Report mean/std + win rate across seeds.
3. Add Nebius reasoning adapter:
   - input: top-k candidates + score breakdown + recent history
   - output: explanation + caution notes
4. Add lightweight Tavily guardrail checks for plausibility before final recommendation.
5. Expose this loop through FastAPI endpoints for demo UI integration.

## 14) Minimal command sequence (real data)

```bash
cd /Users/rajatpatel/research/nebius_ai_hack/LabPilot
source .venv/bin/activate

# EDA
python scripts/analysis/explore_data.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --out-json artifacts/eda_suzuki.json

# Train
python scripts/training/train_surrogate.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --target Product_Yield_PCT_Area_UV \
  --features Reactant_1_Short_Hand,Reactant_1_eq,Reactant_1_mmol,Reactant_2_Name,Reactant_2_eq,Catalyst_1_Short_Hand,Catalyst_1_eq,Ligand_Short_Hand,Ligand_eq,Reagent_1_Short_Hand,Reagent_1_eq,Solvent_1_Short_Hand \
  --out-model artifacts/surrogate_suzuki.joblib \
  --out-meta artifacts/surrogate_suzuki_meta.json

# Recommend
python scripts/workflows/recommend_next.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --model artifacts/surrogate_suzuki.joblib \
  --top-k 5

# Simulate and compare
python scripts/training/simulate_optimization.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --model artifacts/surrogate_suzuki.joblib \
  --strategy random \
  --budget 20 \
  --out artifacts/sim_suzuki_random.json

python scripts/training/simulate_optimization.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --model artifacts/surrogate_suzuki.joblib \
  --strategy adaptive \
  --budget 20 \
  --out artifacts/sim_suzuki_adaptive.json

python scripts/analysis/compare_trajectories.py \
  --random artifacts/sim_suzuki_random.json \
  --adaptive artifacts/sim_suzuki_adaptive.json \
  --out-csv artifacts/suzuki_trajectory_comparison.csv
```

