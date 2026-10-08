# Reference implementation

Deliberately small, dependency-free, and not optimised. Its job is to prove the data model is
sufficient and to make the shape of a good answer concrete — not to be the best matcher.

```bash
pip install -e ".[dev]"
pytest
python -m agiofit.cli ../examples/profile-mature.json ../examples/cut-shirt.json explained
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

And a measurement estimated from size labels cannot make an answer look surer than a cold start
would: above 0.40, confidence is earned only by the measurements used that are not label
estimates, critical zones counting triple.

The disclosure level is held to the same standard: a level this implementation does not recognise
is refused rather than serialised, and when no level is requested the person's `default_level`
applies, falling back to `result_only`. A measurement the person lists in `never_share` never
leaves, as a number or as a judgement, at any level, though it still counts towards the answer.

History is read at the resolution it was written: a return that says where the garment was
wrong corrects those zones, and only a return that does not say where moves them all.

A flaw the person kept a garment despite, in the direction its verdict gives, counts half as much
the next time sizes are compared, though the report still names it.

A tolerance is read in the unit of its own measurement, and one left out counts as the wide end of
what its kind of measurement usually carries, so leaving it out never makes a measurement look more
precise than the usual one of its kind.

Only the measurements a garment uses count towards how sure an answer is, critical zones triple.
One declared less precise than usual for its source counts for less, and a girth loses precision
as it ages, so the same profile is less sure years later.

A past purchase without a category still counts when it is the same model of the same brand, and
is left out otherwise rather than guessed.
