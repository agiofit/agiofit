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

## Identifying fields

None of these affect how a garment is compared against a body. They exist so that two documents
about the same garment can be recognised as such, and so that a person reading the file can tell
what it describes.

**`brand`.** The producer's name, as free text. A consumer that learns a size offset from a
person's history keys it on this string, so two spellings of the same name are two different
brands to it. There is no registry and no normalisation. This is a limitation, not a design.

**`style_id`.** The producer's own identifier for the model. Two garments sharing it are the same
design in the same cut, which is stronger evidence of comparability than two garments merely
sharing a brand.

**`style_name`.** Human-readable. For people, not for matching.

**`gtin`.** The commercial barcode. Not used for matching; present as the link to retail systems
for consumers that have one. The schema does not verify the check digit, so a malformed value is
accepted.

## Cut and shape

`cut` is descriptive. It is there so a person reading the file gets a quick sense of the
garment, and a consumer should not compute with it.

Three reasons, and the first is the one that matters. Fitted is not a property of a garment;
it is a relation between a garment and a body. The same shirt is very fitted on one person and
oversized on another. Someone measuring their own garment and reporting how it sits on them is
describing themselves, not the item, which is both unreliable for anyone else and a small leak
of body information into a public document about a garment. Only a party that knows the design
intent can state it well.

Second, fit belongs to zones and `cut` is one value for a whole garment. A jacket cut close at
the waist and generous across the chest has no place on a single scale.

Third, the values measure one thing only, the amount of ease. Half the words the trade actually
uses describe shape rather than amount: boxy, tapered, cropped, straight, dropped shoulder.
Adding them to the enum would not help, because they are not points on the same axis.

Shape is already expressible, and better. A garment's shape is the profile of its ease across
zones, which is exactly what `intended_ease` carries: a boxy shirt is one that allows more ease
at the waist than at the chest, and that is legible in the numbers without anyone needing to
share a vocabulary. A brand wanting to say its garment is boxy should say it there.

What neither field expresses is where a seam sits. A dropped shoulder, a raised waist or the
shape of a sleeve head are positions, not amounts, and this version does not carry them.

## Provenance

`published_by` is required. It names who is making the claim, and nothing else. It is not a
quality score, and this specification deliberately assigns no weight to its values.

**`brand`.** The party that designs and sells the garment under its own name. Its numbers are
usually a design specification: what the garment is meant to be.

**`manufacturer`.** The party that produced it. Where production drifts from the specification,
the manufacturer knows the actual cut better than the brand does.

**`retailer`.** A party that sells the garment without having made it. Values are typically
copied from the brand, occasionally re-measured.

**`marketplace_seller`.** An individual or shop selling a specific garment, usually second-hand.
The numbers come from an item in hand.

**`community`.** Measured by someone with no stake in selling it, often for a shared catalogue.

**`measured_by_owner`.** Measured by the person who owns the garment.

These are not a ranking, and reading them as one is the most likely mistake. A brand
specification is a statement of intent; a measured garment is an observation. Each is better
than the other at a different question. A brand may publish numbers its production does not
hold to. A person with a tape measure reports what one garment actually is, but a Cut Profile
describes a model, and models vary between units by more than most people expect.

The reason no weight is given here is structural rather than cautious. Provenance is declared
once for a whole document, while reliability belongs to each measurement. Weighting the field
would weight the label on the file instead of the numbers inside it. A consumer is free to
weight it anyway, and should say so in its output.

**`verified`.** Self-asserted. Setting it to true claims that an independent check exists, which
`verification_method` should then describe. Nothing in this version prevents anyone from setting
it, so a consumer should read it as a claim and not as a fact. Provenance that can be checked
rather than claimed is deferred to a later version.

## Relationship to the Digital Product Passport

The European DPP under ESPR is the natural long-term carrier for this document: it is already
per-product, already regulated, and already going to exist. Its current scope is materials,
durability and circularity, and fit data is not obviously inside it.

Whether measurements fall within the DPP perimeter is an open question, not a settled one. This
specification therefore defines the document standalone and provides `provenance.dpp_id` as the
link, so that the two can converge later without either waiting for the other.

## Relationship to EN 13402

EN 13402 is the European labelling standard for garment sizes: a controlled vocabulary of body
dimensions, in centimetres, expressed as intervals the garment is designed for. It is the body
side of a label, not the garment side of a specification. It carries no finished measurements, no
intended ease, no grading, no stretch, no provenance — and its adoption is voluntary and, two
decades on, thin.

The two are complementary rather than competing. An EN 13402 label is, conceptually, the brand's
finished measurements minus its intended ease, already collapsed into a single body interval. This
specification keeps those two quantities separate, because the separation is what makes a
recommendation explainable and correctable. Matching by label interval alone is the size-chart
approach this project exists to replace; whether and how a label can serve as a degraded signal
for a garment that has no Cut Profile is left to a future version.
