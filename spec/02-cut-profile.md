# Cut Profile

Schema: `schemas/cut-profile.schema.json`

A size chart says what a brand calls a size. This document says how the garment is cut. They are
not the same thing and only the second one is useful.

## Required fields, and why

**`measurement_method`.** Flat-laid measurements are half-circumferences. A consumer that compares
a flat-laid chest width of 56 cm against a body chest of 100 cm concludes the garment is 44 cm too
small. This is the single most common failure mode in the field, so the field is required and has
no default.

**`provenance.published_by`.** A profile measured by the brand on a production sample, one typed in
by a marketplace seller, and one crowdsourced by a community are all legitimate and all different.
Consumers SHOULD weight them differently and SHOULD surface the difference to the person.

**`sizes[].finished_measurements`.** Per size, not per style. Grading is where sizing goes wrong.

## Recommended fields

**`intended_ease`.** The gap the designer meant to leave, per zone, as a range. Without it a
consumer falls back on category defaults and MUST lower its confidence for having done so. This is
the field brands are most reluctant to publish and the one that most improves results — the same
finished chest measurement means a fitted shirt on one body and a relaxed one on another, and only
the brand knows which was intended.

**`fabric.stretch_pct`.** Comfortable extension, not extension to failure. Only comfortable
extension is usable for fit; the rest is how a garment gets ruined.

**`production_tolerance`.** Two garments of the same size are not the same object. A specification
that ignores this produces answers more precise than the physical world supports.

**`critical_zones`.** Where a mismatch cannot be tolerated or altered. Overrides category defaults.

## Relationship to the Digital Product Passport

The European DPP under ESPR is the natural long-term carrier for this document: it is already
per-product, already regulated, and already going to exist. Its current scope is materials,
durability and circularity, and fit data is not obviously inside it.

Whether measurements fall within the DPP perimeter is an open question, not a settled one. This
specification therefore defines the document standalone and provides `provenance.dpp_id` as the
link, so that the two can converge later without either waiting for the other.
