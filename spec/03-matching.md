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
6. A consumer MUST NOT produce a match report from a document written to a schema version it
   cannot read. Refusing is the only honest response: across such a version fields move and
   disappear, so reading the document anyway means looking for values where they no longer are and
   answering from whatever happens to be found, which produces a confident answer built on the
   wrong numbers. Which versions can be read across is decided by the version itself: while the
   major version is `0`, a change of minor version is free to break and MUST be treated as
   unreadable; from `1.0` onwards the major version is the line. A newer patch MAY be read, and
   the consumer SHOULD say in `caveats` that part of the document was ignored.
7. When a consumer cannot evaluate a zone that has been named — by the garment in
   `critical_zones` or `intended_ease`, or by the consumer's own category defaults — it MUST name
   that zone in `caveats`, and the absence MUST NOT raise `confidence`. A consumer that has no
   critical zones for a category MUST say so rather than treat the empty set as coverage of
   everything. A zone that was never looked at is not a zone that fitted, and an answer that
   skipped the most important measurement must not score like one that checked it.

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

Every tolerance is read in the unit of its own measurement. A body measurement that declares none
is not taken as exact: the reference assumes the wide end of what its kind of measurement usually
carries, 1.5 cm for a tape or a scan and 3 cm for anything else, so that leaving the field out
never makes a measurement look more precise than the usual one of its kind.

Eight details worth stealing:

- **Learned offsets go where the history says the garment was wrong.** An outcome that carries
  `zone_feedback` moves only the zones it names, each in the direction of its verdict, and a
  verdict on `overall` covers the zones not named one by one. Only an outcome that does not say
  where moves every zone, by the scale below. A kept garment moves nothing: it records what was
  accepted.
- **What was accepted counts for less next time.** When a kept garment lists a zone in
  `kept_despite` and the same entry's `zone_feedback` says which way that zone was off, a later
  miss in that direction, on that zone, in the same category, counts half as much when sizes are
  compared, whatever the brand: the compromise is the person's, not the brand's. The judgement in
  the report is not softened, so a waist that is too loose is still reported as too loose. A zone
  listed without a verdict of its own says what was tolerated but not which way, and teaches
  nothing.
- **Learned offsets are scaled per zone.** A brand that runs small runs small in the torso. Shifting
  a collar by the same number of centimetres turns a useful correction into a wrong answer, since a
  centimetre at the neck is an entire size.
- **Same-brand history counts double.** Sizing drift is overwhelmingly brand-specific.
- **The same outcome counts once.** An entry identical to another in everything but `source` and
  `import_ref`, with its date read as a moment, is the same event written twice, and counts once.
- **On a girth, a recent outcome outweighs an old one.** Next to the others, an outcome weighs
  1.5 / (1.5 + 1 cm for every full year since it happened), the drift the measurements are aged
  by. On a length, which an adult does not grow out of, every outcome weighs the same.
- **The same model needs no category.** A history entry without a category still counts when its
  `brand` and `style_id` match the garment's, which makes it the same model; any other entry
  without one is left out rather than guessed.
- **One preference decides each zone.** A preference about the zone itself wins over one about
  the garment overall; between two at the same level the declared one wins over the inferred
  one, and then the more recent. Preferences are never added together, so a repeated import
  counts once.

## Cold start

With no body measurements, the reference implementation falls back to same-brand purchase history
and derives a size from labels and outcomes, capped at 0.40 confidence.

It deliberately refuses to do this across brands. A size label from one brand says close to nothing
about another's, and pretending otherwise is precisely how size charts earned their reputation.

The same ceiling holds when the evidence is the same. A body measurement whose `source` is
`estimated_from_size_labels` is a size label written down as a measurement, and if it could lift
an answer past 0.40, the refusal above would be undone one step removed. Above the ceiling, the
reference implementation earns confidence only through the measurements used that are not label
estimates, critical zones weighing three times as much, as they do when a size is chosen, and it
says so in `caveats` whenever the ceiling lowers an answer. Other sources are left as they are: a
measurement inferred from history can come from the finished measurements of garments that were
kept, which are centimetres, not labels.

## Confidence

Confidence is a producer's own estimate, not a probability. The reference implementation combines
zone coverage, coverage of *critical* zones specifically, the quality of the measurement sources,
the margin between the best size and the runner-up, and the volume of relevant history, under a
ceiling when the measurements used were estimated from size labels (see *Cold start*).

Critical zone coverage counts every critical zone the consumer knows about, including the ones it
could not reach: a zone with no mapping, and a zone whose measurement the garment never published,
both stay in the denominator. Leaving them out is what lets a document score better for saying
less, and requirement 7 exists to forbid it.

The quality of the measurements is judged on the ones this garment uses, critical zones weighing
three times as much, as they do when a size is chosen: a measurement no garment of this kind reads
cannot raise or lower the answer. Each counts for its source, the producer's own confidence and
its precision. A tolerance wider than the usual one for its source lowers that precision in
proportion, so a tape measurement declared within 3 cm counts like a remembered one within 3, and
a girth loses 1 cm of precision for every full year since it was taken, while the lengths of an
adult do not. Age changes how far an answer can be trusted, not the judgement of any zone.

The volume of history is judged the same way, zone by zone with critical zones triple, and an
outcome counts for less on a girth as it ages, as a measurement does. Outcomes of one age keep
the judgement they gave: only next to a more recent one does an old outcome say less.

A consumer MUST NOT present a confidence from another implementation as comparable to its own.
