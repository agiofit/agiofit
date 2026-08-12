# Licensing

Two licences, following the split between `spec/` and `reference/`. The specification is the
product; the code is the proof that the specification is implementable. They are different kinds
of artefact and they need different instruments.

## Specification, schemas and examples — CC BY 4.0

The contents of `spec/`, `schemas/`, `examples/` and the Markdown documents at the repository root
are licensed under the Creative Commons Attribution 4.0 International Licence.

Full text: `LICENSE-SPEC`, taken verbatim from creativecommons.org.

Attribution is the only condition. A brand publishing Cut Profiles can copy, translate and
embed these schemas in its own documentation without asking anyone. That is the intended
behaviour, and it is why this is not BY-SA: a copyleft condition on the specification would make
it harder for a company to incorporate, and at this stage adoption matters more than reciprocity.

## Reference implementation — Apache 2.0

The contents of `reference/` are licensed under the Apache License, Version 2.0.

Full text: `LICENSE`, taken verbatim from apache.org. See also `NOTICE`.

Apache 2.0 is chosen over MIT for its express patent grant (Section 3). Size recommendation is a
patent-dense field, and two things follow from that grant:

- every contributor licenses the patent claims that read on what they contribute, so a
  contribution cannot later be used as the basis of a claim against adopters;
- anyone who starts patent litigation over this work loses their patent licence to it.

For an adopter's legal team, the difference between an implicit MIT grant and an explicit Apache
one is not cosmetic.

Publishing the specification openly is also intended as defensive prior art: what is published
with a verifiable date is harder for a third party to patent afterwards.

## Contributions

Contributions are accepted under these licences, with a DCO sign-off (`git commit -s`) and no CLA.

The part that matters — the patent grant on contributions — already comes from Apache 2.0 itself
(Section 5). A CLA would only add a transfer of rights to the maintainer, which is the kind of
asymmetry this project argues against elsewhere. A CLA on a personal project asks contributors for
more trust than a personal project has earned.

Changing these licences is listed in `GOVERNANCE.md` as a decision that will not be made
unilaterally, alongside transferring the project to a commercial entity.

## Licence texts are not edited by hand

`LICENSE` and `LICENSE-SPEC` contain the canonical texts, byte for byte, with no preamble and no
Markdown wrapping. Automated licence scanners match on the text itself; a file with a preface or a
code fence is not recognised, and a repository whose entire argument is clarity about rights
should not report as `license: unknown`.

To refresh them from the canonical sources:

```sh
curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE
curl -fsSL https://creativecommons.org/licenses/by/4.0/legalcode.txt -o LICENSE-SPEC
```

## Not legal advice

None of this has been reviewed by a lawyer. It should be, before the first release that anyone is
expected to rely on.
