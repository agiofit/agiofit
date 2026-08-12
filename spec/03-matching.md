# Matching and explanation

Schema: `schemas/match-report.schema.json` · Reference: `reference/agiofit/match.py`

The algorithm is **not normative**. Any implementer is free to do better, and most will. What is
normative is the *shape of the answer*.

## Normative requirements

1. A match report MUST expose a `confidence`.
2. `recommended_size` MAY be `null`. "I do not know enough" is a valid and sometimes correct
   answer, and the schema makes it expressible so implementations are not forced to guess.
3. A report MUST be correctable, and the correction SHOULD flow back into the profile as a
   new `wear_outcome`.
4. When a consumer falls back on defaults instead of published garment data, it MUST say so in
   `caveats` and MUST lower `confidence`.
5. `improve_by` SHOULD be populated whenever confidence is below the implementation's own
   threshold. A person who is told what is missing can fix it; a person given a bare low number
   cannot.

## The reference approach, in outline

Per candidate size, per zone where both sides have data:

    effective_garment = published_measurement
                        × 2 if flat-laid and the zone is a girth
                        × (1 + usable_stretch) for girths
    ease              = effective_garment − body_measurement
    band              = intended_ease (or a category default)
                        + preference shift
                        + learned offset from history

Ease outside the band is penalised in proportion to the distance, divided by a scale derived from
the measurement and production tolerances — so a garment with sloppy tolerances is judged more
loosely, which is the honest outcome. Critical zones carry triple weight, and being too tight in a
critical zone is penalised more heavily than being too loose, because a shoulder seam cannot be let
out.

Two details worth stealing:

- **Learned offsets are scaled per zone.** A brand that runs small runs small in the torso. Shifting
  a collar by the same number of centimetres turns a useful correction into a wrong answer, since a
  centimetre at the neck is an entire size.
- **Same-brand history counts double.** Sizing drift is overwhelmingly brand-specific.

## Cold start

With no body measurements, the reference implementation falls back to same-brand purchase history
and derives a size from labels and outcomes, capped at 0.40 confidence.

It deliberately refuses to do this across brands. A size label from one brand says close to nothing
about another's, and pretending otherwise is precisely how size charts earned their reputation.

## Confidence

Confidence is a producer's own estimate, not a probability. The reference implementation combines
zone coverage, coverage of *critical* zones specifically, the quality of the measurement sources,
the margin between the best size and the runner-up, and the volume of relevant history.

A consumer MUST NOT present a confidence from another implementation as comparable to its own.
