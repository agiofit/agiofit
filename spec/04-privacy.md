# Privacy and disclosure

Privacy here is a design constraint, not a paragraph at the end of a document. It is also the only
durable reason a person would prefer this to a vendor profile.

## The default is not to share the profile

Four levels, declared in the match report itself:

| Level | The verifier receives |
|---|---|
| `result_only` | A size, a confidence and the caveats on the answer. Nothing else. |
| `explained` | Plus reasoning per zone — "tight at the shoulders" — with no numbers, and more. |
| `scoped` | Plus each zone's ease, from which the body measurements this garment needs follow. |
| `full` | Plus the band of each zone. Should be rare, and a consumer SHOULD justify it. |

At `explained` the "more" is the alternatives, what the answer rests on (`based_on`) and what would
improve it (`improve_by`). No level carries the profile itself: `full` is all that a report holds.

When a request names no level, the report MUST be serialised at the level the person declared in
`disclosure_defaults.default_level`, and at `result_only` when the profile declares none. The
person's level is a default, not a ceiling: a request may name another level, and whether a
verifier may ever receive more than the person's default is for the vault to decide.

A measurement the person lists in `disclosure_defaults.never_share` MUST NOT reach a report at
any level, as a number, as a per-zone judgement or by name: a judgement read against the
garment's public measurements narrows the body measurement to the width of the ease band, and a
name, even in a suggestion to take the measurement again, says that it exists and how it was
taken. Listing the `body` layer withholds every zone and every name. The measurement still
counts towards the answer, because the computation happens where the profile lives; what the
list governs is what leaves it. The reference implementation leaves such a zone out of the
explanation altogether and, from `explained` up, says in `caveats` that some zones were
withheld at the person's request.

`based_on` (`03-matching.md`) MUST NOT include a measurement the person lists in its counts, and
MUST leave out the counts of a layer the person lists, `body`, `preferences` or `history`, rather
than give them as zero: a zero would say that nothing of the kind was used.

A report MUST NOT include a caveat, a note or a suggestion that speaks about a layer the person
lists, and MUST leave out of its alternatives a size set aside for a reason that layer gives: with
its score, the size would say that it was set aside. The answer is computed the same. From
`explained` up the reference implementation says in `caveats` that part of the reasoning was kept
back at the person's request; at `result_only` it says nothing, since that would only tell the
verifier that the person keeps something to themselves.

When the person lists `preferences` or `history`, a report MUST NOT include the band of any zone,
at any level: taken out only where it moved, it would say where it moved.

The intended architecture is that the *computation happens where the profile lives* — a vault, a
wallet, or a fit provider the person chose — and only the result travels. A retailer does not need
a chest measurement to sell a shirt. It needs a size.

## The arithmetic leak

At `explained`, numeric ease values MUST be omitted. Garment measurements are public. Ease is
garment minus body. Publishing both hands over the body measurement to anyone willing to subtract,
which defeats the entire point of not sending it. The reference implementation enforces this in
serialisation rather than trusting callers, refuses a level it does not recognise instead of
guessing what was meant, and there is a test for each.

The same subtraction reads more than the body. The band a zone was judged against
(`intended_ease_cm`) is the garment's own, moved by the person's preferences and by what their
history taught, and the verifier knows the band it published. At `scoped`, which gives the
measurements a garment needs and nothing about preferences or history, the band MUST be omitted;
it may travel at `full`, except as `never_share` says.

Put together, by level: at `result_only` a report MUST NOT carry `explanation`, `alternatives`,
`based_on` or `improve_by`, which describe the profile rather than the answer: the same counts and
suggestions reaching several verifiers would let them recognise one person. At `explained`, as
above, no explanation line carries `ease_cm` or `intended_ease_cm`; at `scoped`, none carries
`intended_ease_cm`. The schema of this version checks none of it, so a report that breaks these
rules still validates, and validation is no proof that a report is safe to send.

Without numbers is not without information. At `explained`, a judgement read against the garment's
published measurements and the band it declares places the body measurement inside that band: "as
cut" at the collar of a shirt whose band is 1 to 2.5 cm places a neck within a centimetre and a
half. A person who wants a measurement kept entirely lists it in `never_share`, which takes its
judgement out as well.

## Regulatory notes

Body measurements are generally **not** special-category biometric data under GDPR Article 9, which
requires processing specifically aimed at uniquely identifying a person. Photographs and 3D scans
processed for identification can be. A profile assembled from tape measurements and purchase
history sits in ordinary personal data; one assembled from body scans may not.

Implementers relying on this distinction should get their own legal advice. It is a real
distinction, not a safe harbour, and it changes with how the data is captured.

Two provisions worth building around rather than complying with after the fact:

- **Article 20, portability.** Purchase and return history held by a retailer is the person's data
  and is exportable on request. This is the legal lever that makes the history layer possible
  without any retailer's cooperation.
- **Article 22 and automated decisions.** Marginal here, but a system that assigns sizes and hides
  its reasoning is on the wrong side of the argument. Explanations are also good engineering.

## Deletion

`import_ref` exists so that a person can delete everything that came from one source in one action.
Implementations SHOULD support this, and SHOULD make profile export trivial: a format nobody can
leave is not portable, whatever the schema says.
