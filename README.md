# Agio Fit — an open, portable fit profile

[![CI](https://github.com/agiofit/agiofit/actions/workflows/ci.yml/badge.svg)](https://github.com/agiofit/agiofit/actions/workflows/ci.yml)

> **Status: v0.1 draft.** Nothing here is stable. Breaking changes are expected until v1.0.

## The problem

Size recommendation already works — the market has proven that much. What every working
implementation shares is where the profile lives: with the vendor or the retailer. You rebuild it,
implicitly, at every shop you visit, and you never own it. This project does not attack
recommendation quality; it attacks the profile's address.

There is also an asymmetry hiding in plain sight: to tell you a size, today's services want your
measurements. A shop does not need your chest circumference to sell you a shirt — it needs a size.
This model is built so the computation can happen where the profile lives and only the result
travels, and its disclosure rules are enforced in serialisation, not by goodwill.

Meanwhile the agentic commerce protocols (UCP, ACP, A2UI) are standardising catalogue, checkout
and interface, and none of them has a place to put fit. If that stays true, the assistant that
buys clothes on your behalf will be guessing your size from nothing — and the cost of guessing is
familiar to anyone who has ordered three sizes to keep one.

## What this project is

An open data model for a **portable fit profile**, plus the garment-side counterpart it has to be
matched against, plus a reference implementation that reads the two and produces an *explained*,
correctable answer.

Three artefacts, that's all:

| Artefact | File | What it describes |
|---|---|---|
| Fit Profile | `schemas/fit-profile.schema.json` | Body measurements, fit preferences, and real wear history — each value carrying its source and confidence |
| Cut Profile | `schemas/cut-profile.schema.json` | Finished garment measurements, intended ease, stretch, production tolerance, and who published it |
| Match Report | `schemas/match-report.schema.json` | The output: a size, alternatives, per-zone reasoning, and an honest confidence |

## What this project is **not** (v0.1)

- **Not an identity system.** The profile is designed to live in a vault the person chooses. How
  that vault authenticates, stores and shares is deferred to v0.2, where it maps onto W3C
  Verifiable Credentials and OpenID4VCI rather than inventing anything.
- **Not a body-scanning technology.** Measurements can come from a tape, a scan, an import, or an
  inference. The schema records *which*, and does not care how you got there.
- **Not a protocol.** v0.3 proposes these as namespaced extensions to existing agentic commerce
  protocols. Until then this is a data model that works perfectly well over a plain HTTP API.
- **Not a size chart aggregator.** Those exist and they are the wrong abstraction: they describe
  what a brand calls a size, not how a garment is actually cut.

## Design commitments

1. **Every value declares its provenance.** A measurement taken with a tape, one typed in from
   memory, and one inferred from three returns are not the same fact, and the schema refuses to
   let them look the same. Same on the garment side: a profile published by the brand, by a
   marketplace seller, or by the community is marked as such.
2. **Cold start is a first-class case.** A profile with two declared preferences and no
   measurements must still produce something, with a confidence that says so out loud.
3. **The answer is explained and correctable.** "Take the 42" is not the deliverable.
   "The 42 is right at the chest, tight across the shoulders by about 1 cm, and you have kept two
   jackets in the past that were tight in the same place" is the deliverable.
4. **History is recorded as outcomes, not intentions.** What you kept, what you returned — and,
   through `kept_despite`, what was imperfect on a garment you kept anyway. No other system holds
   that signal in portable form.
5. **Minimum disclosure by default.** Sharing a profile is the exception. Sharing only the result
   of a computation is the norm, and the schema has a `disclosure_level` so the difference is
   explicit rather than a matter of good intentions.

## Quickstart

```bash
cd reference
pip install -e .
python -m agiofit.cli ../examples/profile-mature.json ../examples/cut-shirt.json
```

Or from Python:

```python
from agiofit import load_fit_profile, load_cut_profile, recommend

profile = load_fit_profile("examples/profile-mature.json")
garment = load_cut_profile("examples/cut-shirt.json")
report = recommend(profile, garment)

print(report.recommended_size, report.confidence)
for line in report.explanation:
    print(f"  {line.zone}: {line.assessment} (ease {line.ease_cm:+.1f} cm)")
```

## Repository layout

```
spec/        the normative prose — read 00-overview.md first
schemas/     JSON Schema 2020-12 definitions
examples/    valid documents, including a deliberately cold-start profile
reference/   Python reference implementation and tests
```

## Licensing

- Specification, schemas and examples: **CC BY 4.0** (`LICENSE-SPEC`)
- Reference implementation: **Apache License 2.0** (`LICENSE`, `NOTICE`)

Apache 2.0 is chosen deliberately: size recommendation is a patent-dense field, and the express
patent grant matters more here than it would elsewhere. Publishing the specification openly is
also intended as defensive prior art. This is not legal advice, and the licensing should be
reviewed by a lawyer before the first public release.

`LICENSING.md` explains both choices in full.

## Governance

See `GOVERNANCE.md`. Short version: a personal project today, with a stated intention to move to a
neutral home (a W3C Community Group is the likely candidate) once there is more than one
implementer.
