# Threat model

A portable profile is also a portable target. This document answers open question 7 far enough to
design v0.2: who attacks a fit profile, what they can infer, what the data model already blocks,
and what it honestly does not. It is a threat model of the *data model* — not a security audit of
any particular vault, wallet or transport, which are out of scope here as everywhere else in this
specification.

## The asset

The dangerous part of a Fit Profile is not today's measurements. It is the history. A time series
of body measurements, correction events and `kept_despite` records reads like a diary written in
centimetres: pregnancy, rapid weight change, illness, treatment, an eating disorder. The same
history layer this specification treats as its most valuable signal is also its most sensitive
content, and both facts have to be designed for at once.

A related legal note extends `04-privacy.md`: measurements captured by tape are ordinary personal
data, but *inferences drawn from their trajectory* can land in special categories — health,
pregnancy — regardless of how innocently each individual value was collected. Aggregation changes
the legal character of the data, not only the privacy risk.

## Adversaries

**The curious verifier.** A shop that receives match reports and wants more than a size. The
arithmetic leak is closed (`04-privacy.md`), but subtraction is not the only attack:

- *Triangulation by repeated queries.* A verifier that can ask for many match reports against
  crafted Cut Profiles can bisect its way toward the underlying measurements. Each answer is one
  bit; enough answers are a tape measure. No serialisation rule prevents this — only the vault's
  right to refuse can.
- *Metadata side channels, present today.* In the reference implementation, `result_only` output
  includes `based_on` and `improve_by`. A non-zero `brand_specific_history_signals` tells the
  verifier the person has bought this brand before. An `improve_by` entry naming `arm_length`
  reveals which measurements exist and how good they are. Neither is a body measurement; both are
  disclosures the level's name does not advertise. Coarsening or dropping these fields at
  `result_only` is an open design decision that MUST be resolved before v0.2 freezes the
  recommendation request shape.

**The vault operator.** Whoever runs the vault sees everything, always. No disclosure level
protects against the party doing the computing. This is open question 1 viewed from the security
side, and it is the strongest argument for vaults the person controls directly. The data model's
only contribution is to keep profiles trivially exportable, so that leaving a bad operator is an
afternoon, not a hostage negotiation.

**The report aggregator.** Match reports are individually innocuous and collectively a trajectory.
A party that collects reports across shops and time — an analytics SDK, an advertising broker, a
marketplace — can reconstruct the trend the profile never disclosed. Consequence for v0.2: reports
MUST NOT carry identifiers that are stable across verifiers, and SHOULD NOT carry any identifier
the verifier does not need for correction handling.

**The person with the device.** A partner, parent or employer with access to the phone reads the
profile with no attack at all. This is the least technical adversary and the most common one.
Mitigation is almost entirely outside a data model's reach — device security, wallet
authentication — but the model can refuse to make it worse: nothing in the format should require
keeping history that the person wants deleted, and per-source deletion via `import_ref` exists
precisely so that removal is one action, not an audit.

**The over-permissioned consumer.** `full` disclosure exists for tailors and exceptional cases,
and every incentive pushes consumers to ask for it routinely — the same pressure that made "allow
all cookies" a reflex. The specification already says a consumer SHOULD justify `full`; v0.2 must
decide whether the request shape gives that requirement teeth, for instance by making the
justification a mandatory, displayable field of the request itself.

## What the model already blocks

Arithmetic loss at `result_only` and `explained`, enforced in serialisation and covered by a test.
Minimum disclosure as the default, declared in the report itself. Computation where the profile
lives, so custody never transfers for a size to come back. Provenance and confidence on every
value, so downstream systems cannot silently launder guesses into facts. Per-source deletion.

## What it does not block, stated plainly

Query-rate abuse: a data model has no opinion about how often it is asked, so triangulation
resistance depends entirely on vault policy that v0.2 has not yet defined. The vault operator
itself. Anyone with legitimate access to the device. Coercion — portability means handing the
profile over under pressure is easy, and a format cannot tell consent from duress. And signing
(open question 6) cuts both ways: a signature that proves a profile came from a scanner also makes
the stolen copy more valuable, because it is now authenticated.

## Requirements carried into v0.2

1. The `fit_recommendation` request shape MUST allow the vault to refuse or limit queries without
   breaking conformance; the protocol must not assume unlimited answers.
2. The contents of `based_on` and `improve_by` at `result_only` MUST be re-examined; history depth
   and measurement inventory are disclosures in their own right.
3. Reports MUST NOT be linkable across verifiers through their identifiers.
4. A `full` disclosure request SHOULD carry its justification as data, not as documentation.
