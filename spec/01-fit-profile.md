# Fit Profile

Schema: `schemas/fit-profile.schema.json`

Three independent layers. Each is optional; a profile with only one layer is valid and usable.

## Layer 1 — Body

Measurements, each with `value`, `unit`, `source`, `observed_at` and ideally `tolerance`.

`tolerance` carries most of the honesty in this specification. A waist typed in from memory and one
measured with a tape are both numbers; only the tolerance distinguishes them, and the matcher uses
it to widen or narrow its judgement.

Producers SHOULD NOT silently update a measurement in place. Bodies change, and an `observed_at`
from three years ago is information, not noise.

`morphology` exists because two people with identical girths can need different garments — sloped
shoulders, a long torso. It is deliberately qualitative: a five-point scale a person can answer
honestly beats a measurement they cannot take correctly.

## Layer 2 — Preferences

What the person *wants*, per `category` and `zone`, on a five-point scale shared with the garment's
`cut` field so the two can be compared directly.

`strength` separates a taste from a constraint. "I prefer relaxed sleeves" and "I cannot wear
anything tight at the neck" are not the same statement and MUST NOT be encoded identically.

Preferences MAY be inferred from history, in which case `source` is `inferred_from_history` and the
producer SHOULD make the inference visible to the person, who can then correct it.

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
import in one action. Producers SHOULD populate it for any imported batch.

## Identifiers

`profile_id` is pseudonymous. It MUST NOT be derived from a civil identity, an email address, or a
retailer's customer ID. Consumers MUST NOT rely on its stability: rotating it is a legitimate
privacy action, and a system that breaks when it changes has built a tracking dependency.
