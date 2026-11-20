# Roadmap

## v0.1 — the data model

Fit Profile, Cut Profile, Match Report, plus a reference implementation and
tests. No vault, no protocol, no identity. Ships as a draft, breaks freely.

**Done when** someone other than the author has measured a real garment and produced a valid
Cut Profile from it, and that document, run against a profile supplied by the author, yields an
answer of the shape this specification requires: a size, a confidence, a per-zone explanation, and
a correction path.

The tester supplies a garment, never a body: nothing in this test asks a stranger for their own
measurements. And "sensible" is not the bar, because the arithmetic is explicitly not normative —
the shape of the answer is what has to hold.

**Not done if** two people measuring the same garment disagree by more than a production
tolerance, which would mean the measuring instructions are not enough; if the tester cannot finish
without asking the author a question, since every such question is a missing line in the tool; or
if the document is valid but the answer carries a caveat about something the builder should have
asked for and did not.

**Status (November 2026): not met.** No one other than the author has yet produced a Cut Profile
from a real garment. v0.2 is published without waiting for it, because it changes the Cut Profile
format and a first tester should not be handed a format that is about to break. The criterion
stands as written, and is now to be met with a v0.2 document.

## v0.2 — custody the person controls (this release)

Say what a vault has to guarantee, whoever builds it and wherever it runs: where the profile is
kept, who may ask it for a match, where the match is computed, and what leaves. Define the Match
Request, the document a verifier sends to ask for a report. Invent nothing that already exists.

**Done when** all of this holds:

1. `04-privacy.md` states custody and local processing as requirements an implementation can be
   checked against, with what a hosted vault owes on top.
2. The Match Request has a schema, prose and an example; the three schemas of v0.1 carry the
   corrections listed in `07-changes.md`; and all four carry the identifiers of this version.
3. The reference implementation shows the whole path on one machine with no network: a profile in
   a file the person keeps, a request in that shape, an authorisation given to it as input, and a
   report at the lower of the level asked and the level authorised.
4. Tests show that matching uses no network, that nothing but the report leaves, that no report
   is given without authorisation or above the level granted, and that a request for `full`
   without a justification is declined.

**Not done if** any requirement of this version can be met only by a service, or if a vault that
runs entirely on the person's device could not conform to all of it.

**Status (November 2026): met.** Released as v0.2.0 on 15 November 2026. The four points
above hold on `main`, and no requirement of this version needs a service.

**Why this changed (November 2026).** The criterion used to read "a profile can be held in an
existing wallet implementation and a match report returned without the profile ever leaving it".
A survey of the wallets available in October 2026 found that the open ones can hold a document
that is not an identity credential, and that none of them computes: a wallet presents a
credential, whole or field by field, and a match report is neither. More to the point, a wallet
exists so that a verifier can trust what an issuer signed, and a shop has no need to verify a
size: a person who misstates theirs harms only themselves. The requirement was never the wallet.
It was that the profile stays with the person and the match is computed where they are, and the
criterion now says that.

The specification depends on no wallet, vault or vendor, and nothing in this roadmap is an
application this project has to ship. The command line tool is a reference for checking the
specification, not what a person is meant to use. Mapping a profile onto W3C Verifiable
Credentials remains possible and may be documented as one way of carrying a profile; it is not
part of this criterion (question 6 in `spec/05-open-questions.md`).

## v0.3 — protocol extensions

Propose `catalog.cut_profile`, `fit.fit_profile` and `fit.match_report` as namespaced extensions
to the agentic commerce protocols. Question 3 in `spec/05-open-questions.md` has an answer: UCP
has a formal extension mechanism that needs no maintainer's approval, so on UCP this can be a
module over the protocol; ACP has one too, still a draft, and nothing is proposed there until it
is stable.

## v0.4 — the importer

A tool that ingests GDPR Article 20 data exports from major retailers and normalises purchase and
return history into the history layer.

This is arguably the most useful thing in the whole roadmap and does not depend on a single brand
adopting anything. It should probably be pulled forward if v0.1 gets any traction at all.

---

## Adoption, in order of plausibility

1. **Second-hand marketplaces.** Sellers already type measurements in by hand, fit uncertainty is
   at its highest, and no incumbent vendor serves them. Best fit for the schema, least resistance.
2. **Independent brands** with return-rate pain and no budget for a size-recommendation vendor.
3. **Sizing outside the standard range** — tall, petite, plus. Communities that already exchange
   measurements manually because nothing else works for them.
4. **Large retailers.** Last, and only if a standard emerges around them. They have vendors, and a
   portable profile makes their customers portable too. Do not build the roadmap around them.

## Non-goals

Becoming a size-recommendation vendor. Building a body-scanning app. Competing with the
established size-recommendation platforms on model quality — the argument here is ownership and
portability, and it is lost the moment this turns into another silo with better manners.
