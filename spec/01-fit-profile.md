# Fit Profile

Schema: `schemas/fit-profile.schema.json`

Three independent layers. Each is optional; a profile with only one layer is valid and usable.

## Layer 1 — Body

Measurements, each with `value`, `unit`, `source`, `observed_at` and ideally `tolerance`.

`units`, at the top of the profile, is the unit the person prefers to see measurements in. It says
nothing about how a value is written: each measurement carries its own `unit`, and a consumer MUST
read it in that unit, never in `units`. Read in inches, the 100 cm chest of the example profile
would be 254 cm. A profile whose `units` says inches while its measurements are in centimetres is
valid, and its measurements are in centimetres. No value in this version has a mass, so
`units.mass` names a unit for nothing, and producers SHOULD leave it out.

`tolerance` carries most of the honesty in this specification. A waist typed in from memory and one
measured with a tape are both numbers; only the tolerance distinguishes them, and the matcher uses
it to widen or narrow its judgement.

A profile holds one value per measurement, the latest. When a measurement is taken again, the new
one replaces the old one whole. `observed_at` is when the value was measured, not when the profile
was last saved (that is `updated_at`), and producers MUST NOT change `observed_at` unless the
measurement is taken again. Bodies change, and an `observed_at` from three years ago is
information, not noise.

The profile does not carry earlier values, and producers MUST NOT add them, under `x_` keys or
anywhere else. A series of measurements over time can reveal a pregnancy or an illness
(`06-threat-model.md`), and matching needs only the latest value. A vault MAY keep earlier values
for the person, outside the profile; nothing in this format requires keeping them.

`morphology` exists because two people with identical girths can need different garments — sloped
shoulders, a long torso. It is deliberately qualitative: a five-point scale a person can answer
honestly beats a measurement they cannot take correctly.

The reference implementation does not use `morphology`. There is no defensible way to turn "above
average" into centimetres of ease, and a guess would move answers by amounts nobody measured, so a
trait stays in the profile for a consumer that can use it. A trait carries its `source` like every
other value (`00-overview.md`), although the schema does not require it there. `tape_measured` and
`estimated_from_size_labels` say nothing about how a trait was judged, and producers SHOULD NOT use
them for one.

## Layer 2 — Preferences

What the person *wants*, per `category` and `zone`, on the same five-point scale as the garment's
`cut` field, so a person reads both the same way. A consumer should not compute with `cut`
(`02-cut-profile.md`).

`strength` separates a taste from a constraint. "I prefer relaxed sleeves" and "I cannot wear
anything tight at the neck" are not the same statement and MUST NOT be encoded identically. A
producer SHOULD write a constraint the person states at `strength` 1, and a stated taste below it.

Preferences MAY be inferred from history, in which case `source` is `inferred_from_history` and the
producer SHOULD make the inference visible to the person, who can then correct it.

Where a declared preference and an inferred one disagree, consumers SHOULD follow the declared
one: an inference is a guess at what the person wants, the declaration is what they said.

## Layer 3 — History

Outcomes, not intentions: what was kept, what was returned, and why.

This is the layer no other system holds in portable form, and the hardest one to rebuild from
scratch. Two fields carry its weight:

- `zone_feedback` — where the garment was wrong, not merely that it was.
- `kept_despite` — the zones that were imperfect on a garment the person kept anyway.

`kept_despite` is the only field in the specification that records a *tolerated* compromise.
Without it, a system learns that a person rejects tight shoulders; with it, the system learns they
will accept a slightly loose waist to get the shoulders right. That distinction is the difference
between a system that annoys people and one they trust.

`import_ref` groups everything that arrived from one source, so a person can delete an entire
import in one action. Producers SHOULD populate it for any imported batch. It names the batch and
nothing else: it MUST NOT carry a retailer's customer ID, an order number or any other identifier
taken from the source, for the reason `profile_id` must not (see *Identifiers*). The profile
travels whole when the person moves it to another vault, wallet or fit provider, and such a
reference would tie it to the source's records.

`source` says who recorded an outcome, not how much it counts. What happened to a garment does not
change with who wrote it down, so the reference implementation gives an outcome the same weight
whoever recorded it, as `02-cut-profile.md` gives none to `provenance.published_by`: weighting the
field would weight the label on an entry instead of what the entry says.

`garment_ref.category` is what lets one garment teach anything about another, and producers
SHOULD fill it. An importer that cannot tell the category SHOULD leave it out rather than guess:
a wrong category would carry a shirt's lesson over to a pair of trousers.

`garment_ref.size_label` is how a past purchase is lined up against the sizes of a garment, and
producers SHOULD write the size alone, as its size system names it, with the system in
`size_system`: `41` with `IT`, not `IT 41`.

`garment_ref.cut_profile_id` joins a past purchase to one document exactly (`02-cut-profile.md`),
so producers SHOULD write it exactly as the Cut Profile does, and leave it out when there was none:
an empty reference points at no document.

Entries carry no identifier in this version (`05-open-questions.md`), so an entry written twice
cannot be told apart from two events that look the same. Producers, importers above all, SHOULD
NOT add an entry the history already holds. An entry that turns out to be wrong is corrected where
it is, by changing or removing it: adding another records a second event and leaves the wrong one
counting. The correction of a match report (`03-matching.md`, requirement 3) is a different thing:
it records what happened with a garment, a new outcome, and is added as one.

## Identifiers

`profile_id` is pseudonymous. It MUST NOT be derived from a civil identity, an email address, or a
retailer's customer ID. Consumers MUST NOT rely on its stability: rotating it is a legitimate
privacy action, and a system that breaks when it changes has built a tracking dependency.
