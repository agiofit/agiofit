# Privacy and disclosure

Privacy here is a design constraint, not a paragraph at the end of a document. It is also the only
durable reason a person would prefer this to a vendor profile.

## The default is not to share the profile

Four levels, declared in the match report itself:

| Level | The verifier receives |
|---|---|
| `result_only` | A size, a confidence and the caveats on the answer. Nothing else. |
| `explained` | Plus reasoning per zone — "tight at the shoulders" — with no numbers, and more. |
| `scoped` | Plus each zone's ease, from which the body measurements this garment needs follow. |
| `full` | Plus the band of each zone. Should be rare, and a consumer SHOULD justify it. |

At `explained` the "more" is the alternatives, what the answer rests on (`based_on`) and what would
improve it (`improve_by`). No level carries the profile itself: `full` is all that a report holds.

When a request names no level, the level asked is taken to be the one the person declared in
`disclosure_defaults.default_level`, and `result_only` when the profile declares none. The
person's level is a default, not a ceiling: a request may name another level, and the level a
report is serialised at is the lower of the level asked and the level the person authorised
(`AC3`, below).

A measurement the person lists in `disclosure_defaults.never_share` MUST NOT reach a report at
any level, as a number, as a per-zone judgement or by name: a judgement read against the
garment's public measurements narrows the body measurement to the width of the ease band, and a
name, even in a suggestion to take the measurement again, says that it exists and how it was
taken. Listing the `body` layer withholds every zone and every name. The measurement still
counts towards the answer, because the computation happens where the profile lives; what the
list governs is what leaves it. The reference implementation leaves such a zone out of the
explanation altogether and, from `explained` up, says in `caveats` that some zones were
withheld at the person's request.

`based_on` (`03-matching.md`) MUST NOT include a measurement the person lists in its counts, and
MUST leave out the counts of a layer the person lists, `body`, `preferences` or `history`, rather
than give them as zero: a zero would say that nothing of the kind was used.

A report MUST NOT include a caveat, a note or a suggestion that speaks about a layer the person
lists, and MUST leave out of its alternatives a size set aside for a reason that layer gives: with
its score, the size would say that it was set aside. The answer is computed the same. From
`explained` up the reference implementation says in `caveats` that part of the reasoning was kept
back at the person's request; at `result_only` it says nothing, since that would only tell the
verifier that the person keeps something to themselves.

When the person lists `preferences` or `history`, a report MUST NOT include the band of any zone,
at any level: taken out only where it moved, it would say where it moved.

## Custody and processing

Two things are kept apart here. *Custody* is where a Fit Profile is kept and who can read it.
*Processing* is where a match is computed and what crosses the edge of the person's device for it
to be computed.

The principle is person-controlled custody: the profile stays under the control of the person it
describes. They decide where it is kept, which application reads it, and when a match may be asked
of it. A *vault* is whatever holds a profile and answers for it on those terms. This specification
says what a vault guarantees, not what it is built with, and depends on no product.

The model this specification is written for is the *local vault*: the profile is kept on a device
the person controls and the match is computed there. A *hosted vault*, where a service the person
chose keeps the profile readable or computes the match, is an alternative some people will want.
It is never required, and it is held to more.

A retailer does not need a chest measurement to sell a shirt. It needs a size.

### Custody

**CU1.** The profile is a Fit Profile document as this specification defines it. A vault MUST be
able to give the person the whole profile in that form at any time, and MUST NOT make reading it
depend on a format, a key or an account that only the vault's maker controls.

**CU2.** A vault MUST let the person delete the profile, and SHOULD let them delete everything
that came from one source in one action (`import_ref`).

**CU3.** A vault MUST NOT require the person to identify themselves to a verifier in order to be
answered.

### Access

**AC1.** A vault MUST NOT answer a Match Request the person has not authorised. Authorisation may
be given once for a verifier, or request by request; how it is asked is the vault's business, that
it was given is not.

**AC2.** A vault MAY decline any request, and MAY answer at a lower level than the one asked.
Declining is sending no report. A vault MUST NOT accompany it with anything that describes the
profile, the person or the reason, and a verifier MUST NOT treat the absence of a report as an
error, or as evidence of anything about the person.

**AC3.** The four levels are ordered: `result_only`, `explained`, `scoped`, `full`, each carrying
more than the one before. For one request:

- the *default* level is the one in the profile's `disclosure_defaults.default_level`, and
  `result_only` when the profile declares none;
- the *requested* level is the one the Match Request names, and the default level when it names
  none;
- the *authorised* level is the one the person granted for this request, and the default level
  when they authorised the request without naming one.

A vault MUST serialise the report at the lower of the requested and the authorised level, and at
no other. A report is therefore never above what the verifier asked, never above what the person
granted, and, when the person grants less than was asked, at what they granted.

**AC4.** Before asking the person to authorise a request, a vault MUST show them who is asking,
the level asked, and, for `full`, the justification the request carries (`03-matching.md`).

### Local processing

**LP1.** A Match Report MUST be computable on a device the person controls, from the Fit Profile,
the Cut Profile and the Match Request alone. Nothing in this specification depends on a service,
and a vault that runs entirely on the person's device MUST be able to conform to all of it.

**LP2.** A local vault MUST NOT send the profile, or any value taken from it other than the Match
Report, off the device. A copy kept elsewhere for backup or synchronisation does not change this,
provided the party keeping it cannot read it.

**LP3.** Obtaining the Cut Profile MUST NOT tell anyone but its publisher or the verifier which
garment the person is looking at: a vault SHOULD take the Cut Profile from the verifier that
asked, or from the origin that publishes it.

### Verifiers

**VE1.** A verifier that takes Match Reports MUST treat a valid report the same whichever kind of
vault produced it, and MUST NOT require, as a condition of taking one, that the profile be kept or
the match computed by a service, its own or anyone else's. This is about the document and where it
was computed. It does not oblige a verifier to act on the size a report names, to sell, or to
change its terms because of one: what it does with an answer is its own business.

**VE2.** A verifier MUST NOT ask for the profile itself, or for any measurement, as an alternative
to a Match Request.

### Disclosure

**DI1.** What leaves a vault in answer to a Match Request is one Match Report, serialised at one
level, and nothing else. Everything this document requires of a report holds for it, `never_share`
included.

**DI2.** A report MUST NOT carry an identifier of the profile or of the person, or any value that
is the same across verifiers and would let them recognise one person.

### Hosted vaults

A hosted vault is one where a party other than the person can read the profile, or computes the
match, on equipment the person does not control. Everything above binds it, and so does this.

**HV1.** A profile MUST NOT be moved to a hosted vault without the person's explicit choice, made
knowing who operates it. It is never a default, and never a condition (`VE1`).

**HV2.** The operator MUST use the profile, and the reports it produces, only to answer requests
the person authorised and to keep the vault running: storing it, securing it, backing it up. Any
other use, and any passing on to another party, needs the person's separate and explicit choice,
not one bundled with choosing the vault.

**HV3.** `CU1` and `CU2` hold for a hosted vault as follows.

- What the person takes away is the whole profile.
- From the moment the person deletes the profile, the vault MUST NOT answer any request for it,
  and MUST remove it from the store it serves from and from its replicas without delay.
- Backups need not be rewritten. The operator MUST state, before the person chooses the vault, how
  long a backup is kept, MUST NOT read a deleted profile out of one, and MUST delete it again
  before serving from a backup it had to restore.
- Copies made to compute a match MUST NOT be kept once the report is produced, and logs MUST NOT
  hold profile values or reports.

**HV4.** A vault operated by the verifier of a request, or by a party acting for it, does not give
person-controlled custody with respect to that verifier: the profile is already with the party the
disclosure levels exist to keep it from. Such a vault MUST tell the person so before they choose
it, and MUST NOT be described as conformant to this section for requests from that verifier.

### What can be checked, and how

A specification cannot see inside an application, so these requirements are written as behaviour
that shows from outside. Some of it a test can run; the rest someone has to look at.

| Requirement | What shows |
|---|---|
| `LP1`, `LP2` | With the network recorded during a match, nothing sent out holds a value of the profile that is not in the report. The reference implementation has a test: matching runs with the network taken away. |
| `DI1`, `DI2`, `CU3` | What comes back is one document that validates as a Match Report, with no identifier of the profile or the person in it. The reference implementation has a test for each. |
| `CU1` | The profile the vault hands back validates as a Fit Profile and holds what was put in. A match leaves it unchanged, which the reference implementation tests. |
| `AC1`, `AC2`, `AC3` | Without authorisation no report comes back, and nothing else does; with it, the report is at the lower of the level asked and the level granted. |
| `AC4`, `CU2`, `LP3` | Shown by the application itself: what the person sees before authorising, that a deleted profile is gone, where the Cut Profile was fetched from. |
| `VE1`, `VE2` | Shown by the verifier: the same treatment for a report from any vault, and no request for a profile or a measurement. |
| `HV1` to `HV4` | From outside: a deleted profile is no longer answered for, and the time a backup is kept is stated before the person chooses. That a backup really expires is the operator's statement, which it answers for; no test shows it. |

A vault whose code cannot be read can still be held to the first five rows.

## The arithmetic leak

At `explained`, numeric ease values MUST be omitted. Garment measurements are public. Ease is
garment minus body. Publishing both hands over the body measurement to anyone willing to subtract,
which defeats the entire point of not sending it. The reference implementation enforces this in
serialisation rather than trusting callers, refuses a level it does not recognise instead of
guessing what was meant, and there is a test for each.

The same subtraction reads more than the body. The band a zone was judged against
(`intended_ease_cm`) is the garment's own, moved by the person's preferences and by what their
history taught, and the verifier knows the band it published. At `scoped`, which gives the
measurements a garment needs and nothing about preferences or history, the band MUST be omitted;
it may travel at `full`, except as `never_share` says.

Put together, by level: at `result_only` a report MUST NOT carry `explanation`, `alternatives`,
`based_on` or `improve_by`, which describe the profile rather than the answer: the same counts and
suggestions reaching several verifiers would let them recognise one person. At `explained`, as
above, no explanation line carries `ease_cm` or `intended_ease_cm`; at `scoped`, none carries
`intended_ease_cm`. The schema of this version checks none of it, so a report that breaks these
rules still validates, and validation is no proof that a report is safe to send.

Without numbers is not without information. At `explained`, a judgement read against the garment's
published measurements and the band it declares places the body measurement inside that band: "as
cut" at the collar of a shirt whose band is 1 to 2.5 cm places a neck within a centimetre and a
half. A person who wants a measurement kept entirely lists it in `never_share`, which takes its
judgement out as well.

## Regulatory notes

Body measurements are generally **not** special-category biometric data under GDPR Article 9, which
requires processing specifically aimed at uniquely identifying a person. Photographs and 3D scans
processed for identification can be. A profile assembled from tape measurements and purchase
history sits in ordinary personal data; one assembled from body scans may not.

Implementers relying on this distinction should get their own legal advice. It is a real
distinction, not a safe harbour, and it changes with how the data is captured.

Two provisions worth building around rather than complying with after the fact:

- **Article 20, portability.** Purchase and return history held by a retailer is the person's data
  and is exportable on request. This is the legal lever that makes the history layer possible
  without any retailer's cooperation.
- **Article 22 and automated decisions.** Marginal here, but a system that assigns sizes and hides
  its reasoning is on the wrong side of the argument. Explanations are also good engineering.

## Deletion

`import_ref` exists so that a person can delete everything that came from one source in one action.
Implementations SHOULD support this, and SHOULD make profile export trivial: a format nobody can
leave is not portable, whatever the schema says.
