Available Tooling

Goal

This document maps hackathon sponsor tools to the LabPilot MVP so the team stays disciplined and makes sponsor usage explicit in the demo and submission.

The MVP is an experiment recommendation product for R&D labs: load a real reaction dataset, train a surrogate model, run adaptive optimization, recommend the next experiment, and explain the recommendation.

The key principle is simple: use sponsor tools where they add real value to the core loop, not as decoration.

Core product workflow

The LabPilot MVP has five layers:
	1.	dataset and preprocessing
	2.	surrogate model / virtual lab
	3.	optimization engine
	4.	reasoning + guardrails
	5.	product packaging

The sponsor tools should map cleanly to these layers.

Sponsor tools and recommended usage

1. Nebius Token Factory

Priority: highest
Use in MVP: yes

This should be the primary LLM provider for the project. It is the most strategically important sponsor integration.

Recommended usage:
	•	explain why the next experiment is being recommended
	•	summarize observed patterns from prior experiments
	•	optionally refine candidate experiments before ranking
	•	generate concise user-facing rationale in the UI

Do not use it as the core optimizer. The optimizer should remain algorithmic and credible. Nebius LLM should sit on top as the reasoning layer.

Best demo line:
“Nebius Token Factory powers the scientific reasoning and recommendation explanation layer in LabPilot.”

2. Nebius Cloud Compute

Priority: highest
Use in MVP: yes

This is the second most important sponsor integration.

Recommended usage:
	•	train the surrogate model
	•	run optimization simulations
	•	evaluate baseline vs adaptive strategies
	•	host model inference or batch experiment scoring if needed

Best demo line:
“Nebius compute powers model training and the adaptive optimization loop behind the virtual lab.”

3. Tavily

Priority: medium-high
Use in MVP: probably yes, but lightly

Tavily should be used as a lightweight literature and guardrails layer, not as the center of the product.

Recommended usage:
	•	retrieve literature or public references on reaction condition ranges
	•	validate common operating ranges
	•	surface plausibility checks for suggested experiments
	•	support guardrails against obviously unrealistic recommendations

Do not let Tavily turn the product into RAG or paper summarization. It is a support tool.

Best demo line:
“Tavily provides literature-aware guardrails so LabPilot recommendations stay grounded in known reaction practices.”

4. OpenRouter

Priority: low
Use in MVP: optional

This is useful only if model flexibility becomes important. It is not core to the product story, and it is weaker than Nebius strategically for this hackathon.

Possible usage:
	•	backup LLM routing
	•	quick model comparisons for explanation quality

Recommendation:
only use if Nebius integration blocks or if you want a fallback.

5. Oumi

Priority: low-medium
Use in MVP: probably no

Oumi is more relevant for training/fine-tuning workflows. It is interesting, but not necessary for the MVP.

Possible future usage:
	•	train experiment recommendation policies
	•	fine-tune models on proprietary lab workflows

Recommendation:
do not spend time here for the hackathon MVP unless someone on the team already knows it.

6. Toloka

Priority: low
Use in MVP: no

Toloka is not central to the current product. It may be useful for evaluation or future human-in-the-loop labeling workflows, but it is not relevant to the MVP.

Recommendation:
ignore for now.

7. Hugging Face

Priority: medium
Use in MVP: maybe

This is useful for getting access to datasets, models, or quick experimentation.

Possible usage:
	•	locate reaction datasets
	•	store benchmark assets
	•	use standard modeling utilities if needed

Recommendation:
use only if it speeds up dataset access or model loading.

8. Cline

Priority: medium
Use in MVP: yes if it helps coding speed

Cline can help with implementation speed, scaffolding, and debugging. It is not part of the product architecture, but it may help the team move faster.

Recommendation:
use as a coding productivity aid, not as part of the product story.

Recommended MVP tooling stack

For the MVP, the stack should be:
	•	real-world reaction dataset
	•	Python modeling stack: pandas, scikit-learn, xgboost/lightgbm if needed
	•	Nebius Token Factory for recommendation explanations
	•	Nebius Cloud Compute for model training and optimization runs
	•	Tavily for literature guardrails
	•	FastAPI for backend
	•	React / Next.js for frontend

That is enough.

Mapping tools to product architecture

Dataset + preprocessing:
	•	pandas
	•	scikit-learn
	•	Hugging Face if needed for dataset retrieval

Virtual lab / surrogate model:
	•	scikit-learn
	•	xgboost/lightgbm
	•	Nebius compute for training runs

Optimization engine:
	•	Python optimization libraries
	•	scikit-optimize / bayesian optimization / custom bandit logic
	•	Nebius compute for simulations

Reasoning layer:
	•	Nebius Token Factory

Guardrails layer:
	•	Tavily

Backend:
	•	FastAPI

Frontend:
	•	React / Next.js

What not to do

Do not force every sponsor tool into the architecture. That makes the product look incoherent.

Do not use the LLM as the optimizer.

Do not turn Tavily into a paper-chat feature.

Do not spend time on Oumi, Toloka, or OpenRouter unless a concrete need appears.

Do not broaden scope just because credits are available.

Tooling recommendation

The MVP should explicitly use:
	•	Nebius Token Factory
	•	Nebius Cloud Compute
	•	Tavily

Everything else is optional.

That combination is enough to make sponsor usage clear and defensible while keeping the architecture tight.