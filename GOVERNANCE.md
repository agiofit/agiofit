# Governance

## Today

A personal project, maintained by one person. Decisions are made by the maintainer, in the open,
with reasoning written down. Pretending otherwise at this stage would be theatre.

## Intended trajectory

The specification should not stay under one person's control if it gets adopted, because nobody
sensible builds a business on a schema that one individual can change unilaterally.

Trigger for moving to a neutral home: **two independent implementations, at least one of them not
by the maintainer.** The likely destination is a W3C Community Group — open to anyone, free, and it
brings an IPR framework that a personal repository cannot offer.

Until then the commitment is narrow and concrete: schema `$id` URIs will remain resolvable, and
breaking changes will bump the major version rather than mutate a published schema in place.

## Contributions and IP

Contributions are accepted under the repository licences (CC BY 4.0 for the specification, Apache
2.0 for the code). The Apache patent grant is the relevant part: size recommendation is a
patent-dense field, and contributors granting patent rights to what they contribute is the point.

A DCO sign-off (`git commit -s`) is required. No CLA — a CLA on a personal project asks
contributors for more trust than a personal project has earned.

## Decisions that will not be made unilaterally

- Changing the licences.
- Adding a field that requires body data to leave the person's control by default.
- Transferring the project to a commercial entity.
