# Reference implementation

Deliberately small, dependency-free, and not optimised. Its job is to prove the data model is
sufficient and to make the shape of a good answer concrete — not to be the best matcher.

```bash
pip install -e ".[dev]"
pytest
python -m agiofit.cli ../examples/profile-mature.json ../examples/cut-shirt.json
python -m agiofit.cli ../examples/profile-cold-start.json ../examples/cut-shirt.json result_only
```

## Files

| File | What it holds |
|---|---|
| `agiofit/mapping.py` | Zone tables, category defaults, preference shifts. Everything here is a default the garment can override. |
| `agiofit/match.py` | Scoring, confidence, explanation, cold-start fallback, disclosure-level serialisation. |
| `agiofit/cli.py` | Two arguments and a JSON document. |

## What the tests are actually protecting

Not the numbers — those will change. The invariants: flat-laid measurements get doubled, critical
zones dominate, history biases the result in the right direction, cold start still answers and says
how sure it is, and `result_only` output contains no reconstructable body data.
