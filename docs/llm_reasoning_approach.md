# LLM Reasoning Approach (Current Status)

## Where LLM is right now

LLM is not yet integrated into the execution path.

Current recommendation logic is algorithmic:
- surrogate model predicts yield and uncertainty,
- adaptive policy (UCB) ranks candidates,
- contextual LinUCB updates reward-based policy online.

So far, the system is numerically adaptive but not LLM-driven.

## How LLM will be used

LLM (Nebius Token Factory) will be added as a reasoning layer **after** candidate ranking.

Planned flow:
1. Optimizer generates top-k candidates with scores.
2. LLM receives structured inputs:
   - candidate parameters,
   - predicted yield / uncertainty / score,
   - recent history (best-so-far trend),
   - optional guardrail notes.
3. LLM returns:
   - concise rationale for top choice,
   - exploit vs explore explanation,
   - caution notes (if any),
   - human-readable recommendation text.

## Design principle

LLM explains and contextualizes decisions.
LLM does **not** replace the optimizer.

This keeps recommendation quality grounded in measurable optimization logic while still providing an understandable scientist-facing explanation layer.

