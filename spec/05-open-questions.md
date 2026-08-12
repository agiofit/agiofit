# Open questions

Listed rather than hidden. Contributions on any of these are more useful than schema bikeshedding.

1. **Who runs a fit vault, and why?** The architecture assumes an independent provider with an
   incentive to hold profiles and no incentive to exploit them. That business model is not obvious.
   Candidates: a co-operative funded by retailers who benefit from lower returns, a wallet provider
   for whom fit is one credential among many, or a pure consumer subscription. None is proven.

2. **Is fit inside the Digital Product Passport perimeter?** The JRC study on textile DPP content
   needs reading before assuming it is. If measurements are excluded, the Cut Profile stays
   a voluntary publication and catalogue coverage becomes the binding constraint.

3. **Can UCP and ACP carry namespaced extensions at all?** If they can, this becomes a module. If
   they cannot, it stays an out-of-band API and the ambition changes shape.

4. **How do you bootstrap cut profiles?** Roughly: second-hand marketplaces where sellers
   already measure by hand, brands with return-rate pain and no vendor budget, and community
   measurement for everything else. Whether community data is trustworthy enough is untested.

5. **Footwear.** Structurally different — length, width, volume, last shape — and served by mature
   3D scanning inside retailer ecosystems. Probably a separate profile rather than a category.

6. **Verifiable credentials: worth it?** Signing a fit profile proves it came from a scanner rather
   than from a person's optimism. It also adds a great deal of machinery. Deferred to v0.2 on the
   assumption that unsigned portability is worth more than signed friction.

7. **Anti-abuse.** A portable profile is also a portable target. Inference of health conditions,
   pregnancy or weight change from measurement history is possible and needs thinking about before
   scale, not after.

8. **Assessment words for length zones.** `snug` and `roomy` are girth words. For a sleeve or an
   inseam the honest words are *short* and *long*, and collapsing both onto one scale loses the
   direction of an error a tailor could actually fix. A per-dimension vocabulary is a candidate
   for v0.2, to be weighed against keeping the normative enum as small as possible.
