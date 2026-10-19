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

A validator SHOULD check `format` as an assertion. JSON Schema 2020-12 reads it as an
annotation unless told otherwise, and a `profile_id` written as an email address then passes a
schema that asks for a UUID.

## Schema descriptions and this prose

The schemas carry `description` text for a reader who has only the schema at hand. Descriptions
are annotations and validate nothing. Where a schema's `description` and the prose of this
specification disagree, the prose governs. The rule covers descriptions only: whether a document
is valid is decided by the schema's validation keywords, exactly as written.

The v0.1 schemas are served at fixed `$id`s and are not edited in place, so a schema fetched today
is the same file as one fetched at launch. A description known to be wrong is listed here
instead, and corrected in the next version of the schemas.

### Errata to the v0.1 schema descriptions

1. **Cut Profile, `provenance.published_by`.** The description says consumers are expected to
   weight the values differently. No weight is assigned to them: the field names who makes the
   claim, and a consumer that weights it anyway should say so in its output (`02-cut-profile.md`,
   Provenance).
2. **Cut Profile, `cut`.** The description says the field is shared with `fit_preference` so the
   two can be compared directly. `cut` is descriptive, and a consumer should not compute with it
   (`02-cut-profile.md`, Cut and shape).
3. **Fit Profile, `disclosure_defaults`.** The description reads as a limit on how much a verifier
   may receive. `default_level` is a default, not a ceiling: a request may name another level, and
   whether a verifier may ever receive more is for the vault to decide (`04-privacy.md`).
4. **Fit Profile, `$defs.disclosure_level`.** The description says `scoped` adds the measurements
   the garment needs and `full` is the whole profile. `scoped` adds each zone's ease, `full` adds
   the band of each zone, and no level carries the profile itself (`04-privacy.md`).
5. **Fit Profile, `fit_preference.strength`.** The description says a stated dislike is not a hard
   constraint. A producer SHOULD write a constraint the person states at `strength` 1
   (`01-fit-profile.md`), and the reference implementation holds a declared preference at
   `strength` 1 as a constraint (`03-matching.md`).
6. **Match Report, `explanation`.** The description says numeric fields must be omitted at
   `explained`. At `result_only` there is no explanation, at `explained` no ease, at `scoped` no
   band, and no band at any level when the person lists `preferences` or `history` in
   `never_share` (`04-privacy.md`).
7. **Match Report, `based_on`.** The description says it lets a person see that an answer rests on
   one self-reported measurement. `based_on` carries counts and nothing else: it does not say where
   a measurement came from. It counts what the answer used, and it is not sent at `result_only`
   (`03-matching.md`, What an answer rests on; `04-privacy.md`).

## Reading order

1. `01-fit-profile.md` — the person's side
2. `02-cut-profile.md` — the garment's side
3. `03-matching.md` — how a match report is produced and explained
4. `04-privacy.md` — disclosure levels and what must never leave
5. `05-open-questions.md` — what is unresolved, honestly listed
6. `06-threat-model.md` — who attacks a portable profile, and what that means for v0.2
