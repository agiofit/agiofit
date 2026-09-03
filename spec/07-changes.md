# Changes between versions

This file answers one question: you hold a document written for an earlier version, what do you
have to do about it.

It lists only changes that make a previously valid document invalid. New optional fields are not
listed, because nothing needs to be done about them. For the full history of what changed and
when, read the commits.

## From 0.1 to 0.2

This version is still a draft. Nothing here is settled until it is merged.

### Measurement names are now a closed list

**What changed.** The keys of `finished_measurements` used to accept any lowercase word. They are
now the sixteen names defined in the specification, or a name beginning with `x_`.

**What breaks.** A profile carrying a measurement under any other key, `chest` or `torace` or
`chestWidth`, is no longer valid.

**What to do.** If the key was a spelling of a standard name, rename it. If the measurement has no
standard name, prefix it with `x_` and it stays valid. Do not drop the measurement: a consumer
that cannot use it will now say so, which is more useful than its absence.

### Zone names are now a closed list

**What changed.** `critical_zones` and the keys of `intended_ease` used to accept any lowercase
word. They now accept the sixteen zone names, or a name beginning with `x_`.

**What breaks.** `shoulder` instead of `shoulders` is no longer valid. So is an `intended_ease`
keyed by garment measurement names: the field is keyed by zone, so `chest` and not `chest_width`.

**What to do.** Correct the spelling, or move to the zone name. The two vocabularies are separate
on purpose: zones are where fit is judged, measurement names are what was physically measured.

### `measurement_method` has two values instead of four

**What changed.** `iso_8559` and `brand_defined` were removed. Only `flat_laid` and
`circumference` remain.

**What breaks.** A profile declaring either of the removed values is no longer valid.

**What to do.** If you know where the tape went, say so: it was either taken flat across the
garment or all the way round, and there is no third thing it could have been. If you do not know,
measure again. This is deliberately the only case in this file where the answer is to redo work
rather than to edit a file, and the reason is that no correct edit exists: a number that may or
may not be half a circumference cannot be used by anyone, and guessing between the two is the one
mistake this field exists to prevent.

`iso_8559` was removed because it is a standard for measuring bodies rather than garments. It
remains a legitimate value for the `method` of a body measurement in a Fit Profile, where it says
which definition was followed. `brand_defined` was removed because it named a method no reader
could ever learn, which made it indistinguishable from not knowing.
