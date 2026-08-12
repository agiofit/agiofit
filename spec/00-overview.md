# Agio Fit v0.1 — Overview

**Status:** draft. Not stable. Nothing here should be implemented in production yet.

## Scope

Three documents and the relationship between them:

- a **Fit Profile**, owned by a person and portable across retailers;
- a **Cut Profile**, published alongside a garment, describing how it is actually cut;
- a **Match Report**, the only artefact that normally needs to cross a trust boundary.

## Out of scope for v0.1

Authentication, storage, vault protocols, payment, catalogue, checkout, and body scanning. Where
those are needed, this specification points at existing standards rather than inventing new ones.

## Conformance

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

A **producer** is anything that writes a Fit Profile. A **consumer** is anything that
reads one to compute a match report. A **publisher** is whoever issues a Cut Profile.

Three requirements apply to every conformant implementation:

1. Every value in a Fit Profile MUST carry its `source`. A consumer that treats a
   self-reported waist and a scanned one as equivalent is not conformant.
2. Every Cut Profile MUST declare `measurement_method` and `provenance.published_by`.
3. Every Match Report MUST be correctable and MUST expose a confidence. A consumer that
   presents a size as final, without a route for the person to disagree, is not conformant.

## Reading order

1. `01-fit-profile.md` — the person's side
2. `02-cut-profile.md` — the garment's side
3. `03-matching.md` — how a match report is produced and explained
4. `04-privacy.md` — disclosure levels and what must never leave
5. `05-open-questions.md` — what is unresolved, honestly listed
