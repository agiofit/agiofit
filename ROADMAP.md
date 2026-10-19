# Roadmap

## v0.1 — the data model (this release)

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

## v0.2 — the vault, by reference

Map the profile onto W3C Verifiable Credentials and OpenID4VCI. Define the shape of a
match request so the computation can happen inside the vault and only the report
leaves. Invent nothing that already exists.

**Done when** a profile can be held in an existing wallet implementation and a match report
returned without the profile ever leaving it.

## v0.3 — protocol extensions

Propose `catalog.cut_profile`, `wallet.fit_profile` and `fit.match_report` as namespaced
extensions to the agentic commerce protocols. Contingent on question 3 in `spec/05-open-questions.md`:
if UCP and ACP have no formal extension mechanism, this becomes a proposal to the standards rather
than a module over them, which is a slower and more political road.

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
