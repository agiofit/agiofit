# Privacy and disclosure

Privacy here is a design constraint, not a paragraph at the end of a document. It is also the only
durable reason a person would prefer this to a vendor profile.

## The default is not to share the profile

Four levels, declared in the match report itself:

| Level | The verifier receives |
|---|---|
| `result_only` | A size and a confidence. Nothing else. |
| `explained` | Plus qualitative per-zone reasoning — "tight at the shoulders" — with no numbers. |
| `scoped` | Plus the specific measurements needed for this garment. |
| `full` | The whole profile. Should be rare, and a consumer SHOULD justify it. |

The intended architecture is that the *computation happens where the profile lives* — a vault, a
wallet, or a fit provider the person chose — and only the result travels. A retailer does not need
a chest measurement to sell a shirt. It needs a size.

## The arithmetic leak

At `explained`, numeric ease values MUST be omitted. Garment measurements are public. Ease is
garment minus body. Publishing both hands over the body measurement to anyone willing to subtract,
which defeats the entire point of not sending it. The reference implementation enforces this in
serialisation rather than trusting callers, and there is a test for it.

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
