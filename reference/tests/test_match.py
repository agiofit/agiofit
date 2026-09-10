import json
from pathlib import Path

import pytest

from agiofit import (
    load_fit_profile,
    load_cut_profile,
    recommend,
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


def test_a_reversed_ease_band_falls_back_and_says_so(mature, shirt):
    # min above max describes an interval no value can satisfy. Swapping the two
    # would be guessing at an intention; treating the band as absent is the same
    # fallback the spec already requires when the field is missing.
    import copy

    garment = copy.deepcopy(shirt)
    garment["intended_ease"]["chest"] = {"min": 12.0, "max": 8.0, "unit": "cm"}
    out = recommend(mature, garment).to_json()

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
    out = recommend(profile, shirt).to_json()

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
