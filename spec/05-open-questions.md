# Open questions

Listed rather than hidden. Contributions on any of these are more useful than schema bikeshedding.

1. **Who runs a fit vault, and why?** What a vault has to guarantee is now stated
   (`04-privacy.md`, Custody and processing), and the model it is written for needs no one to run
   anything: a profile kept and matched on the person's own device. What stays open is who will
   build a vault people want to use, and what a hosted one lives on if not the profiles it holds.
   Candidates for the latter: a co-operative funded by retailers who benefit from lower returns, a
   wallet provider for whom fit is one credential among many, or a pure consumer subscription. None
   is proven, and the specification does not depend on the answer.

2. **Is fit inside the Digital Product Passport perimeter?** The JRC study on textile DPP content
   needs reading before assuming it is. If measurements are excluded, the Cut Profile stays
   a voluntary publication and catalogue coverage becomes the binding constraint.

3. **Can UCP and ACP carry namespaced extensions at all?** If they can, this becomes a module. If
   they cannot, it stays an out-of-band API and the ambition changes shape. Answered in August
   2026, unevenly. UCP has a formal extension mechanism that needs no maintainer's approval,
   provided the schema is served from the extension's own domain, here `agiofit.org`. ACP has an
   extensions framework too, still a draft. The question stays listed until the ACP side is
   stable.

4. **How do you bootstrap cut profiles?** Roughly: second-hand marketplaces where sellers
   already measure by hand, brands with return-rate pain and no vendor budget, and community
   measurement for everything else. Whether community data is trustworthy enough is untested.

5. **Footwear.** Structurally different — length, width, volume, last shape — and served by mature
   3D scanning inside retailer ecosystems. Probably a separate profile rather than a category.

6. **Verifiable credentials: worth it?** Signing a fit profile proves it came from a scanner rather
   than from a person's optimism. It also adds a great deal of machinery. A survey of wallets in
   October 2026 sharpened the doubt: a credential is signed so that a verifier can trust its
   issuer, and a shop has no need to verify a size, since a person who misstates theirs harms only
   themselves; and no wallet computes, so one could carry a profile but not answer for it. v0.2
   therefore does not depend on credentials (`ROADMAP.md`). The question stays open for the case
   it started from: a fit provider that wants to know a measurement came from an instrument.

7. **Anti-abuse.** A portable profile is also a portable target. Inference of health conditions,
   pregnancy or weight change from measurement history is possible and needs thinking about before
   scale, not after. A first threat model is in `06-threat-model.md`. One countermeasure is now in
   the data model: a profile keeps only the latest value of each measurement (`01-fit-profile.md`).
   What remains open is which others belong there.

8. **Assessment words for length zones.** `snug` and `roomy` are girth words. For a sleeve or an
   inseam the honest words are *short* and *long*, and collapsing both onto one scale loses the
   direction of an error a tailor could actually fix. A per-dimension vocabulary is a candidate
   for a later version, to be weighed against keeping the normative enum as small as possible.

9. **An identifier for history entries.** Entries carry none, so the same event written twice
   cannot be told from two that look alike, and a wrong entry can be corrected only where it is,
   not by sending its replacement. An identifier would settle both, and would also be one more
   handle for following a person across systems, if it were ever taken from an order number. A
   candidate for a later version, to be designed with that in mind.

10. **Bust and underbust.** A chest taken at its fullest part serves shirts and tops, for every
    body. A fitted dress, a bodice or a bra is decided by the bust and the underbust together, and
    the relation between the two is what a single girth cannot express. This version names neither
    on the body, and the `bust` zone has no mapping. Naming them, and saying how a garment is
    compared against two body measurements at once, is left to a later version, to be checked with
    people who cut such garments.

11. **The names of body measurements are still an open list.** A Cut Profile takes its
    measurement names from a closed list; a Fit Profile accepts any lowercase name, and
    `01-fit-profile.md` only says which ones a garment can be compared against today. Closing the
    list depends on question 10, and it will make some profiles that are valid now invalid. v0.2
    leaves it open on purpose, and a later version will close it and say so in `07-changes.md`.
