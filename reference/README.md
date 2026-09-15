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
| `agiofit/mapping.py` | Zone tables, category defaults, preference shifts — and two statements of what this implementation cannot do: which zones it is able to evaluate at all, and which categories it has no critical zones for. The defaults a garment can override; the two statements it cannot. |
| `agiofit/match.py` | Scoring, confidence, explanation, cold-start fallback, disclosure-level serialisation. |
| `agiofit/cli.py` | Two arguments and a JSON document. |

## What the tests are actually protecting

Not the numbers — those will change. The invariants: flat-laid measurements get doubled, critical
zones dominate, history biases the result in the right direction, cold start still answers and says
how sure it is, and `result_only` output contains no reconstructable body data.

And, since half the zone vocabulary has no mapping here: a zone this implementation cannot evaluate
is named rather than dropped, and costs confidence rather than passing unnoticed. Every zone in the
schema is either mapped or knowingly unmapped, and every category either has critical zones or
declares that it has none — both checked against the published schemas, so adding a zone or a
category turns a test red instead of going unnoticed.
