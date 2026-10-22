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
leaves, as a number, as a judgement or by name, at any level, though it still counts towards the
answer.

History is read at the resolution it was written: a return that says where the garment was
wrong corrects those zones, and only a return that does not say where moves them all.

A flaw the person kept a garment despite, in the direction its verdict gives, counts half as much
the next time sizes are compared, though the report still names it.

A tolerance is read in the unit of its own measurement and on the same girth, so a flat-laid width's
tolerance is doubled with the width. One left out counts as the wide end of what its kind of
measurement usually carries, so leaving it out never makes a measurement look more precise than the
usual one of its kind.

Only the measurements a garment uses count towards how sure an answer is, critical zones triple.
One declared less precise than usual for its source counts for less, and a girth loses precision
as it ages, so the same profile is less sure years later.

A past purchase without a category still counts when it is the same model of the same brand, and
is left out otherwise rather than guessed.

One preference decides each zone, never a sum: the one about the zone before the one about the
whole garment, the person's own before an inferred one, the latest before an older one.

The same outcome written twice counts once. On a girth a recent outcome outweighs an old one, and a
history that has aged as a whole leaves the bands where they were and makes the answer less sure.

A size label is read the way a person reads it: spaces and capitals do not make another label,
and a size system written inside one is not guessed.

A reference to a Cut Profile is read without the spaces around it. Its capitals count, since an
identifier may be a URL.

A measurement under a name this implementation does not know is named from `explained` up, so
the person can find it.

A preference moves each zone as far as a learned correction does: at the collar, where a
centimetre is a whole size, a relaxed fit is about a size larger, not four.

A size is held to its own explanation: one too tight where a seam cannot be let out is not
recommended, and any other that is too tight or too loose somewhere is named as the closest there
is, no surer than a cold start, unless the person has already kept a garment despite that flaw.

A preference the person declared at full strength is a constraint, not a strong taste: a size that
breaks it is not recommended, and when every size does, none is.

A date is read as RFC 3339 writes it, the same on every Python this package supports, and one that
cannot be read stops the answer instead of counting as today's.

Each measurement is read in its own unit. The profile's `units` is the unit the person prefers to
see, and changes nothing here.

`morphology` is descriptive here: no trait moves an answer, because none can be turned into
centimetres without inventing them.

`based_on` counts what the answer used, not what the profile holds. A layer the person lists in
`never_share` leaves its counts out, and a measurement listed there is not counted.
Nor is a layer the person lists there told through the reasoning: no caveat, note or suggestion
about it leaves, and a size set aside for its sake leaves the alternatives.

Who recorded an outcome does not change how much it counts, and `import_ref` never reaches a
report.

The band a zone was judged against leaves only at `full`, and never when the person lists
preferences or history in `never_share`: it carries both.

Each level carries only what `spec/04` allows it. The schema of this version does not check it, so
a test does, on reports of every kind.

At `result_only` a report says what kind of answer it is and nothing about the profile: what the
answer rests on and what would improve it leave from `explained` up. A critical zone the garment
does not publish is named, and not put down to the profile; a suggestion asks only for what the
garment uses, critical zones first.
