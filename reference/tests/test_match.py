import json
from pathlib import Path

import pytest

from agiofit import load_fit_profile, load_cut_profile, recommend

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


def test_zone_vocabulary_stays_identical_across_schemas():
    # The Cut Profile carries its own copy of the zone enum so that it can be
    # validated without fetching a second document. A copy is only safe while
    # something notices when it drifts, and this is that something.
    fit = json.loads((SCHEMAS / "fit-profile.schema.json").read_text(encoding="utf-8"))
    cut = json.loads((SCHEMAS / "cut-profile.schema.json").read_text(encoding="utf-8"))
    assert cut["$defs"]["zone"]["enum"] == fit["$defs"]["zone"]["enum"]


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
