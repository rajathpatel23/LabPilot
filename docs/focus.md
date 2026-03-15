Focus

Yes. That is the right order.

Do modeling first, then wrap it in backend, then frontend last.

The reason is simple: the only thing that actually matters in this product is whether you can produce a credible next-experiment recommendation loop on real data. If that core loop is weak or broken, a polished frontend just hides an empty product. For a hackathon, the model and optimization loop are the product.

The build order should be:
	1.	Data + surrogate model
Get a real dataset loaded, pick the target, preprocess features, train a first model that predicts yield reasonably well. This gives you the virtual lab.
	2.	Optimization loop
Add random search baseline and one adaptive strategy. Run a 20-step simulation and make sure you can generate:

	•	next experiment recommendation
	•	predicted score
	•	best-so-far curve

This is the core demo.
	3.	LLM reasoning layer
Once the optimizer works, add the explanation layer:

	•	summarize what patterns were found
	•	explain why the next experiment is recommended
	•	optionally use literature guardrails

This makes it product-shaped.
	4.	Backend
Only after the loop works locally should you expose it through FastAPI endpoints. Backend should just package existing logic, not invent logic.
	5.	Frontend
Frontend is last. It should be very thin:

	•	dataset/objective/budget input
	•	next recommendation card
	•	progress chart
	•	experiment history table

That’s enough.

A good mental model is:
	•	modeling proves the product works
	•	backend makes it callable
	•	frontend makes it demoable

For the first 2–3 hours, you should stay entirely in Python scripts or notebooks and get these artifacts working:
	•	train_surrogate.py
	•	simulate_optimization.py
	•	recommend_next.py

If those three work, the rest is packaging.

The concrete first milestone should be: load a real reaction dataset, train a surrogate model, and print one recommended next experiment from an adaptive search strategy.

If you can do that, you already have the heart of LabPilot.

Structure the immediate work like this:

Milestone 1

Dataset loaded, target chosen, preprocessing done.

Milestone 2

Surrogate model trained and evaluated.

Milestone 3

Random baseline + adaptive optimizer working over fixed budget.

Milestone 4

One function returns:

{
  "next_experiment": ..., 
  "predicted_yield": ..., 
  "rationale_stub": ...
}

Then move to backend and frontend.

Do not start with frontend or backend. Start with the modeling loop. That is the priority.

Next

Define exactly what the modeling folder should contain and what the first scripts are.