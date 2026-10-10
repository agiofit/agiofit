import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agiofit import (
    load_fit_profile,
    load_cut_profile,
    recommend,
    UnknownDisclosureLevel,
    UnsupportedSchemaVersion,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
SCHEMAS = ROOT / "schemas"


@pytest.fixture
def mature():
    return load_fit_profile(EXAMPLES / "profile-mature.json")


@pytest.fixture
def cold():
    return load_fit_profile(EXAMPLES / "profile-cold-start.json")


@pytest.fixture
def shirt():
    return load_cut_profile(EXAMPLES / "cut-shirt.json")


# The day every test computes on. A measurement's age changes the answer, and a test must not
# start failing because a year went by.
TODAY = datetime(2026, 10, 8, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr("agiofit.match._now", lambda: TODAY)


# --------------------------------------------------------------------- schema conformance

def test_examples_validate_against_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    profile_schema = json.loads((SCHEMAS / "fit-profile.schema.json").read_text())
    cut_schema = json.loads((SCHEMAS / "cut-profile.schema.json").read_text())
    report_schema = json.loads((SCHEMAS / "match-report.schema.json").read_text())

    for name in ("profile-mature.json", "profile-cold-start.json"):
        jsonschema.validate(json.loads((EXAMPLES / name).read_text()), profile_schema)
    jsonschema.validate(json.loads((EXAMPLES / "cut-shirt.json").read_text()), cut_schema)

    profile = load_fit_profile(EXAMPLES / "profile-mature.json")
    garment = load_cut_profile(EXAMPLES / "cut-shirt.json")
    jsonschema.validate(recommend(profile, garment).to_json(), report_schema)


# --------------------------------------------------------------------- core behaviour

def test_recommends_a_plausible_size(mature, shirt):
    report = recommend(mature, shirt)
    assert report.recommended_size in {"40", "41"}
    assert report.confidence > 0.5


def test_shoulders_are_treated_as_critical(mature, shirt):
    report = recommend(mature, shirt)
    shoulders = next(l for l in report.explanation if l.zone == "shoulders")
    assert shoulders.critical is True


def test_smallest_size_is_never_the_answer(mature, shirt):
    """Size 39 is too tight at the shoulders for this body; it must not win."""
    report = recommend(mature, shirt)
    assert report.recommended_size != "39"


def test_history_pushes_upward(mature, shirt):
    """Two shirts returned or exchanged for being too small must bias the result upward."""
    without = dict(mature)
    without["history"] = []
    biased = recommend(mature, shirt)
    neutral = recommend(without, shirt)
    sizes = ["39", "40", "41", "42"]
    assert sizes.index(biased.recommended_size) >= sizes.index(neutral.recommended_size)
    assert biased.based_on["learned_offset_applied"] is True


def test_cold_start_still_answers_but_says_so(cold, shirt):
    """No measurements at all, one kept shirt from the same brand: still a usable answer."""
    report = recommend(cold, shirt)
    assert report.based_on["body_signals"] == 0
    assert report.recommended_size == "41"
    assert 0.1 < report.confidence < 0.45, "a label-derived guess must never look confident"
    assert report.improve_by, "a cold-start answer must tell the person how to improve it"


def test_cold_start_ignores_other_brands(cold, shirt):
    other = json.loads(json.dumps(cold))
    other["history"][0]["garment_ref"]["brand"] = "SomeoneElse"
    assert recommend(other, shirt).recommended_size is None


def test_every_report_is_correctable(mature, shirt):
    assert recommend(mature, shirt).to_json()["correctable"] is True


# --------------------------------------------------------------------- privacy behaviour

# The ten keys a result_only report may carry. Pinned as a set because a leak
# arrives as a new key, not as a new digit: widening this is a deliberate act and
# has to be argued for in the diff that widens it.
RESULT_ONLY_KEYS = {
    "schema_version",
    "cut_profile_id",
    "computed_at",
    "disclosure_level",
    "recommended_size",
    "confidence",
    "correctable",
    "based_on",
    "caveats",
    "improve_by",
}


def test_result_only_leaks_nothing(mature, shirt):
    out = recommend(mature, shirt, disclosure_level="result_only").to_json()
    assert set(out) == RESULT_ONLY_KEYS

    # Free prose is the one allowed field a measurement could travel inside, so it
    # is the only place worth sweeping for digits. Sweeping the whole document
    # instead collides with the timestamp, the confidence score, the signal counts
    # and any size label that happens to be a number: Italian sizes reach 46, which
    # is also the shoulder measurement below.
    prose = " ".join(out["caveats"] + out["improve_by"])
    for measure in ("100", "88", "46"):  # chest, waist, shoulders
        assert measure not in prose


def test_explained_level_drops_numeric_ease(mature, shirt):
    out = recommend(mature, shirt, disclosure_level="explained").to_json()
    assert out["explanation"], "explained level must still carry per-zone reasoning"
    for line in out["explanation"]:
        assert "ease_cm" not in line
        assert "intended_ease_cm" not in line


def test_scoped_level_keeps_numbers(mature, shirt):
    out = recommend(mature, shirt, disclosure_level="scoped").to_json()
    assert any("ease_cm" in line for line in out["explanation"])


# --------------------------------------------------------------------- unit handling

def test_flat_laid_measurements_are_doubled(mature, shirt):
    """A flat-laid chest width of 58 cm is a 116 cm circumference, not a 58 cm one."""
    report = recommend(mature, shirt, disclosure_level="scoped").to_json()
    chest = next(l for l in report["explanation"] if l["zone"] == "chest")
    assert chest["ease_cm"] > 5  # would be deeply negative if doubling were skipped


def _in_inches(measurement):
    """The same measurement, tolerance included, written in inches."""
    measurement["value"] /= 2.54
    if "tolerance" in measurement:
        measurement["tolerance"] /= 2.54
    measurement["unit"] = "in"


def _answer(profile, garment):
    report = recommend(profile, garment, disclosure_level="scoped")
    return (
        report.recommended_size,
        report.confidence,
        [(line.zone, line.assessment, line.ease_cm) for line in report.explanation],
        report.alternatives,
    )


def test_a_tolerance_is_read_in_the_unit_of_its_measurement(mature, shirt):
    """The same person and the same shirt, written in inches, get the same answer. A tolerance
    of 0.59 in used to be read as 0.59 cm, so declaring in inches made a measurement look two
    and a half times more precise than it was."""
    import copy

    person = copy.deepcopy(mature)
    for measurement in person["body"]["measurements"].values():
        _in_inches(measurement)
    assert _answer(person, shirt) == _answer(mature, shirt)

    garment = copy.deepcopy(shirt)
    for size in garment["sizes"]:
        for measurement in size["finished_measurements"].values():
            _in_inches(measurement)
    assert _answer(mature, garment) == _answer(mature, shirt)


def test_a_tolerance_left_out_is_not_the_strictest_one(mature, shirt):
    """A waist written from memory with no tolerance used to count as precise to half a
    centimetre, stricter than a waist taken with a tape and declared within 1.5. On a 41 that
    is 2 cm roomier at the waist than the brand intends, the tape got "roomy" and the memory
    "too loose". A tolerance left out now counts as the wide end of what its source carries."""
    import copy

    roomy = copy.deepcopy(shirt)
    for size in roomy["sizes"]:
        if size["size_label"] == "41":
            size["finished_measurements"]["waist_width"]["value"] = 58

    def waist(profile):
        report = recommend(profile, roomy, disclosure_level="explained")
        assert report.recommended_size == "41"
        return next(line.assessment for line in report.explanation if line.zone == "waist")

    remembered = copy.deepcopy(mature)
    measurement = remembered["body"]["measurements"]["waist_circumference"]
    measurement["source"] = "self_reported"
    del measurement["tolerance"]
    assert waist(mature) == "roomy"
    assert waist(remembered) == "roomy"


def test_leaving_tolerances_out_never_makes_an_answer_more_confident(mature, shirt):
    """Leaving the field out used to pay, because every measurement without a tolerance became
    the most precise one in the profile."""
    import copy

    without = copy.deepcopy(mature)
    for measurement in without["body"]["measurements"].values():
        measurement.pop("tolerance", None)
    assert recommend(without, shirt).confidence <= recommend(mature, shirt).confidence


def test_a_document_from_another_version_is_refused(mature, shirt):
    # Under a zero major, a minor bump is free to break: 0.2 moves fields 0.1 had
    # elsewhere. Reading it anyway would mean looking for values where they no
    # longer are and answering from whatever happened to be found.
    import copy

    for version in ("0.2.0", "1.0.0", "", "abc"):
        garment = copy.deepcopy(shirt)
        garment["schema_version"] = version
        with pytest.raises(UnsupportedSchemaVersion):
            recommend(mature, garment)


def test_a_newer_patch_is_read_and_declared(mature, shirt):
    # A patch only fixes; what this code knows is still where it expects it. Going
    # ahead is safe, but the reader is owed the fact that part was ignored.
    import copy

    garment = copy.deepcopy(shirt)
    garment["schema_version"] = "0.1.4"
    out = recommend(mature, garment).to_json()

    assert out["recommended_size"] is not None
    assert any("newer than" in c for c in out["caveats"])


def test_size_order_comes_from_measurements_not_from_the_file(cold, shirt):
    # Stepping one size up only means something on an ordered list, and nothing
    # requires a document to list its sizes in order. Taking the order from the
    # measurements makes the answer independent of how the file was written.
    import copy

    expected = recommend(cold, shirt).to_json()["recommended_size"]

    shuffled = copy.deepcopy(shirt)
    shuffled["sizes"] = list(reversed(shuffled["sizes"]))

    assert recommend(cold, shuffled).to_json()["recommended_size"] == expected


def test_a_repeated_size_label_is_declared(mature, shirt):
    # The answer names a label. A label standing for two different garments makes
    # it unusable however good the arithmetic behind it was.
    import copy

    garment = copy.deepcopy(shirt)
    twin = copy.deepcopy(garment["sizes"][2])
    twin["finished_measurements"]["chest_width"]["value"] += 6.0
    garment["sizes"].append(twin)

    caveats = recommend(mature, garment).to_json()["caveats"]
    assert any("same label" in c and twin["size_label"] in c for c in caveats)


def test_an_empty_garment_is_not_blamed_on_the_profile(mature, shirt):
    # Both sides empty land in the same cold-start branch, but only one of the two
    # readers can act. Telling someone with a full profile to go and measure
    # themselves is advice aimed at the wrong person.
    import copy

    garment = copy.deepcopy(shirt)
    for size in garment["sizes"]:
        size["finished_measurements"] = {}

    assert any(
        "this garment publishes no measurements" in c
        for c in recommend(mature, garment).to_json()["caveats"]
    )


def test_history_in_another_size_system_is_not_used(cold, shirt):
    # A label means nothing without its system: a 42 is a different garment in IT,
    # US and UK. The cold start path matches labels by position, so crossing
    # systems there would silently line up sizes that have nothing in common.
    import copy

    assert recommend(cold, shirt).to_json()["recommended_size"] is not None

    profile = copy.deepcopy(cold)
    for entry in profile["history"]:
        entry["garment_ref"]["size_system"] = "US"
    out = recommend(profile, shirt).to_json()

    assert out["recommended_size"] is None
    # The reason has to survive result_only, where explanation is withheld.
    stripped = recommend(profile, shirt, disclosure_level="result_only").to_json()
    assert any("size system" in c for c in stripped["caveats"])


def test_an_undeclared_size_system_is_not_treated_as_a_conflict(cold, shirt):
    # The field is optional inside garment_ref. Dropping entries that simply do
    # not say would throw away usable history on no evidence.
    import copy

    expected = recommend(cold, shirt).to_json()["recommended_size"]
    profile = copy.deepcopy(cold)
    for entry in profile["history"]:
        entry["garment_ref"].pop("size_system", None)

    assert recommend(profile, shirt).to_json()["recommended_size"] == expected


def test_a_past_purchase_of_the_same_model_counts_without_a_category(mature, cold, shirt):
    """An importer that cannot map a shop's categories onto ours leaves the field out, and every
    entry without it used to be dropped: the new profile, whose only purchase is a 41 of this
    very shirt, got no size at all. Brand and style_id together identify a model, so a past
    purchase of the same model needs no category to count."""
    import copy

    def uncategorised(profile):
        profile = copy.deepcopy(profile)
        for item in profile["history"]:
            ref = item["garment_ref"]
            if (ref.get("brand"), ref.get("style_id")) == (shirt["brand"], shirt["style_id"]):
                del ref["category"]
        return profile

    for profile in (mature, cold):
        before = recommend(profile, shirt)
        after = recommend(uncategorised(profile), shirt)
        assert (after.recommended_size, after.confidence, after.based_on) == (
            before.recommended_size,
            before.confidence,
            before.based_on,
        )


def test_a_past_purchase_of_another_model_without_a_category_stays_out(mature, shirt):
    """Without a category, a purchase of a different model could have been anything. It counts
    as if it were not there, rather than as a guess."""
    import copy

    uncategorised = copy.deepcopy(mature)
    for item in uncategorised["history"]:
        if item["garment_ref"]["style_id"] == "POPLIN-SLIM":
            del item["garment_ref"]["category"]
    removed = copy.deepcopy(mature)
    removed["history"] = [
        item for item in removed["history"] if item["garment_ref"]["style_id"] != "POPLIN-SLIM"
    ]
    assert recommend(uncategorised, shirt).confidence == recommend(removed, shirt).confidence


def test_a_reversed_ease_band_falls_back_and_says_so(mature, shirt):
    # min above max describes an interval no value can satisfy. Swapping the two
    # would be guessing at an intention; treating the band as absent is the same
    # fallback the spec already requires when the field is missing.
    import copy

    garment = copy.deepcopy(shirt)
    garment["intended_ease"]["chest"] = {"min": 12.0, "max": 8.0, "unit": "cm"}
    out = recommend(mature, garment, disclosure_level="explained").to_json()

    assert any("minimum exceeds its maximum" in c for c in out["caveats"])
    assert out["confidence"] < recommend(mature, shirt).to_json()["confidence"]
    # The zone must not be judged against the impossible band.
    chest = [l for l in out["explanation"] if l["zone"] == "chest"][0]
    assert chest["assessment"] != "too_loose"


def test_a_single_point_ease_band_is_left_alone(mature, shirt):
    # min == max claims a precision no production line has, but it is coherent.
    # Judging the value rather than its consistency is not this check's job.
    import copy

    garment = copy.deepcopy(shirt)
    garment["intended_ease"]["chest"] = {"min": 10.0, "max": 10.0, "unit": "cm"}
    out = recommend(mature, garment).to_json()

    assert not any("minimum exceeds its maximum" in c for c in out["caveats"])


def _returned(shirt, label, outcome="returned_too_small"):
    return {
        "occurred_at": "2026-07-01T00:00:00Z",
        "garment_ref": {
            "cut_profile_id": shirt["cut_profile_id"],
            "size_label": label,
        },
        "outcome": outcome,
        "source": "user",
    }


def test_a_size_already_returned_is_not_recommended_again(mature, shirt):
    # An entry pointing at this very document is not evidence about a similar
    # garment. Recommending back what the person sent back would make the
    # correctability the spec promises purely nominal.
    import copy

    first = recommend(mature, shirt).to_json()["recommended_size"]

    profile = copy.deepcopy(mature)
    profile["history"].append(_returned(shirt, first))
    out = recommend(profile, shirt, disclosure_level="explained").to_json()

    assert out["recommended_size"] != first
    # Removed, not hidden: it comes back as an alternative carrying the reason.
    assert any(
        alt["size_label"] == first and alt.get("note") for alt in out["alternatives"]
    )
    assert any(first in c for c in out["caveats"])


def test_the_join_needs_the_cut_profile_id(mature, shirt):
    # Same return, recorded without the identifier. A brand or style match means a
    # similar garment, which is a weaker claim and must not trigger exclusion.
    import copy

    first = recommend(mature, shirt).to_json()["recommended_size"]
    profile = copy.deepcopy(mature)
    entry = _returned(shirt, first)
    del entry["garment_ref"]["cut_profile_id"]
    entry["garment_ref"]["brand"] = shirt.get("brand", "Sartoria Esempio")
    profile["history"].append(entry)

    assert recommend(profile, shirt).to_json()["recommended_size"] == first


def test_keeping_a_garment_does_not_exclude_its_size(mature, shirt):
    import copy

    first = recommend(mature, shirt).to_json()["recommended_size"]
    profile = copy.deepcopy(mature)
    profile["history"].append(_returned(shirt, first, outcome="kept"))

    assert recommend(profile, shirt).to_json()["recommended_size"] == first


def test_no_size_is_named_when_every_size_came_back(mature, shirt):
    import copy

    profile = copy.deepcopy(mature)
    for size in shirt["sizes"]:
        profile["history"].append(_returned(shirt, size["size_label"]))
    out = recommend(profile, shirt).to_json()

    assert out["recommended_size"] is None
    assert any("already been returned" in c for c in out["caveats"])


def test_unused_measurements_are_declared(mature, shirt):
    # A measurement the implementation cannot map used to vanish without trace.
    # Naming it is what makes the answer correctable by whoever wrote the profile.
    import copy

    assert not any("does not use" in c for c in recommend(mature, shirt).to_json()["caveats"])

    extended = copy.deepcopy(shirt)
    extended["sizes"][0]["finished_measurements"]["x_yoke_width"] = {
        "value": 42.0,
        "unit": "cm",
    }
    caveats = recommend(mature, extended).to_json()["caveats"]
    assert any("x_yoke_width" in c for c in caveats)


def test_missing_garment_data_lowers_confidence(mature, shirt):
    stripped = json.loads(json.dumps(shirt))
    for size in stripped["sizes"]:
        size["finished_measurements"] = {"chest_width": size["finished_measurements"]["chest_width"]}
    assert recommend(mature, stripped).confidence < recommend(mature, shirt).confidence


def test_every_zone_is_either_mapped_or_knowingly_unmapped():
    """Eight of the sixteen zones have no mapping. That is allowed. Forgetting which is not.

    This test fails the day someone adds a zone to the schema, or mistypes one in ZONE_MAPPINGS.
    Updating the set below is the moment to decide what the implementation should say about it.
    """
    from agiofit.mapping import MAPPED_ZONES

    zones = set(json.loads((SCHEMAS / "fit-profile.schema.json").read_text())["$defs"]["zone"]["enum"])

    assert MAPPED_ZONES <= zones, "a mapping points at a zone the schema does not define"
    assert zones - MAPPED_ZONES == {
        "overall",       # the scope of a preference, not a measurement
        "bust",          # no body measurement name is defined for it yet
        "arm_width",     # sleeve_width exists on the garment side, nothing on the body side
        "calf",          # calf_width exists on the garment side, nothing on the body side
        "rise",          # the garment side is split into front_rise and back_rise
        "total_length",  # rejected as a measurement name: two people measure it from two places
        "foot_length",   # footwear is out of the measurement vocabulary, by decision
        "foot_width",
    }


def test_zones_that_cannot_be_evaluated_are_declared(mature, shirt):
    """Eight of the sixteen zones have no mapping. Dropping one in silence made the answer look
    as complete as one where every zone was weighed, whether the garment named the zone or the
    category default did."""
    import copy

    assert not any("no mapping" in c for c in recommend(mature, shirt).to_json()["caveats"])

    declared = copy.deepcopy(shirt)
    declared["critical_zones"] = ["shoulders", "bust"]
    caveats = recommend(mature, declared).to_json()["caveats"]
    assert any("bust" in c and "no mapping" in c for c in caveats)

    defaulted = copy.deepcopy(shirt)
    defaulted["category"] = "dresses"
    del defaulted["critical_zones"]
    caveats = recommend(mature, defaulted).to_json()["caveats"]
    assert any("bust" in c and "no mapping" in c for c in caveats), \
        "a category default is as silent as a declaration"

    ease = copy.deepcopy(shirt)
    ease["intended_ease"]["calf"] = {"min": 2.0, "max": 6.0, "unit": "cm"}
    caveats = recommend(mature, ease).to_json()["caveats"]
    assert any("calf" in c and "does not use" in c for c in caveats)


def test_a_critical_zone_that_cannot_be_evaluated_lowers_confidence(mature, shirt):
    """It used to raise it. A zone with no mapping produced no explanation line, so it fell out
    of the denominator of critical_coverage and the answer scored as if the zone had been
    measured and found to fit. No absolute number is asserted here: the arithmetic is not
    normative, the direction is."""
    import copy

    base = recommend(mature, shirt).confidence

    partly = copy.deepcopy(shirt)
    partly["critical_zones"] = ["shoulders", "neck", "bust"]
    assert recommend(mature, partly).confidence < base

    none_reachable = copy.deepcopy(shirt)
    none_reachable["critical_zones"] = ["bust"]
    assert recommend(mature, none_reachable).confidence < base


def test_a_critical_measurement_the_garment_omits_lowers_confidence(mature, shirt):
    """It used to raise it. An absent garment key produced no explanation line at all, so the zone
    left the denominator of critical_coverage together with the numerator, and a Cut Profile that
    never measured the shoulders of a shirt scored like one that did. The profile side of the same
    loop was already symmetric; the garment side was not."""
    import copy

    without = copy.deepcopy(shirt)
    for size in without["sizes"]:
        del size["finished_measurements"]["shoulder_width"]

    report = recommend(mature, without, disclosure_level="explained")
    assert report.confidence < recommend(mature, shirt).confidence

    shoulders = [l for l in report.to_json()["explanation"] if l["zone"] == "shoulders"]
    assert shoulders and shoulders[0]["assessment"] == "unknown"

    # Only critical zones earn the unknown line. A shirt has no thigh, and must not be marked
    # down for a measurement its category does not have.
    zones = {
        l["zone"]
        for l in recommend(mature, shirt, disclosure_level="explained").to_json()["explanation"]
    }
    assert "thigh" not in zones and "inseam" not in zones


def test_a_category_with_no_critical_zones_does_not_collect_the_credit(mature, shirt):
    """An empty critical set used to score as full coverage, so a category nobody had thought
    about was paid a fifth of the confidence for weighting nothing."""
    import copy

    unweighted = copy.deepcopy(shirt)
    unweighted["category"] = "swimwear"
    del unweighted["critical_zones"]

    report = recommend(mature, unweighted)
    assert any("no critical zones for this category" in c for c in report.to_json()["caveats"])

    # The same document naming one critical zone, which its measurements satisfy. That answer
    # knows strictly more, so it must score higher. While an empty set counted as full coverage
    # the two came out level, and naming a zone could only lose points.
    named = copy.deepcopy(unweighted)
    named["critical_zones"] = ["chest"]
    named_report = recommend(mature, named)
    assert named_report.confidence > report.confidence
    assert not any(
        "no critical zones for this category" in c for c in named_report.to_json()["caveats"]
    )


def test_every_category_either_has_critical_zones_or_declares_it_has_none():
    """The companion of the zone test above, on the other table. A category that falls through
    both is a silent hole: nothing is weighted, and nothing says so."""
    from agiofit.mapping import CRITICAL_ZONES, CATEGORIES_WITHOUT_CRITICAL_DEFAULTS

    categories = set(
        json.loads((SCHEMAS / "cut-profile.schema.json").read_text())["properties"]["category"]["enum"]
    )

    assert not (set(CRITICAL_ZONES) & CATEGORIES_WITHOUT_CRITICAL_DEFAULTS)
    assert set(CRITICAL_ZONES) | CATEGORIES_WITHOUT_CRITICAL_DEFAULTS == categories


def _measured_by(profile, estimated_keys):
    """The same body, with the named measurements estimated from size labels and the rest
    taken with a tape. History and preferences are cleared, so only the measurements speak."""
    import copy

    profile = copy.deepcopy(profile)
    profile["history"], profile["preferences"] = [], []
    for key, measurement in profile["body"]["measurements"].items():
        if key in estimated_keys:
            measurement["source"], measurement["confidence"] = "estimated_from_size_labels", 1.0
        else:
            measurement["source"], measurement["confidence"] = "tape_measured", 0.9
    return profile


def test_label_estimates_cannot_lift_an_answer_past_the_cold_start_ceiling(mature, shirt):
    """A body measurement estimated from size labels is a size label written down as a
    measurement. With every measurement estimated that way, the answer used to come out at
    0.63, above the 0.40 a cold start may claim from the very same kind of evidence."""
    every_key = set(mature["body"]["measurements"])
    report = recommend(_measured_by(mature, every_key), shirt)

    assert report.confidence <= 0.40
    assert any("estimated from size labels" in c for c in report.caveats)


def test_guessing_the_critical_zones_costs_more_than_guessing_the_rest(mature, shirt):
    """Above the ceiling, confidence is earned by the measurements that are not label
    estimates, and a critical zone counts as much as it does when the size is chosen. Guessing
    the shoulders and neck of a shirt used to score higher than guessing its chest, waist and
    sleeve, the reverse of what matters."""
    critical_guessed = recommend(
        _measured_by(mature, {"shoulder_width", "neck_circumference"}), shirt
    )
    rest_guessed = recommend(
        _measured_by(mature, {"chest_circumference", "waist_circumference", "arm_length"}), shirt
    )

    assert critical_guessed.confidence < rest_guessed.confidence


def test_a_label_estimate_the_garment_does_not_use_costs_nothing_here(mature, shirt):
    """The mature profile's inseam is a label estimate, and a shirt never looks at it. The
    ceiling is about the evidence behind this answer, not about the profile as a whole."""
    assert mature["body"]["measurements"]["inseam"]["source"] == "estimated_from_size_labels"
    report = recommend(mature, shirt)

    assert not any("estimated from size labels" in c for c in report.caveats)


def test_a_measurement_the_garment_does_not_use_does_not_move_the_confidence(mature, shirt):
    """The quality of the measurements used to be averaged over the whole profile: five invented
    measurements declared as 3D scans lifted the shirt's confidence, and an inseam estimated from
    size labels, which no shirt reads, pulled it down."""
    import copy

    base = recommend(mature, shirt).confidence

    padded = copy.deepcopy(mature)
    for name in ("x_a", "x_b", "x_c", "x_d", "x_e"):
        padded["body"]["measurements"][name] = {
            "value": 50,
            "unit": "cm",
            "source": "scan_3d",
            "confidence": 1.0,
            "observed_at": "2026-10-01T00:00:00Z",
            "tolerance": 0.5,
        }
    assert recommend(padded, shirt).confidence == base

    trimmed = copy.deepcopy(mature)
    del trimmed["body"]["measurements"]["inseam"]
    assert recommend(trimmed, shirt).confidence == base


def test_a_measurement_counts_for_how_precise_it_is_not_how_it_was_taken(mature, shirt):
    """A tolerance wider than usual for its source used to leave the confidence where it was. A
    chest taken with a tape but declared within 3 cm now counts like one remembered within 3."""
    import copy

    def with_chest(source, tolerance):
        profile = copy.deepcopy(mature)
        profile["body"]["measurements"]["chest_circumference"].update(
            source=source, tolerance=tolerance
        )
        return recommend(profile, shirt).confidence

    assert with_chest("tape_measured", 3.0) < with_chest("tape_measured", 1.0)
    assert with_chest("tape_measured", 3.0) == with_chest("self_reported", 3.0)


def test_an_old_girth_counts_for_less_than_a_fresh_one(mature, shirt):
    """Measurements from ten years ago used to count exactly like this year's. A girth now loses
    precision with every full year, while the lengths of an adult keep their value, and the day
    of the calculation can be given: five years on, the same profile is less sure."""
    import copy

    base = recommend(mature, shirt).confidence

    def dated(keys, when):
        profile = copy.deepcopy(mature)
        for key in keys:
            profile["body"]["measurements"][key]["observed_at"] = when
        return recommend(profile, shirt).confidence

    girths = ("chest_circumference", "waist_circumference", "neck_circumference")
    assert dated(girths, "2021-09-01T00:00:00Z") < dated(girths, "2025-09-01T00:00:00Z") < base
    assert dated(("shoulder_width", "arm_length"), "2016-01-01T00:00:00Z") == base
    later = datetime(2031, 10, 8, tzinfo=timezone.utc)
    assert recommend(mature, shirt, now=later).confidence < base


def test_an_unknown_disclosure_level_fails_closed(mature, shirt):
    """Serialisation removes what a level forbids, so a level it did not recognise used to
    remove nothing: "Result_only", capitalised, came out with the numeric ease that the
    arithmetic leak exists to withhold."""
    import copy

    with pytest.raises(UnknownDisclosureLevel):
        recommend(mature, shirt, disclosure_level="Result_only")

    # The same guard where the leak would happen, for a report built or changed by hand.
    report = recommend(mature, shirt, disclosure_level="result_only")
    report.disclosure_level = "resultonly"
    with pytest.raises(UnknownDisclosureLevel):
        report.to_json()

    # And from the profile, which nothing guarantees was validated before it got here.
    profile = copy.deepcopy(mature)
    profile["disclosure_defaults"]["default_level"] = "Result_only"
    with pytest.raises(UnknownDisclosureLevel):
        recommend(profile, shirt)


def test_with_no_level_requested_the_persons_default_applies(mature, shirt):
    """Both example profiles declare result_only, and both used to come out explained: more
    disclosure than the person had written down."""
    import copy

    def level(profile, **kw):
        return recommend(profile, shirt, **kw).to_json()["disclosure_level"]

    assert mature["disclosure_defaults"]["default_level"] == "result_only"
    assert level(mature) == "result_only"

    profile = copy.deepcopy(mature)
    profile["disclosure_defaults"]["default_level"] = "explained"
    assert level(profile) == "explained"

    # Nothing declared means the least disclosure, not the implementation's preference.
    del profile["disclosure_defaults"]
    assert level(profile) == "result_only"

    # The person's level is a default, not a ceiling: a request that names a level gets it.
    assert level(mature, disclosure_level="scoped") == "scoped"


def _trousers():
    """Two sizes of a plain trouser, enough to put the hips in play."""
    return {
        "schema_version": "0.1.0",
        "cut_profile_id": "test-trousers-hips",
        "category": "trousers",
        "size_system": "IT",
        "measurement_method": "circumference",
        "provenance": {"published_by": "brand"},
        "sizes": [
            {
                "size_label": label,
                "finished_measurements": {
                    "waist_width": {"value": waist, "unit": "cm"},
                    "hip_width": {"value": hip, "unit": "cm"},
                },
            }
            for label, waist, hip in (("48", 90, 104), ("50", 94, 108))
        ],
    }


def test_a_never_shared_measurement_leaves_no_trace_at_any_level(mature):
    """The mature profile lists its hips in never_share. At scoped the report used to carry
    an ease of 5 cm on a size that publishes 104 cm at the hip, and 104 - 5 is the 99 the
    person had withheld. A judgement alone does almost as much: "as cut", read against the
    ease band, places the hips inside an 8 cm window."""
    assert mature["disclosure_defaults"]["never_share"] == ["hip_circumference"]
    trousers = _trousers()

    # The hips still count towards the answer: they are used where the profile lives.
    report = recommend(mature, trousers, disclosure_level="scoped")
    assert any(line.zone == "hip" for line in report.explanation)

    for level in ("explained", "scoped", "full"):
        out = recommend(mature, trousers, disclosure_level=level).to_json()
        zones = {line["zone"] for line in out["explanation"]}
        assert "hip" not in zones
        assert "waist" in zones, "only the listed measurement is withheld"
        assert any("at the person's request" in c for c in out["caveats"])

    # Where nothing is explained there is nothing to withhold, and nothing to announce.
    out = recommend(mature, trousers, disclosure_level="result_only").to_json()
    assert not any("at the person's request" in c for c in out["caveats"])


def test_never_sharing_the_body_layer_withholds_every_zone(mature, shirt):
    """never_share names measurement keys or whole layers, and the body layer is every
    measurement in it."""
    import copy

    profile = copy.deepcopy(mature)
    profile["disclosure_defaults"]["never_share"] = ["body"]
    out = recommend(profile, shirt, disclosure_level="scoped").to_json()

    assert out["explanation"] == []
    assert out["recommended_size"] is not None
    assert any("at the person's request" in c for c in out["caveats"])


def _bands(profile, garment):
    """The ease band each zone was judged against, after preferences and history."""
    report = recommend(profile, garment, disclosure_level="scoped")
    return {line.zone: line.intended_ease_cm for line in report.explanation}


def test_history_corrects_the_zone_it_names_not_every_zone(mature, shirt):
    """The mature profile's returns say "shoulders too tight, chest right". The correction
    used to land on every zone by fixed weights, the chest taking four times what the
    shoulders got: +2.0 cm on the zone that was right, +0.5 on the one that was wrong."""
    declared = shirt["intended_ease"]
    bands = _bands(mature, shirt)

    # The chest was right, so its band is the one the brand declared.
    assert bands["chest"] == (declared["chest"]["min"], declared["chest"]["max"])
    # The shoulders were too tight, so their band moves towards more ease.
    assert bands["shoulders"][0] > declared["shoulders"]["min"]


def test_an_outcome_that_does_not_say_where_still_moves_every_zone(mature, shirt):
    """Whoever did not say where the garment was wrong loses nothing: the outcome alone
    still moves every zone, by the per-zone scale."""
    import copy

    profile = copy.deepcopy(mature)
    for item in profile["history"]:
        item.pop("zone_feedback", None)
    bands = _bands(profile, shirt)

    assert bands["chest"][0] > shirt["intended_ease"]["chest"]["min"]


def _slim(shirt):
    """The same sizes, with the brand declaring less ease at the chest and waist: a slimmer
    intended fit, where the 40 and the 41 each get something wrong."""
    import copy

    slim = copy.deepcopy(shirt)
    slim["cut_profile_id"] = "sartoria-esempio:POPLIN-SLIM:2026"
    slim["style_id"] = "POPLIN-SLIM"
    slim["style_name"] = "Slim Poplin Shirt"
    for zone in ("chest", "waist"):
        slim["intended_ease"][zone] = {"min": 6, "max": 12, "unit": "cm"}
    return slim


def test_a_flaw_kept_before_counts_for_less_than_one_returned_before(mature, shirt):
    """The mature profile kept the 41 despite a roomy waist, and sent back two 40s for tight
    shoulders. On a slimmer cut the 40 has snug shoulders and the 41 a loose waist. The kept
    compromise used to count for nothing, and the answer was the 40: the tight shoulders again."""
    import copy

    slim = _slim(shirt)
    report = recommend(mature, slim, disclosure_level="explained")
    assert report.recommended_size == "41"
    # The judgement is not softened: the waist is still reported as it is.
    waist = next(line for line in report.explanation if line.zone == "waist")
    assert waist.assessment == "too_loose"

    without = copy.deepcopy(mature)
    for item in without["history"]:
        item.pop("kept_despite", None)
    assert recommend(without, slim).recommended_size == "40"


def test_a_kept_flaw_teaches_only_the_direction_it_was_kept_in(mature, shirt):
    """kept_despite names a zone, not a direction. Without a verdict on that zone in the same
    entry there is nothing to learn, and a flaw the other way is not what was tolerated."""
    import copy

    slim = _slim(shirt)

    no_verdict = copy.deepcopy(mature)
    for item in no_verdict["history"]:
        kept = item.get("kept_despite") or []
        item["zone_feedback"] = [f for f in item.get("zone_feedback", []) if f["zone"] not in kept]
    assert recommend(no_verdict, slim).recommended_size == "40"

    other_way = copy.deepcopy(mature)
    for item in other_way["history"]:
        for verdict in item.get("zone_feedback", []):
            if verdict["zone"] in (item.get("kept_despite") or []):
                verdict["verdict"] = "snug"
    assert recommend(other_way, slim).recommended_size == "40"


def _with_preferences(profile, *preferences):
    """The profile with its preferences replaced by shirt ones, each (zone, preference, source,
    updated_at), at full strength and confidence."""
    import copy

    profile = copy.deepcopy(profile)
    profile["preferences"] = [
        {
            "category": "shirts",
            "zone": zone,
            "preference": preference,
            "strength": 1.0,
            "source": source,
            "confidence": 1.0,
            "updated_at": when,
        }
        for zone, preference, source, when in preferences
    ]
    return profile


RELAXED = ("overall", "relaxed", "declared", "2026-09-01T00:00:00Z")


def test_a_preference_written_twice_counts_once(mature, shirt):
    """Preferences used to be added together: a profile imported twice asked for 4 cm more ease
    at the chest with every copy of "relaxed"."""
    once = _bands(_with_preferences(mature, RELAXED), shirt)
    assert _bands(_with_preferences(mature, RELAXED, RELAXED, RELAXED), shirt) == once


def test_a_preference_about_a_zone_wins_over_one_about_the_whole_garment(mature, shirt):
    """A "relaxed overall" with "regular shoulders" used to widen the shoulders as well, because
    the regular preference added nothing instead of replacing the general one."""
    regular_shoulders = ("shoulders", "regular", "declared", "2026-09-01T00:00:00Z")
    both = _bands(_with_preferences(mature, RELAXED, regular_shoulders), shirt)
    assert both["shoulders"] == _bands(_with_preferences(mature), shirt)["shoulders"]
    assert both["chest"] == _bands(_with_preferences(mature, RELAXED), shirt)["chest"]


def test_the_persons_own_word_and_then_the_latest_decide_a_preference(mature, shirt):
    """A declared "relaxed" and an inferred "fitted" used to cancel out without anyone being
    told, and a newer "regular" could not undo an older "relaxed"."""
    relaxed = _bands(_with_preferences(mature, RELAXED), shirt)
    inferred = ("overall", "fitted", "inferred_from_history", "2026-10-01T00:00:00Z")
    assert _bands(_with_preferences(mature, RELAXED, inferred), shirt) == relaxed
    assert _bands(_with_preferences(mature, inferred, RELAXED), shirt) == relaxed

    older = ("overall", "relaxed", "declared", "2025-01-01T00:00:00Z")
    newer = ("overall", "regular", "declared", "2026-01-01T00:00:00Z")
    latest = _bands(_with_preferences(mature, newer), shirt)
    assert _bands(_with_preferences(mature, older, newer), shirt) == latest
    assert _bands(_with_preferences(mature, newer, older), shirt) == latest


def test_the_same_outcome_written_twice_counts_once(mature, cold, shirt):
    """Entries carry no identifier, and one written twice used to count twice: an import run again
    made the answer surer without telling it anything new, and the new profile's only purchase,
    imported three times, went from 0.25 to 0.39. Who wrote it, which import brought it, the time
    zone of its date and the order of its lists do not make it another event."""
    import copy
    from datetime import timedelta

    def written_again(profile):
        again = copy.deepcopy(profile)
        for item in profile["history"]:
            twin = copy.deepcopy(item)
            twin["source"] = "retailer_import"
            twin["import_ref"] = "the-same-export-again"
            moment = datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00"))
            twin["occurred_at"] = moment.astimezone(timezone(timedelta(hours=2))).isoformat()
            if "zone_feedback" in twin:
                twin["zone_feedback"].reverse()
            again["history"].append(twin)
        return again

    for profile in (mature, cold):
        once = recommend(profile, shirt, "scoped").to_json()
        assert recommend(written_again(profile), shirt, "scoped").to_json() == once


def _outcome(when, size, outcome, zone, verdict):
    """One shirt of this very model, with a single verdict, as the person recorded it."""
    return {
        "occurred_at": when,
        "garment_ref": {
            "brand": "Sartoria Esempio",
            "style_id": "OXF-CLASSIC",
            "category": "shirts",
            "size_label": size,
        },
        "outcome": outcome,
        "zone_feedback": [{"zone": zone, "verdict": verdict}],
        "source": "user",
    }


def test_a_recent_outcome_outweighs_an_old_one_on_a_girth(mature, shirt):
    """A return from five years ago used to weigh as much as last month's: "chest too tight" then
    and "chest too loose" now cancelled out, and the band stayed where it was. A body moves at the
    girths, so the recent verdict now decides most of it. Shoulders do not grow, and two opposite
    verdicts there still cancel. Age alone moves no band: it makes the answer less sure."""
    import copy

    def bands_after(*history):
        profile = copy.deepcopy(mature)
        profile["history"] = list(history)
        return _bands(profile, shirt)

    old, recent = "2021-09-01T00:00:00Z", "2026-09-01T00:00:00Z"
    declared = shirt["intended_ease"]

    chest = bands_after(
        _outcome(old, "40", "returned_too_small", "chest", "too_tight"),
        _outcome(recent, "42", "returned_too_large", "chest", "too_loose"),
    )["chest"]
    assert chest[0] < declared["chest"]["min"]

    shoulders = bands_after(
        _outcome(old, "40", "returned_too_small", "shoulders", "too_tight"),
        _outcome(recent, "42", "returned_too_large", "shoulders", "too_loose"),
    )["shoulders"]
    assert shoulders == (declared["shoulders"]["min"], declared["shoulders"]["max"])

    aged = copy.deepcopy(mature)
    for item in aged["history"]:
        item["occurred_at"] = item["occurred_at"].replace("2026", "2021")
    assert _bands(aged, shirt) == _bands(mature, shirt)
    assert recommend(aged, shirt).confidence < recommend(mature, shirt).confidence


def test_the_latest_purchase_is_found_by_its_moment_not_its_text(cold, shirt):
    """A purchase dated 02:00 at UTC+2 happened at midnight in UTC, an hour before one dated
    01:00Z. Ordered as text it came second, passed for the latest, and the cold start named
    its size."""
    import copy

    profile = copy.deepcopy(cold)
    the_41 = profile["history"][0]
    the_41["occurred_at"] = "2026-05-05T01:00:00Z"
    the_40 = copy.deepcopy(the_41)
    the_40["garment_ref"]["size_label"] = "40"
    the_40["occurred_at"] = "2026-05-05T02:00:00+02:00"
    profile["history"] = [the_41, the_40]
    assert recommend(profile, shirt).recommended_size == "41"


def test_a_size_returned_under_another_spelling_is_not_recommended_again(mature, shirt):
    """The history and the garment are written by different people. A 41 sent back and recorded
    as "41 ", with a space at the end, used to be recommended again without a word, because the
    labels were compared letter by letter. Spaces do not make another label."""
    import copy

    first = recommend(mature, shirt).to_json()["recommended_size"]
    for spelling in (first + " ", "  " + first + "  "):
        profile = copy.deepcopy(mature)
        profile["history"].append(_returned(shirt, spelling))
        out = recommend(profile, shirt, disclosure_level="explained").to_json()

        assert out["recommended_size"] != first
        assert any(
            alt["size_label"] == first and alt.get("note") for alt in out["alternatives"]
        )


def test_a_past_purchase_written_with_other_spaces_or_capitals_still_counts(mature, cold, shirt):
    """A kept 41 recorded as " 41 " used to leave the new profile with no size at all, a kept "m "
    taught nothing about a garment labelled M, and a return written again by hand with a space
    counted as a second event. Spaces and capitals do not make another label."""
    import copy

    def relabelled(profile, label):
        profile = copy.deepcopy(profile)
        profile["history"][0]["garment_ref"]["size_label"] = label
        return profile

    assert recommend(relabelled(cold, " 41 "), shirt).to_json() == recommend(cold, shirt).to_json()

    lettered = copy.deepcopy(shirt)
    for size, letter in zip(lettered["sizes"], ("S", "M", "L", "XL")):
        size["size_label"] = letter
    assert recommend(relabelled(cold, "m "), lettered).recommended_size == "M"

    twice = copy.deepcopy(mature)
    again = copy.deepcopy(mature["history"][0])
    again["garment_ref"]["size_label"] += " "
    again["source"] = "user"
    again.pop("import_ref")
    twice["history"].append(again)
    once = recommend(mature, shirt, "scoped").to_json()
    assert recommend(twice, shirt, "scoped").to_json() == once


def test_a_size_system_inside_a_label_is_not_guessed(cold, shirt):
    """A label written "IT 41" could be read as the 41 only by knowing what IT means, which is
    the size-chart knowledge this model does without. It is not guessed. With no size named,
    the reason now reaches a result_only answer too, where the person can see that the history
    was not used."""
    import copy

    profile = copy.deepcopy(cold)
    profile["history"][0]["garment_ref"]["size_label"] = "IT 41"
    out = recommend(profile, shirt, disclosure_level="result_only").to_json()

    assert out["recommended_size"] is None
    assert any("No usable purchase history" in c for c in out["caveats"])
