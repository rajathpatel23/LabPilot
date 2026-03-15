# Contextual Bandit / Learned Policy Approach

## Goal

This document defines the RL-shaped extension for LabPilot that is both technically credible and realistic for the current dataset and product scope.

The key idea is simple:
LabPilot is not a classic long-horizon RL problem first. It is a **budgeted experiment selection** problem. The right decision-policy framing is therefore **contextual bandits or lightweight policy learning over a virtual lab**, not PPO/DQN theater.

## Why this approach is the right fit

The current LabPilot setup has the following structure:
- the system observes historical experiments and current search state
- it chooses the next experiment to run
- it observes reward in the form of yield or improvement
- it updates belief and repeats under a fixed budget

This is sequential, but the dominant challenge is **exploration vs exploitation under sparse, expensive feedback**.

That makes the most natural algorithm families:
- Bayesian optimization
- contextual bandits
- offline policy learning over logged data
- policy learning over the surrogate environment

This is a much cleaner fit than trying to force deep RL methods designed for long-horizon control.

## Product framing

The product framing should be:

> LabPilot uses a virtual lab built from real reaction data and learns an adaptive decision policy for selecting the next experiment under a constrained budget.

That is stronger than saying:
- “we did RL for chemistry”

And more credible than saying:
- “we only did regression and heuristics”

## Problem formulation

### Environment
The environment is the surrogate model trained on a real reaction optimization dataset such as Suzuki–Miyaura.

Input:
- reaction conditions / experiment parameters

Output:
- predicted yield
- optional uncertainty estimate

This surrogate acts as the **virtual lab**.

### Episode
One optimization campaign = one episode.

Example:
- budget = 20 experiments
- episode length = 20 decision steps

The episode ends when the budget is exhausted.

### State
The state should summarize what the system knows so far.

Recommended state features:
- current step index
- remaining budget
- best yield observed so far
- mean yield of prior experiments
- top-k recent experiment outcomes
- uncertainty summary over candidate pool
- summary of explored regions
- optional substrate / reaction context features

The state should be compact and intentionally engineered. Do not overcomplicate it.

### Action
The action is to choose the next experiment from a finite candidate pool.

Recommended action design:
- rank all currently available candidate experiments
- choose one experiment to run next

This makes the action space discrete and much easier to model.

### Reward
Recommended reward options:

Option A: raw yield
- simplest and easiest to explain

Option B: improvement over current best
- better aligns with the product objective of making progress efficiently

Option C: threshold bonus
- reward a positive bonus when crossing a target yield threshold

Best default for the benchmark:
- use **improvement over best-so-far** as the main reward
- also report final best yield as the external product metric

## Candidate approaches

### 1. Contextual bandit
This is the cleanest first extension.

Context:
- state summary + candidate features

Action:
- select one candidate experiment

Reward:
- observed yield or improvement

Good algorithms:
- LinUCB
- Thompson sampling
- neural contextual bandit

Why it is good:
- sample-efficient
- easy to explain
- directly models exploration vs exploitation
- strong fit for one-step experimental selection

### 2. Learned policy over virtual lab
This is the more ambitious extension.

The surrogate model defines the environment.
A policy is trained to maximize cumulative reward or final best yield over an episode.

Possible implementations:
- policy gradient over discrete candidate actions
- DQN over top-N candidate pool
- imitation / offline policy learning from synthetic rollouts

Why it is attractive:
- gives a stronger “policy learning” story
- moves beyond hand-designed UCB scoring
- still fits the product loop cleanly

Why it is risky:
- more engineering effort
- harder to stabilize and benchmark well
- may not outperform a strong bandit baseline in limited time

## Recommended benchmark ladder

The policy benchmark should compare increasing levels of sophistication.

1. random search
2. surrogate-UCB adaptive strategy
3. contextual LinUCB
4. optional learned policy over virtual lab

This is the right hierarchy because it makes the project look deliberate rather than arbitrary.

## Success metrics

The policy extension should be evaluated using product-facing metrics, not only RL terminology.

Primary metrics:
- final best yield
- mean final best yield across seeds
- trajectory AUC
- threshold hit rate
- average step-to-threshold
- win rate vs random

Secondary metrics:
- regret vs oracle best candidate
- average improvement per step
- stability across random seeds

## Recommended implementation path

### Phase 1: contextual bandit baseline
Build this first.

Requirements:
- finite candidate pool
- state summary features
- one contextual bandit policy
- multi-seed comparison against random and surrogate-UCB

This gives you a credible policy-learning story fast.

### Phase 2: learned policy
Only do this if Phase 1 is already stable.

Requirements:
- compact state representation
- discrete action selection over candidate pool
- episodic rollout over virtual lab
- stable evaluation across seeds

If this takes too long, keep it as future work.

## Product narrative

The right product narrative is:

> LabPilot starts with a virtual lab learned from real reaction optimization data. On top of that, it runs adaptive experiment-selection policies that balance exploration and exploitation under a fixed experiment budget. In the MVP, this is implemented with contextual bandits and uncertainty-aware recommendation. Learned policies over the virtual lab are the next step.

This is much stronger than claiming generic “RL for chemistry.”

## Where the LLM fits

The LLM is not the policy.
The LLM explains policy decisions.

Input to LLM:
- selected candidate
- top competing candidates
- reward / uncertainty decomposition
- recent experiment history

Output from LLM:
- why this experiment is recommended now
- whether it is exploitative or exploratory
- what uncertainty it is trying to resolve
- optional caution note

That separation keeps the architecture credible.

## Recommended immediate next steps

1. Finish multi-seed benchmark for current strategies
2. Add contextual-bandit benchmark as the first RL-shaped extension
3. Compare against random and surrogate-UCB
4. Report mean/std, win rate, and threshold metrics
5. Only then consider learned policy training over the virtual lab

## What not to do

Do not:
- force PPO, SAC, or DQN onto the raw problem without careful action/state design
- overcomplicate the state
- replace the current working adaptive engine
- let the LLM become the policy
- claim full RL if the implementation is really a bandit / uncertainty-aware recommender

## Final recommendation

For LabPilot, the correct RL-shaped path is:
- **contextual bandit first**
- **learned policy over virtual lab second**
- **full long-horizon RL only as future work when richer lab dynamics exist**

This path preserves product credibility, aligns with the dataset structure, and gives the project more technical depth without breaking execution speed.

## Practical MVP pivot (Paper-Proof Mode)

If the immediate objective is to prove the ranking-paper direction quickly and credibly, use this narrower track:

1. keep only two benchmark lines:
   - random baseline
   - ranking-based recommender
2. prove ranking quality on Doyle-style substrate holdout splits
3. add LLM reasoning on top of ranked outputs
4. avoid expanding algorithm scope until proof is stable

This is valid and high signal for hackathon judging.

### What “prove the paper direction” means in this repo

Use ranking metrics that directly reflect the paper-style objective:
- top-1 hit rate
- top-3 hit rate
- top-5 hit rate
- MRR (mean reciprocal rank)

And always compare against random under the same split protocol.

### Minimal benchmark protocol

Dataset:
- Doyle raw dataset (with descriptor-enhanced variant if available)

Split:
- substrate holdout
- multi-seed repeated runs

Required outputs:
- mean and std for top-k metrics
- mean and std for MRR
- uplift over random

### Current scripts for this mode

Use:
- `benchmark_label_ranking.py` (minimal substrate-only ranking baseline)
- `benchmark_doyle_condition_ranking.py` (descriptor-informed condition ranking)

### Recommended claim format

Use one sentence in the demo:

> On Doyle substrate-holdout ranking benchmarks, LabPilot’s ranking policy outperforms random recommendation on top-k hit rate and MRR, and we layer LLM explanations on top of these policy decisions for scientist-facing guidance.

### Where reasoning fits in this pivot

Reasoning layer should consume:
- ranked candidates
- ranking scores / relative confidence
- gap between top candidates

Reasoning layer should output:
- why top candidate is preferred now
- exploit vs explore framing
- short caution if score gap is small

Keep separation strict:
- ranking policy chooses
- LLM explains

### What to skip while in this mode

Skip for now:
- deep RL policy training
- broad algorithm proliferation
- complex backend abstractions

Focus only on:
- proving ranking vs random
- packaging explanation quality
