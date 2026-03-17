# LabPilot Modeling Quickstart

Run these commands from the repo root. They reference the reorganized `scripts/`
tree (`training/`, `workflows/`, `analysis/`, `benchmarks/`, `demos/`).

## 1) Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . --no-build-isolation
```

## 2) Train surrogate model

```bash
python scripts/training/train_surrogate.py \
  --data data/reactions.csv \
  --target yield \
  --out-model artifacts/surrogate.joblib \
  --out-meta artifacts/surrogate_meta.json
```

## 3) Simulate optimization loop

Adaptive:

```bash
python scripts/training/simulate_optimization.py \
  --data data/reactions.csv \
  --model artifacts/surrogate.joblib \
  --strategy adaptive \
  --budget 20 \
  --out artifacts/sim_adaptive.json
```

Random baseline:

```bash
python scripts/training/simulate_optimization.py \
  --data data/reactions.csv \
  --model artifacts/surrogate.joblib \
  --strategy random \
  --budget 20 \
  --out artifacts/sim_random.json
```

## 4) Recommend next experiment

```bash
python scripts/workflows/recommend_next.py \
  --data data/reactions.csv \
  --model artifacts/surrogate.joblib
```

Optional history file: CSV with `index` column to exclude already tried rows.
