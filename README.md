# LabPilot

LabPilot is a hackathon MVP for experiment recommendation in R&D workflows.

Current focus:
- train a surrogate model from historical experiment data,
- run optimization simulations (random vs adaptive),
- recommend the next experiment with a rationale stub.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . --no-build-isolation
```

Then run the modeling scripts in `docs/modeling_quickstart.md`.

