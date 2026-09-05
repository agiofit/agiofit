"""Match a Fit Profile against a Cut Profile.

The point of this module is not the arithmetic — any team can write a better scorer. The point is
the *shape* of the answer: a size, an honest confidence, a per-zone explanation, and a list of
things the person could add to make the next answer better.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from .mapping import (
    ZONE_MAPPINGS,
    PREFERENCE_SHIFT,
    STRETCH_CLASS_FRACTION,
    critical_zones,
    default_ease,
)

SCHEMA_VERSION = "0.1.0"
IN_TO_CM = 2.54


# --------------------------------------------------------------------------- loading


def _load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


load_fit_profile = _load
load_cut_profile = _load


def _cm(value: float, unit: str) -> float:
    return value * IN_TO_CM if unit == "in" else float(value)


# --------------------------------------------------------------------------- results


@dataclass
class ExplanationLine:
    zone: str
    assessment: str
    critical: bool = False
    ease_cm: float | None = None
    intended_ease_cm: tuple[float, float] | None = None
    note: str | None = None


@dataclass
class MatchReport:
    cut_profile_id: str
    recommended_size: str | None
    confidence: float
    disclosure_level: str = "explained"
    alternatives: list[dict] = field(default_factory=list)
    explanation: list[ExplanationLine] = field(default_factory=list)
    based_on: dict = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    improve_by: list[str] = field(default_factory=list)
    computed_at: str = ""
    correctable: bool = True

    def to_json(self) -> dict:
        """Serialise at the declared disclosure level.

        At ``result_only`` and ``explained`` the numeric ease values are stripped. Publishing both
        the ease and the garment measurement would let anyone subtract one from the other and
        recover the body measurement the person chose not to send.
        """
        out = {
            "schema_version": SCHEMA_VERSION,
            "cut_profile_id": self.cut_profile_id,
            "computed_at": self.computed_at,
            "disclosure_level": self.disclosure_level,
            "recommended_size": self.recommended_size,
            "confidence": round(self.confidence, 2),
            "correctable": True,
            "based_on": self.based_on,
            "caveats": self.caveats,
            "improve_by": self.improve_by,
        }
        if self.disclosure_level == "result_only":
            return out
        out["alternatives"] = self.alternatives
        lines = []
        for line in self.explanation:
            d = {k: v for k, v in asdict(line).items() if v is not None}
            if self.disclosure_level == "explained":
                d.pop("ease_cm", None)
                d.pop("intended_ease_cm", None)
            elif d.get("intended_ease_cm"):
                d["intended_ease_cm"] = list(d["intended_ease_cm"])
            lines.append(d)
        out["explanation"] = lines
        return out


# --------------------------------------------------------------------------- helpers


def _preference_shift(profile: dict, category: str, zone: str, linear: bool) -> float:
    shift = 0.0
    for pref in profile.get("preferences", []):
        if pref.get("category") != category:
            continue
        if pref.get("zone") not in (zone, "overall"):
            continue
        weight = float(pref.get("strength", 1.0)) * float(pref.get("confidence", 0.7))
        base = PREFERENCE_SHIFT.get(pref.get("preference", "regular"), 0.0)
        shift += base * weight * (0.25 if linear else 1.0)
    return shift


def _usable_stretch(garment: dict) -> float:
    fabric = garment.get("fabric") or {}
    pct = (fabric.get("stretch_pct") or {}).get("horizontal")
    if pct is not None:
        # Only half of the comfortable extension is treated as usable for fit.
        return float(pct) / 100.0 * 0.5
    return STRETCH_CLASS_FRACTION.get(fabric.get("stretch_class", "none"), 0.0)


RETURNED_FOR_SIZE = {
    "returned_too_small",
    "returned_too_large",
    "returned_wrong_shape",
    "exchanged_for_smaller",
    "exchanged_for_larger",
}


def _sizes_already_returned(profile: dict, garment: dict) -> set[str]:
    """Size labels this person sent back, for this exact Cut Profile.

    Keyed on cut_profile_id and nothing else: a brand or style match means a
    similar garment, which is a weaker claim and already handled by the learned
    offset. "kept" and "returned_other" are left out because neither says the
    size was wrong.
    """
    cut_id = garment.get("cut_profile_id")
    if not cut_id:
        return set()
    labels = set()
    for entry in profile.get("history", []):
        ref = entry.get("garment_ref", {})
        if ref.get("cut_profile_id") != cut_id:
            continue
        if entry.get("outcome") in RETURNED_FOR_SIZE:
            labels.add(ref.get("size_label"))
    return {l for l in labels if l}


def _history_offset(profile: dict, garment: dict) -> tuple[float, int, int]:
    """Learned bias from what actually happened, in cm of ease.

    Returns (offset_cm, total_relevant_outcomes, same_brand_outcomes). Same-brand outcomes count
    double, because sizing drift is overwhelmingly brand-specific.
    """
    category = garment.get("category")
    brand = garment.get("brand")
    direction = 0.0
    total = 0
    same_brand = 0
    for item in profile.get("history", []):
        ref = item.get("garment_ref", {})
        if ref.get("category") != category:
            continue
        weight = 1.0
        total += 1
        if brand and ref.get("brand") == brand:
            weight = 2.0
            same_brand += 1
        outcome = item.get("outcome")
        if outcome in ("returned_too_small", "exchanged_for_larger"):
            direction += weight
        elif outcome in ("returned_too_large", "exchanged_for_smaller"):
            direction -= weight
        elif outcome == "kept" and item.get("kept_despite"):
            # Kept in spite of something: a real signal, but a weak one. The person tolerated it.
            direction += 0.0
    if total == 0:
        return 0.0, 0, 0
    # 1.5 cm of ease per net weighted step, capped so history can nudge but not override the body.
    offset = max(-3.0, min(3.0, 1.5 * direction / max(1.0, total)))
    return offset, total, same_brand


def _assess(ease: float, lo: float, hi: float, slack: float) -> str:
    if ease < lo - slack:
        return "too_tight"
    if ease < lo:
        return "snug"
    if ease > hi + slack:
        return "too_loose"
    if ease > hi:
        return "roomy"
    return "as_cut"


# --------------------------------------------------------------------------- the matcher


def recommend(profile: dict, garment: dict, disclosure_level: str = "explained") -> MatchReport:
    category = garment.get("category", "")
    flat = garment.get("measurement_method") == "flat_laid"
    crit = critical_zones(category, garment)
    stretch = _usable_stretch(garment)
    prod_tol = garment.get("production_tolerance") or {"value": 1.0, "unit": "cm"}
    prod_tol_cm = _cm(prod_tol["value"], prod_tol["unit"])
    declared_ease = garment.get("intended_ease") or {}

    body = ((profile.get("body") or {}).get("measurements")) or {}
    history_offset, history_n, brand_history_n = _history_offset(profile, garment)

    caveats: list[str] = []
    improve_by: list[str] = []
    fallback_zones = 0
    reversed_ease_zones: set[str] = set()

    # A measurement this implementation has no mapping for is silently dropped
    # otherwise. Saying so is the difference between an answer that can be
    # corrected and one that only looks complete.
    known_keys = {m.garment_key for m in ZONE_MAPPINGS}
    unused_keys = sorted(
        {
            key
            for size in garment.get("sizes", [])
            for key in (size.get("finished_measurements") or {})
        }
        - known_keys
    )

    scored: list[tuple[float, str, list[ExplanationLine]]] = []

    for size in garment.get("sizes", []):
        label = size["size_label"]
        finished = size.get("finished_measurements", {})
        lines: list[ExplanationLine] = []
        penalty = 0.0
        weight_total = 0.0

        for mapping in ZONE_MAPPINGS:
            gm = finished.get(mapping.garment_key)
            bm = body.get(mapping.body_key)
            is_critical = mapping.zone in crit
            if gm is None:
                continue
            if bm is None:
                lines.append(
                    ExplanationLine(
                        zone=mapping.zone,
                        assessment="unknown",
                        critical=is_critical,
                        note="no matching body measurement in the profile",
                    )
                )
                continue

            g_cm = _cm(gm["value"], gm["unit"])
            if flat and mapping.doubles_when_flat_laid:
                g_cm *= 2
            g_cm *= 1 + (stretch if not mapping.linear else 0.0)
            b_cm = _cm(bm["value"], bm["unit"])
            ease = g_cm - b_cm

            band = declared_ease.get(mapping.zone)
            if band is not None and _cm(band["min"], band["unit"]) > _cm(
                band["max"], band["unit"]
            ):
                # An empty interval is not a typo whose intention is known: it is a
                # document asserting something impossible. Swapping the two numbers
                # would be guessing, so the declared ease is treated as absent and
                # the fallback is paid for like any other.
                reversed_ease_zones.add(mapping.zone)
                band = None
            if band is not None:
                lo = _cm(band["min"], band["unit"])
                hi = _cm(band["max"], band["unit"])
            else:
                lo, hi = default_ease(category, mapping.zone, mapping.linear)
                fallback_zones += 1

            shift = _preference_shift(profile, category, mapping.zone, mapping.linear)
            shift += history_offset * mapping.offset_scale
            lo, hi = lo + shift, hi + shift

            meas_tol = float(gm.get("tolerance", prod_tol_cm)) + float(bm.get("tolerance", 0.5))
            slack = meas_tol
            assessment = _assess(ease, lo, hi, slack)

            if ease < lo:
                distance = lo - ease
            elif ease > hi:
                distance = ease - hi
            else:
                distance = 0.0

            scale = max(1.0, meas_tol + (1.0 if mapping.linear else 3.0))
            zone_penalty = distance / scale
            if is_critical and ease < lo:
                zone_penalty *= 1.5  # too tight in a zone that cannot be let out
            w = 3.0 if is_critical else 1.0
            penalty += zone_penalty * w
            weight_total += w

            lines.append(
                ExplanationLine(
                    zone=mapping.zone,
                    assessment=assessment,
                    critical=is_critical,
                    ease_cm=round(ease, 1),
                    intended_ease_cm=(round(lo, 1), round(hi, 1)),
                )
            )

        if weight_total == 0:
            continue
        score = 1.0 / (1.0 + penalty / weight_total)
        if size.get("availability") == "out_of_stock":
            score *= 0.5
        scored.append((score, label, lines))

    scored.sort(key=lambda t: -t[0])

    # A history entry pointing at this very document is not evidence about a
    # similar garment: it is this garment, already worn by this person. Where the
    # outcome says the size was wrong, recommending it again would make the
    # correctability the specification promises purely nominal. The entry does not
    # outweigh the calculation, it removes one option from it.
    returned_labels = _sizes_already_returned(profile, garment)
    rejected = [t for t in scored if t[1] in returned_labels]
    all_returned = bool(rejected) and len(rejected) == len(scored)
    if rejected and not all_returned:
        scored = [t for t in scored if t[1] not in returned_labels]

    computed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    based_on = {
        "body_signals": len(body),
        "preference_signals": len(profile.get("preferences", [])),
        "history_signals": history_n,
        "brand_specific_history_signals": brand_history_n,
        "learned_offset_applied": abs(history_offset) > 0.01,
    }

    if not scored:
        # Cold start: nothing to compare numerically. Fall back on what the person actually wore.
        # This path is the whole argument for the history layer — it works with zero measurements.
        label, conf, notes = _history_only_size(profile, garment)
        return MatchReport(
            cut_profile_id=garment.get("cut_profile_id", ""),
            recommended_size=label,
            confidence=conf,
            disclosure_level=disclosure_level,
            explanation=[
                ExplanationLine(zone="overall", assessment="unknown", note=n) for n in notes
            ],
            based_on=based_on,
            caveats=(
                ["No zone could be compared: the profile has no measurements this garment can be matched against."]
                + (["Answer derived from past purchases alone."] if label else [])
                # Explanation is withheld at result_only, so a reason that lives only
                # there is a reason the reader never gets.
                + [n for n in notes if "size system" in n]
            ),
            improve_by=_improvements(body, profile, garment),
            computed_at=computed_at,
        )

    best_score, best_label, best_lines = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0

    confidence = _confidence(
        body=body,
        lines=best_lines,
        best=best_score,
        runner_up=runner_up,
        history_n=history_n,
        brand_history_n=brand_history_n,
        fallback_zones=fallback_zones,
        n_sizes=len(scored),
    )

    if fallback_zones:
        caveats.append(
            "The garment does not publish an intended ease for every zone; category defaults were used."
        )
    if reversed_ease_zones:
        caveats.append(
            "The garment declares an intended ease whose minimum exceeds its maximum, "
            "so no value could satisfy it. Category defaults were used instead for: "
            + ", ".join(sorted(reversed_ease_zones))
            + "."
        )
    if unused_keys:
        caveats.append(
            "The garment publishes measurements this implementation does not use: "
            + ", ".join(unused_keys)
            + "."
        )
    if any(line.assessment == "unknown" for line in best_lines):
        caveats.append("Some zones could not be evaluated because the profile has no matching measurement.")
    if confidence < 0.4:
        caveats.append("Low confidence: treat this as a starting point, not an answer.")

    if rejected and not all_returned:
        caveats.append(
            "Sizes already returned for this exact garment were removed from the "
            "candidates: " + ", ".join(sorted(lbl for _, lbl, _ in rejected)) + "."
        )
    if all_returned:
        # Every size on offer has already come back. Naming one anyway would be
        # worse than naming none, and the person is owed the reason rather than
        # a silent shrug.
        caveats.append(
            "Every size of this garment has already been returned by this person. "
            "No size is named, deliberately."
        )
    recommended = None if all_returned else (best_label if confidence >= 0.25 else None)
    if recommended is None:
        caveats.append("Not enough signal to name a size. Returning alternatives only, deliberately.")

    return MatchReport(
        cut_profile_id=garment.get("cut_profile_id", ""),
        recommended_size=recommended,
        confidence=confidence,
        disclosure_level=disclosure_level,
        alternatives=[
            {"size_label": lbl, "score": round(sc, 2)} for sc, lbl, _ in scored[1:4]
        ]
        + [
            {
                "size_label": lbl,
                "score": round(sc, 2),
                "note": "Already returned for this garment.",
            }
            for sc, lbl, _ in (rejected if not all_returned else [])
        ],
        explanation=best_lines,
        based_on=based_on,
        caveats=caveats,
        improve_by=_improvements(body, profile, garment),
        computed_at=computed_at,
    )


def _confidence(
    *, body, lines, best, runner_up, history_n, brand_history_n, fallback_zones, n_sizes
) -> float:
    known = [l for l in lines if l.assessment != "unknown"]
    if not known:
        return 0.05
    coverage = len(known) / max(1, len(lines))
    critical_known = [l for l in known if l.critical]
    critical_total = [l for l in lines if l.critical]
    critical_coverage = (
        len(critical_known) / len(critical_total) if critical_total else 1.0
    )

    source_quality = 0.0
    if body:
        weights = {
            "scan_3d": 1.0,
            "tape_measured": 0.9,
            "imported_from_retailer": 0.6,
            "inferred_from_history": 0.5,
            "self_reported": 0.45,
            "estimated_from_size_labels": 0.25,
        }
        source_quality = sum(
            weights.get(m.get("source", "self_reported"), 0.4) * float(m.get("confidence", 0.5))
            for m in body.values()
        ) / len(body)

    margin = best - runner_up if n_sizes > 1 else 0.15
    margin_factor = min(1.0, margin / 0.12)
    history_factor = min(1.0, (history_n + brand_history_n) / 6.0)
    fallback_penalty = min(0.15, 0.03 * fallback_zones)

    raw = (
        0.05
        + 0.25 * coverage
        + 0.20 * critical_coverage
        + 0.25 * source_quality
        + 0.15 * margin_factor
        + 0.10 * history_factor
        - fallback_penalty
    )
    return max(0.0, min(1.0, round(raw, 3)))


def _improvements(body: dict, profile: dict, garment: dict) -> list[str]:
    out: list[str] = []
    needed = {m.body_key for m in ZONE_MAPPINGS}
    missing = [k for k in sorted(needed) if k not in body]
    for key in missing[:3]:
        out.append(f"Add a measurement for {key.replace('_', ' ')}.")
    weak = [k for k, v in body.items() if v.get("source") in ("self_reported", "estimated_from_size_labels")]
    if weak:
        out.append(f"Re-measure with a tape: {', '.join(sorted(weak)[:3])}.")
    if not profile.get("history"):
        out.append("Record how past garments actually fitted — it is the strongest signal available.")
    return out


def _same_size_system(ref: dict, garment: dict) -> bool:
    """False only when both sides name a system and the two disagree.

    A label means nothing without its system: a 42 is a different garment in IT, US
    and UK. The field is optional inside garment_ref, so absence is not treated as
    conflict; dropping entries that simply do not say would throw away usable
    history on no evidence.
    """
    a, b = ref.get("size_system"), garment.get("size_system")
    return not (a and b and a != b)


def _history_only_size(profile: dict, garment: dict) -> tuple[str | None, float, list[str]]:
    """Guess a size from past outcomes alone, with no body measurements at all.

    Only same-brand history is trusted here: a size label from one brand says almost nothing about
    another brand's label, and pretending otherwise is how size charts got their reputation.
    """
    labels = [s["size_label"] for s in garment.get("sizes", [])]
    brand = garment.get("brand")
    category = garment.get("category")
    step = {
        "kept": 0,
        "returned_too_small": 1,
        "exchanged_for_larger": 1,
        "returned_too_large": -1,
        "exchanged_for_smaller": -1,
    }

    crossed_systems = False
    candidates: list[tuple[str, str, float]] = []  # (occurred_at, label, weight)
    for item in profile.get("history", []):
        ref = item.get("garment_ref", {})
        if ref.get("brand") != brand or ref.get("category") != category:
            continue
        if not _same_size_system(ref, garment):
            crossed_systems = True
            continue
        if ref.get("size_label") not in labels:
            continue
        delta = step.get(item.get("outcome"))
        if delta is None:
            continue
        idx = labels.index(ref["size_label"]) + delta
        if not 0 <= idx < len(labels):
            continue
        same_style = ref.get("style_id") == garment.get("style_id")
        candidates.append((item.get("occurred_at", ""), labels[idx], 1.5 if same_style else 1.0))

    if not candidates:
        notes = ["No usable purchase history for this brand and category."]
        if crossed_systems:
            notes.append(
                "History for this brand exists but is labelled in a different size "
                "system, so it was not used."
            )
        return None, 0.0, notes

    candidates.sort(reverse=True)  # most recent first
    scores: dict[str, float] = {}
    for rank, (_, label, weight) in enumerate(candidates):
        scores[label] = scores.get(label, 0.0) + weight * (0.7**rank)
    best = max(scores, key=scores.get)

    # Deliberately capped. A size guessed from labels is a starting point, never a confident answer.
    confidence = min(0.40, 0.18 + 0.07 * len(candidates))
    agreement = scores[best] / sum(scores.values())
    confidence *= 0.6 + 0.4 * agreement
    return best, round(confidence, 3), [
        f"Derived from {len(candidates)} past {brand} purchase(s) in this category, no measurements used."
    ]
