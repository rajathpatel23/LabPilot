# LabPilot Modeling Quickstart

This guide assumes commands are run from repo root using the reorganized `scripts/`
tree (`training/`, `analysis/`, `benchmarks/`, `workflows/`, `demos/`).

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

You can also pass an Excel benchmark file directly, for example:
`--data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx`

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

Explicit online bandit (reward-driven):

```bash
python scripts/training/simulate_optimization.py \
  --data data/reactions.csv \
  --model artifacts/surrogate.joblib \
  --strategy bandit_ucb \
  --reward-mode improvement \
  --bandit-c 1.0 \
  --budget 20 \
  --out artifacts/sim_bandit_ucb.json
```

Contextual bandit (LinUCB, reward generalizes across similar conditions):

```bash
python scripts/training/simulate_optimization.py \
  --data data/reactions.csv \
  --model artifacts/surrogate.joblib \
  --strategy contextual_linucb \
  --reward-mode improvement \
  --linucb-alpha 1.0 \
  --linucb-lambda 1.0 \
  --budget 20 \
  --out artifacts/sim_contextual_linucb.json
```

## 4) Recommend next experiment

```bash
python scripts/workflows/recommend_next.py \
  --data data/reactions.csv \
  --model artifacts/surrogate.joblib \
  --top-k 5
```

Optional history file: CSV with `index` column to exclude already tried rows.

## 5) Compare trajectory improvement (adaptive vs random)

```bash
python scripts/analysis/compare_trajectories.py \
  --random artifacts/sim_random.json \
  --adaptive artifacts/sim_adaptive.json \
  --out-csv artifacts/trajectory_comparison.csv
```

This prints:
- final best-yield uplift,
- trajectory AUC uplift (better earlier convergence),
- time-to-threshold comparison.

## 6) Explore a new dataset quickly (EDA)

```bash
python scripts/analysis/explore_data.py \
  --data data/reactions.csv \
  --target yield \
  --out-json artifacts/eda_summary.json
```

For Excel benchmark files (Suzuki/Buchwald), pass the `.xlsx` path directly.

## 7) Label-ranking style baseline (Doyle dataset)

```bash
python scripts/benchmarks/label_ranking_baseline.py \
  --data data/doyle_data/Doyle_raw_data.csv \
  --substrate-cols aryl_halide,aryl_halide_smiles \
  --condition-cols base,ligand,additive \
  --yield-col yield \
  --out-json artifacts/label_ranking_doyle.json
```

This reports top-k condition ranking metrics against a random ranking baseline.

Multi-seed substrate-holdout benchmark:

```bash
python scripts/benchmarks/benchmark_label_ranking.py \
  --data data/doyle_data/Doyle_raw_data.csv \
  --substrate-cols aryl_halide,aryl_halide_smiles \
  --condition-cols base,ligand,additive \
  --yield-col yield \
  --test-frac 0.25 \
  --seeds 20 \
  --out-json artifacts/benchmark_label_ranking_doyle.json
```

This gives mean/std for top-k and MRR vs random across multiple random substrate-holdout splits.

Descriptor-enhanced condition-ranking benchmark (Doyle):

```bash
python scripts/benchmarks/benchmark_doyle_condition_ranking.py \
  --raw-data data/doyle_data/Doyle_raw_data.csv \
  --aryl-dft data/doyle_data/aryl_halide_DFT.csv \
  --additive-dft data/doyle_data/additive_DFT.csv \
  --yield-col yield \
  --test-frac 0.25 \
  --seeds 20 \
  --out-json artifacts/benchmark_doyle_condition_ranking.json
```

This evaluates ranking quality on unseen substrates using descriptor-informed condition scoring.

## 8) Multi-seed benchmark (robust comparison)

Note: this is now **diagnostic only**. Do not use for headline claims.
For claim-quality evaluation, run Section 9 (group-holdout) instead.

```bash
python scripts/benchmarks/benchmark_strategies.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --model artifacts/surrogate_suzuki.joblib \
  --budget 20 \
  --seeds 20 \
  --strategies random,greedy,adaptive,contextual_linucb \
  --reference-strategies random,greedy \
  --allow-non-holdout \
  --out-json artifacts/benchmark_suzuki_multi_seed.json
```

This reports mean/std, threshold metrics, and confidence intervals vs both random and greedy baselines.

## 9) Group-holdout generalization benchmark (anti-overfitting check)

```bash
python scripts/benchmarks/benchmark_generalization.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --target Product_Yield_PCT_Area_UV \
  --group-col Reactant_1_Short_Hand \
  --features Reactant_1_Short_Hand,Reactant_1_eq,Reactant_1_mmol,Reactant_2_Name,Reactant_2_eq,Catalyst_1_Short_Hand,Catalyst_1_eq,Ligand_Short_Hand,Ligand_eq,Reagent_1_Short_Hand,Reagent_1_eq,Solvent_1_Short_Hand \
  --folds 3 \
  --seeds 5 \
  --budget 20 \
  --strategies random,greedy,adaptive,contextual_linucb \
  --out-json artifacts/benchmark_generalization_suzuki.json
```

This retrains the surrogate on train-groups only and evaluates strategies on unseen holdout groups.

## 10) Plot benchmark results (to inspect yield behavior)

```bash
python scripts/benchmarks/plot_benchmark_results.py \
  --benchmark-json artifacts/benchmark_generalization_suzuki_3x3.json \
  --out-dir artifacts/plots \
  --title-prefix "Suzuki Holdout"
```

This generates:
- best-yield bar chart,
- trajectory-AUC bar chart,
- threshold-hit-rate bar chart.

## 11) Add human-facing reasoning on top of ranked recommendation

First, save recommendation output:

```bash
python scripts/workflows/recommend_next.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --model artifacts/surrogate_suzuki.joblib \
  --top-k 5 > artifacts/recommendation_top5.json
```

Then generate explanation payload:

```bash
python scripts/workflows/reason_recommendation.py \
  --recommendation-json artifacts/recommendation_top5.json \
  --out-json artifacts/recommendation_reasoning.json
```

Optional (if Nebius key is configured):

```bash
NEBIUS_API_KEY=... \
NEBIUS_API_BASE=https://api.studio.nebius.com/v1 \
NEBIUS_MODEL=meta-llama/Meta-Llama-3.1-70B-Instruct \
python scripts/workflows/reason_recommendation.py \
  --recommendation-json artifacts/recommendation_top5.json \
  --out-json artifacts/recommendation_reasoning_llm.json \
  --use-llm
```

## 12) Agentic end-to-end showcase (optimizer + guardrails + reasoning)

```bash
python scripts/demos/agentic_showcase.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --model artifacts/surrogate_suzuki.joblib \
  --top-k 5 \
  --out-json artifacts/agentic_showcase_output.json
```

Optional tool integrations:
- `--use-llm` (Nebius/OpenAI-compatible reasoning path)
- `--use-tavily` (literature guardrail lookup)

## 13) Integration readiness + raw LLM payload

Check sponsor integration readiness:

```bash
python scripts/check_integrations.py
```

Build direct LLM input payload from model recommendation:

```bash
python scripts/workflows/recommend_next.py \
  --data data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx \
  --model artifacts/surrogate_suzuki.joblib \
  --top-k 5 > artifacts/recommendation_top5.json

python scripts/workflows/build_llm_input.py \
  --recommendation-json artifacts/recommendation_top5.json \
  --out-json artifacts/llm_input.json
```

Prompt template used by default:
- `prompts/recommendation_reasoning_prompt.md`

Optional: include evidence file for grounded reasoning:
`--evidence-json artifacts/guardrail_evidence.json`
