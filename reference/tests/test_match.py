import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from agiofit import (
    load_fit_profile,
    load_cut_profile,
    recommend,
    UnknownDisclosureLevel,
    UnreadableDate,
    UnsupportedSchemaVersion,
    answer,
    effective_level,
    request_problems,
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

# A date-time as RFC 3339 writes it, for the format check below: written here rather than taken
# from the implementation, so that the two can disagree.
RFC3339_DATE_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})"
)


def _formats(jsonschema):
    """A format checker that asserts, as spec/00 asks of a validator. jsonschema checks uuid on
    its own, and date-time and uri only with packages this suite does not install, so those two
    are checked here."""
    checker = jsonschema.FormatChecker()

    @checker.checks("date-time")
    def date_time(value):
        return not isinstance(value, str) or RFC3339_DATE_TIME.fullmatch(value) is not None

    @checker.checks("uri", raises=ValueError)
    def uri(value):
        return not isinstance(value, str) or bool(urlsplit(value).scheme)

    return checker


def test_examples_validate_against_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    formats = _formats(jsonschema)
    profile_schema = json.loads((SCHEMAS / "fit-profile.schema.json").read_text())
    cut_schema = json.loads((SCHEMAS / "cut-profile.schema.json").read_text())
    report_schema = json.loads((SCHEMAS / "match-report.schema.json").read_text())

    for name in ("profile-mature.json", "profile-cold-start.json"):
        profile = json.loads((EXAMPLES / name).read_text())
        jsonschema.validate(profile, profile_schema, format_checker=formats)
    garment = json.loads((EXAMPLES / "cut-shirt.json").read_text())
    jsonschema.validate(garment, cut_schema, format_checker=formats)

    profile = load_fit_profile(EXAMPLES / "profile-mature.json")
    garment = load_cut_profile(EXAMPLES / "cut-shirt.json")
    report = recommend(profile, garment).to_json()
    jsonschema.validate(report, report_schema, format_checker=formats)


def test_a_format_is_checked_where_nothing_here_reads_it():
    """JSON Schema 2020-12 reads format as a note unless a validator is told otherwise, so a
    profile_id written as an email address passed, though the schema asks for a uuid and the
    specification forbids deriving one from an email, and so did an updated_at of "yesterday".
    This implementation reads neither and does not police them: the suite validates with
    formats asserted, as spec/00 asks a validator to."""
    import copy

    jsonschema = pytest.importorskip("jsonschema")
    formats = _formats(jsonschema)
    profile_schema = json.loads((SCHEMAS / "fit-profile.schema.json").read_text())
    cut_schema = json.loads((SCHEMAS / "cut-profile.schema.json").read_text())

    profile = json.loads((EXAMPLES / "profile-mature.json").read_text())
    for field, value in (("profile_id", "mario.rossi@example.com"), ("updated_at", "yesterday")):
        wrong = dict(profile, **{field: value})
        jsonschema.validate(wrong, profile_schema)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(wrong, profile_schema, format_checker=formats)

    garment = json.loads((EXAMPLES / "cut-shirt.json").read_text())
    for field, value in (("published_at", "February 2026"), ("source_url", "not a link")):
        wrong = copy.deepcopy(garment)
        wrong["provenance"][field] = value
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(wrong, cut_schema, format_checker=formats)


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

# The eight keys a result_only report may carry. Pinned as a set because a leak
# arrives as a new key, not as a new digit: widening this is a deliberate act and
# has to be argued for in the diff that widens it. based_on and improve_by are not
# among them: they describe the profile, not the answer.
RESULT_ONLY_KEYS = {
    "schema_version",
    "cut_profile_id",
    "computed_at",
    "disclosure_level",
    "recommended_size",
    "confidence",
    "correctable",
    "caveats",
}


def test_result_only_leaks_nothing(mature, shirt):
    out = recommend(mature, shirt, disclosure_level="result_only").to_json()
    assert set(out) == RESULT_ONLY_KEYS

    # Free prose is the one allowed field a measurement could travel inside, so it
    # is the only place worth sweeping for digits. Sweeping the whole document
    # instead collides with the timestamp, the confidence score and any size label
    # that happens to be a number: Italian sizes reach 46, which is also the shoulder
    # measurement below.
    prose = " ".join(out["caveats"])
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


def test_the_schema_descriptions_no_longer_say_what_the_errata_list():
    """spec/00-overview.md lists seven descriptions of the v0.1 schemas that say something the
    specification does not. A description is prose and no test can say that it is right; this one
    notices if a sentence known to be wrong comes back, if the sentence that replaced it goes, or
    if a field that is easy to misread loses its description."""
    texts = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(SCHEMAS.glob("*.json"))
    }
    assert len(texts) == 4
    for wrong in (
        "expected to weight them differently",
        "so the two can be compared directly",
        "how much a verifier may receive",
        "the whole profile",
        "is not the same as a hard constraint",
        "numeric fields MUST be omitted",
        "rests on one self-reported measurement",
    ):
        for name, text in texts.items():
            assert wrong not in text, (name, wrong)

    fit = json.loads(texts["fit-profile.schema.json"])
    cut = json.loads(texts["cut-profile.schema.json"])
    report = json.loads(texts["match-report.schema.json"])
    alternative = report["properties"]["alternatives"]["items"]["properties"]
    for field, says in (
        (cut["properties"]["provenance"]["properties"]["published_by"], "no weight is assigned"),
        (cut["properties"]["cut"], "should not compute with it"),
        (fit["properties"]["disclosure_defaults"], "a default, not a ceiling"),
        (fit["$defs"]["disclosure_level"], "No level carries the profile itself"),
        (fit["$defs"]["fit_preference"]["properties"]["strength"], "states at 1"),
        (report["properties"]["explanation"], "Absent at result_only"),
        (report["properties"]["based_on"], "Not sent at result_only"),
        (fit["properties"]["units"], "each measurement carries its own unit"),
        (alternative["score"], "Not a confidence"),
    ):
        assert says in field["description"], says


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


def test_a_flat_width_is_half_a_girth_and_so_is_its_tolerance(mature, shirt):
    """Plus or minus 1 cm across a flat chest is plus or minus 2 cm round it. The width was doubled
    and its tolerance was not, so a garment measured flat looked twice as precise at its girths as
    the same garment measured round: a 41 whose chest sat 1.5 cm past the brand's band was called
    too loose, and named only as the closest size, though the shirt itself varies by 2 cm there.
    The collar is laid flat too, but measured whole, and keeps its tolerance."""
    import copy

    person = copy.deepcopy(mature)
    # Taken as exact, so that only the garment's tolerance is left to judge by.
    for key in ("chest_circumference", "neck_circumference"):
        person["body"]["measurements"][key]["tolerance"] = 0

    # The 41 alone: 16 cm of ease at the chest, under the shirt's 1 cm production tolerance, and
    # 2 cm at the collar, under its own 0.5 cm.
    garment = copy.deepcopy(shirt)
    garment["sizes"] = [size for size in garment["sizes"] if size["size_label"] == "41"]

    def judged(zone, low, high):
        cut = copy.deepcopy(garment)
        cut["intended_ease"][zone] = {"min": low, "max": high, "unit": "cm"}
        report = recommend(person, cut, disclosure_level="explained")
        return next(line.assessment for line in report.explanation if line.zone == zone)

    assert judged("chest", 12, 14.5) == "roomy"  # 1.5 cm past: inside the 2 cm round the chest
    assert judged("chest", 12, 13.5) == "too_loose"  # 2.5 cm past: outside it
    assert judged("neck", 0.5, 1.25) == "too_loose"  # 0.75 cm past a whole 0.5 cm


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


def test_schemas_examples_and_reference_agree_on_the_version():
    """One version, said in four places: what the reference implementation reads and writes,
    what each schema requires, where each schema says it is served, and what the examples
    declare. A schema that moved without its address, or an example left behind, is a document
    that validates against nothing a reader can fetch."""
    from agiofit.match import SCHEMA_VERSION

    major, minor, _patch = SCHEMA_VERSION.split(".")
    schemas = sorted(SCHEMAS.glob("*.schema.json"))
    assert len(schemas) >= 3
    for path in schemas:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["properties"]["schema_version"] == {"const": SCHEMA_VERSION}, path.name
        assert schema["$id"] == f"https://agiofit.org/schemas/v{major}.{minor}/{path.name}"
    examples = sorted(EXAMPLES.glob("*.json"))
    assert len(examples) >= 3
    for path in examples:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["schema_version"] == SCHEMA_VERSION, path.name


def test_the_package_says_the_version_it_implements():
    """The package has a version of its own, in two places, and it is the version of the
    documents it reads: a package that calls itself 0.1 while refusing every 0.1 document says
    the wrong thing to whoever installs it."""
    import agiofit
    from agiofit.match import SCHEMA_VERSION

    declared = re.search(
        r'^version = "([^"]+)"$',
        (ROOT / "reference" / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    ).group(1)
    assert agiofit.__version__ == declared
    assert agiofit.__version__.split(".")[:2] == SCHEMA_VERSION.split(".")[:2]


def test_a_document_from_another_version_is_refused(mature, shirt):
    # Under a zero major, a minor bump is free to break: 0.2 moves fields 0.1 had
    # elsewhere. Reading a 0.1 document anyway would mean looking for values where they
    # no longer are and answering from whatever happened to be found.
    import copy

    for version in ("0.1.0", "0.3.0", "1.0.0", "", "abc"):
        garment = copy.deepcopy(shirt)
        garment["schema_version"] = version
        with pytest.raises(UnsupportedSchemaVersion):
            recommend(mature, garment)


def test_a_newer_patch_is_read_and_declared(mature, shirt):
    # A patch only fixes; what this code knows is still where it expects it. Going
    # ahead is safe, but the reader is owed the fact that part was ignored.
    import copy

    garment = copy.deepcopy(shirt)
    garment["schema_version"] = "0.2.4"
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
    # The reason is given, so the one for an answer that knows too little is not added beside it.
    assert not any("Not enough signal" in c for c in out["caveats"])


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

    # Only the zones a shirt has earn the unknown line. A shirt has no thigh, and must not be
    # marked down for a measurement its category does not have.
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
        "schema_version": "0.2.0",
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


def _full_at_the_waist(shirt):
    """A cut where the 40 and the 41 each get one thing wrong: the 40 is snug at the shoulders,
    and the 41, cut fuller at the waist than the closer waist the brand intends, is loose there.
    With the example's own grading the two sizes are one step apart at the waist and the answer
    turned on a few thousandths; the fuller 41 makes it turn on the flaw kept before."""
    import copy

    full = copy.deepcopy(shirt)
    full["cut_profile_id"] = "sartoria-esempio:POPLIN-EASY:2026"
    full["style_id"] = "POPLIN-EASY"
    full["style_name"] = "Easy Poplin Shirt"
    full["intended_ease"]["waist"] = {"min": 12, "max": 16, "unit": "cm"}
    for size in full["sizes"]:
        if size["size_label"] == "41":
            size["finished_measurements"]["waist_width"]["value"] = 58
    return full


def test_a_flaw_kept_before_counts_for_less_than_one_returned_before(mature, shirt):
    """The mature profile kept the 41 despite a roomy waist, and sent back two 40s for tight
    shoulders. On a cut where the 40 has snug shoulders and the 41 a loose waist, the kept
    compromise used to count for nothing, and the answer was the 40: the tight shoulders again."""
    import copy

    cut = _full_at_the_waist(shirt)
    report = recommend(mature, cut, disclosure_level="explained")
    assert report.recommended_size == "41"
    # The judgement is not softened: the waist is still reported as it is.
    waist = next(line for line in report.explanation if line.zone == "waist")
    assert waist.assessment == "too_loose"

    without = copy.deepcopy(mature)
    for item in without["history"]:
        item.pop("kept_despite", None)
    assert recommend(without, cut).recommended_size == "40"


def test_a_kept_flaw_teaches_only_the_direction_it_was_kept_in(mature, shirt):
    """kept_despite names a zone, not a direction. Without a verdict on that zone in the same
    entry there is nothing to learn, and a flaw the other way is not what was tolerated."""
    import copy

    cut = _full_at_the_waist(shirt)

    no_verdict = copy.deepcopy(mature)
    for item in no_verdict["history"]:
        kept = item.get("kept_despite") or []
        item["zone_feedback"] = [f for f in item.get("zone_feedback", []) if f["zone"] not in kept]
    assert recommend(no_verdict, cut).recommended_size == "40"

    other_way = copy.deepcopy(mature)
    for item in other_way["history"]:
        for verdict in item.get("zone_feedback", []):
            if verdict["zone"] in (item.get("kept_despite") or []):
                verdict["verdict"] = "snug"
    assert recommend(other_way, cut).recommended_size == "40"


def _with_preferences(profile, *preferences):
    """The profile with its preferences replaced by shirt ones, each (zone, preference, source,
    updated_at), taken whole. No strength is written, so each is a taste and none a constraint:
    these tests are about how far a preference moves a band, not about what it rules out."""
    import copy

    profile = copy.deepcopy(profile)
    profile["preferences"] = [
        {
            "category": "shirts",
            "zone": zone,
            "preference": preference,
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


def test_a_measurement_under_a_name_this_implementation_does_not_know_is_named(
    mature, cold, shirt
):
    """Written as "chest" instead of chest_circumference, the chest used to vanish: the answer
    said only that some zone had no matching measurement, and improve_by asked for the very
    measurement the person had just written. The name now appears where an explanation is
    sent. Not at result_only, where it would only tell the verifier what the profile holds, and
    never for an x_ extension, which the schema allows on purpose."""
    import copy

    def named(profile, level):
        out = recommend(profile, shirt, disclosure_level=level).to_json()
        return [c for c in out["caveats"] if "does not know" in c]

    renamed = copy.deepcopy(mature)
    measurements = renamed["body"]["measurements"]
    measurements["chest"] = measurements.pop("chest_circumference")
    measurements["x_torso_length"] = dict(measurements["chest"], value=70)

    said = named(renamed, "explained")
    assert len(said) == 1 and said[0].endswith(": chest.")
    assert named(renamed, "result_only") == []
    assert named(mature, "explained") == []

    # A profile whose only measurement is misnamed has nothing to compare at all.
    only = copy.deepcopy(cold)
    chest = mature["body"]["measurements"]["chest_circumference"]
    only["body"] = {"measurements": {"chest": chest}}
    assert named(only, "explained")


def test_a_never_shared_measurement_is_never_named(mature, shirt):
    """The mature profile keeps its hips to itself. Taken from memory, they used to come back at
    every level as "Re-measure with a tape: ..., hip_circumference, ...", telling the verifier
    that the profile holds them and how they were taken; and listing the whole body layer left
    every other name in place."""
    import copy

    def everything_said(profile, garment=shirt):
        said = []
        for level in ("result_only", "explained", "scoped", "full"):
            out = recommend(profile, garment, disclosure_level=level).to_json()
            said += out["caveats"] + out.get("improve_by", [])
        return " ".join(said)

    def mentions(text, key):
        return key in text or key.replace("_", " ") in text

    remembered = copy.deepcopy(mature)
    remembered["body"]["measurements"]["hip_circumference"]["source"] = "self_reported"
    # Trousers use the hips, so they are where a suggestion would ask for them again.
    assert not mentions(everything_said(remembered, _trousers()), "hip_circumference")
    assert mentions(everything_said(remembered), "arm_length")

    hidden = copy.deepcopy(mature)
    measurements = hidden["body"]["measurements"]
    measurements["hips"] = measurements.pop("hip_circumference")
    hidden["disclosure_defaults"]["never_share"] = ["hips"]
    assert not mentions(everything_said(hidden), "hips")

    whole = copy.deepcopy(mature)
    whole["disclosure_defaults"]["never_share"] = ["body"]
    said = everything_said(whole)
    for key in ("arm_length", "inseam", "thigh_circumference", "chest_circumference"):
        assert not mentions(said, key)


def test_a_preference_at_the_collar_moves_it_by_a_collar_not_by_a_chest(mature, shirt):
    """A preference used to move every girth by the same centimetres, so "relaxed" asked a collar
    for four more, where a centimetre is a whole size and the brand allows one and a half: every
    collar came out tight, and a "fitted" collar with the room the brand intends came out too
    loose. A preference now moves each zone by the scale a learned correction is taken at."""
    plain = _bands(_with_preferences(mature), shirt)
    relaxed = _bands(_with_preferences(mature, RELAXED), shirt)
    chest_moved = relaxed["chest"][0] - plain["chest"][0]
    neck_moved = relaxed["neck"][0] - plain["neck"][0]
    # Less than a collar size at the collar, the full step at the chest.
    assert 0 < neck_moved < 1.0 < chest_moved

    for preference, wrong in (
        ("relaxed", {"snug", "too_tight"}),
        ("oversized", {"snug", "too_tight"}),
        ("fitted", {"too_loose"}),
        ("very_fitted", {"too_loose"}),
    ):
        wish = ("neck", preference, "declared", "2026-09-01T00:00:00Z")
        report = recommend(_with_preferences(mature, wish), shirt, disclosure_level="explained")
        collar = next(line for line in report.explanation if line.zone == "neck")
        assert collar.assessment not in wrong, preference


def test_a_size_too_tight_where_it_cannot_be_let_out_is_not_named(mature, shirt):
    """A 46 cm neck closes no collar of this shirt, the largest being 43. The answer used to be
    the 42, at the confidence of a shirt that fits, and at result_only nothing said otherwise. A
    size too tight where a seam cannot be let out is no longer a candidate: when it is only some
    sizes, one of the others is named; when it is every size, none is, and the reason goes out
    at every level."""
    import copy

    def with_neck(cm):
        profile = copy.deepcopy(mature)
        profile["body"]["measurements"]["neck_circumference"]["value"] = cm
        return profile

    out = recommend(with_neck(46), shirt, disclosure_level="result_only").to_json()
    assert out["recommended_size"] is None
    assert any("cannot be let out" in c for c in out["caveats"])
    assert not any("Not enough signal" in c for c in out["caveats"])

    explained = recommend(with_neck(46), shirt, disclosure_level="explained").to_json()
    labels = {size["size_label"] for size in shirt["sizes"]}
    assert {alt["size_label"] for alt in explained["alternatives"]} == labels
    assert all(alt.get("note") for alt in explained["alternatives"])

    # At 43 cm only the 42 closes: it is named, and the others come back with the reason.
    out = recommend(with_neck(43), shirt, disclosure_level="explained").to_json()
    assert out["recommended_size"] == "42"
    noted = {alt["size_label"] for alt in out["alternatives"] if alt.get("note")}
    assert noted == {"39", "40", "41"}


def test_a_size_that_does_not_fit_elsewhere_is_named_only_as_the_closest(mature, shirt):
    """A 120 cm chest leaves the largest shirt no ease at all, and the 42 used to come out at
    0.80, with nothing said at result_only. The chest is not a critical zone of a shirt, so the
    size is still named, as the closest there is, but no surer than a cold start and with the
    reason at every level. A flaw the person has kept a garment despite does not count: the
    mature profile kept a shirt with a roomy waist, and a waist that is too loose leaves the
    answer as sure as it was."""
    import copy

    broad = copy.deepcopy(mature)
    broad["body"]["measurements"]["chest_circumference"]["value"] = 120
    out = recommend(broad, shirt, disclosure_level="result_only").to_json()
    assert out["recommended_size"] == "42"
    assert out["confidence"] <= 0.40
    assert any("not one that fits" in c for c in out["caveats"])

    slender = copy.deepcopy(mature)
    slender["body"]["measurements"]["waist_circumference"]["value"] = 74
    report = recommend(slender, shirt, disclosure_level="explained")
    waist = next(line for line in report.explanation if line.zone == "waist")
    assert waist.assessment == "too_loose"
    assert report.confidence > 0.40
    assert not any("not one that fits" in c for c in report.to_json()["caveats"])


def _constraint(profile, zone, preference, **fields):
    """The profile with one more shirt preference, declared and at full strength unless fields
    say otherwise. A field given as None is left out."""
    import copy

    profile = copy.deepcopy(profile)
    added = {
        "category": "shirts",
        "zone": zone,
        "preference": preference,
        "strength": 1.0,
        "source": "declared",
        "confidence": 0.8,
        "updated_at": "2026-09-01T00:00:00Z",
    }
    added.update(fields)
    profile["preferences"].append({k: v for k, v in added.items() if v is not None})
    return profile


def test_a_constraint_the_person_declared_rules_a_size_out(mature, shirt):
    """An app writes "I cannot wear anything tight at the chest" as a regular chest at full
    strength. Strength only scaled a shift, and a regular fit has none, so the line changed
    nothing: at a 112 cm chest, which no size of this shirt leaves room for, the answer was the
    closest size. A preference the person declared at full strength is now a constraint: a size
    that breaks it is not a candidate, and when every size does, none is named, with the reason
    at every level. Below full strength, inferred from history or with no strength written, a
    preference is a taste, and the closest size is named as before."""
    import copy

    broad = copy.deepcopy(mature)
    broad["body"]["measurements"]["chest_circumference"]["value"] = 112

    held = _constraint(broad, "chest", "regular")
    out = recommend(held, shirt, disclosure_level="result_only").to_json()
    assert out["recommended_size"] is None
    assert any("outside a limit the person has set" in c for c in out["caveats"])
    assert not any("Not enough signal" in c for c in out["caveats"])

    for taste in ({"strength": 0.5}, {"source": "inferred_from_history"}, {"strength": None}):
        out = recommend(_constraint(broad, "chest", "regular", **taste), shirt).to_json()
        assert out["recommended_size"] == "42", taste


def test_a_constraint_rules_out_what_its_preference_asks_against(mature, shirt):
    """A relaxed or oversized fit held as a constraint rules out tight, a fitted one loose, and a
    regular one both. On the slim variant the 41 and the 42 are too loose at the chest: a regular
    chest held as a constraint rules them out, and they come back with a reason that names
    neither the zone nor the preference, while a relaxed one leaves them in. Nor does a garment
    kept despite the flaw excuse it: the mature profile kept a shirt with a roomy waist, and at a
    74 cm waist, too loose in the 41, the 41 is named only while a fitted waist is a taste."""
    import copy

    slim = _slim(shirt)
    held = recommend(_constraint(mature, "chest", "regular"), slim, disclosure_level="explained")
    out = held.to_json()
    assert out["recommended_size"] not in (None, "41", "42")
    noted = {
        alt["size_label"]
        for alt in out["alternatives"]
        if alt.get("note") == "Outside a limit the person has set."
    }
    assert {"41", "42"} <= noted
    relaxed = recommend(
        _constraint(mature, "chest", "relaxed"), slim, disclosure_level="explained"
    ).to_json()
    assert relaxed["recommended_size"] == "41"
    assert not any(alt.get("note") for alt in relaxed["alternatives"])

    slender = copy.deepcopy(mature)
    slender["body"]["measurements"]["waist_circumference"]["value"] = 74
    held = recommend(_constraint(slender, "waist", "fitted"), shirt).to_json()
    assert held["recommended_size"] != "41"
    taste = recommend(_constraint(slender, "waist", "fitted", strength=0.5), shirt).to_json()
    assert taste["recommended_size"] == "41"


def test_a_date_that_cannot_be_read_stops_the_answer(mature, shirt):
    """A date that could not be read used to count as no age at all, so measurements taken five
    years earlier and written the Italian way, 14/03/2021, counted as taken that day, and the
    answer came out surer than it was, without a word. Today is no less an invented age than any
    other: a date this implementation reads and cannot read now stops the answer, naming the
    field. Dates are read as RFC 3339 writes them, the two letters in either case, the same on
    every Python this package supports, and a date nothing here reads stops nothing."""
    import copy

    def dated(when):
        profile = copy.deepcopy(mature)
        profile["body"]["measurements"]["waist_circumference"]["observed_at"] = when
        return profile

    for when in ("14/03/2021", "2021-03-14", "2021-03-14T18:00:00+0200", "yesterday"):
        with pytest.raises(UnreadableDate, match="waist_circumference.observed_at"):
            recommend(dated(when), shirt)

    def all_taken(when):
        profile = copy.deepcopy(mature)
        for measurement in profile["body"]["measurements"].values():
            measurement["observed_at"] = when
        return recommend(profile, shirt).confidence

    five_years = all_taken("2021-03-14T18:00:00Z")
    assert all_taken("2021-03-14t18:00:00z") == five_years
    assert all_taken("2021-03-14T20:00:00.5+02:00") == five_years
    assert five_years < recommend(mature, shirt).confidence

    # Read as moments, offsets included: of two preferences the later decides, and 06:00 at five
    # hours behind UTC is later than 10:00 in UTC.
    later = ("chest", "regular", "declared", "2026-09-01T06:00:00-05:00")
    earlier = ("chest", "relaxed", "declared", "2026-09-01T10:00:00Z")
    both = _bands(_with_preferences(mature, earlier, later), shirt)
    assert both == _bands(_with_preferences(mature, later), shirt)

    missing = copy.deepcopy(mature)
    del missing["body"]["measurements"]["neck_circumference"]["observed_at"]
    with pytest.raises(UnreadableDate, match="neck_circumference.observed_at"):
        recommend(missing, shirt)

    outcome = copy.deepcopy(mature)
    outcome["history"][0]["occurred_at"] = "yesterday"
    with pytest.raises(UnreadableDate, match=r"history\[0\]\.occurred_at"):
        recommend(outcome, shirt)

    wish = copy.deepcopy(mature)
    wish["preferences"][0]["updated_at"] = "last winter"
    with pytest.raises(UnreadableDate, match=r"preferences\[0\]\.updated_at"):
        recommend(wish, shirt)

    unread = dict(copy.deepcopy(mature), updated_at="yesterday")
    assert recommend(unread, shirt).confidence == recommend(mature, shirt).confidence


def test_the_unit_a_person_prefers_to_see_changes_nothing(mature, shirt):
    """units is the unit the person prefers to see, not the one the values are written in: each
    measurement carries its own. A profile whose units say inches while its measurements are in
    centimetres is valid, and a consumer that trusted units would read a 100 cm chest as 254 cm.
    Here it changes nothing, at any level, and nor does units.mass, which names a unit for
    nothing."""
    import copy

    shown_in_inches = copy.deepcopy(mature)
    shown_in_inches["units"] = {"length": "in", "mass": "lb"}
    for level in ("result_only", "explained", "scoped", "full"):
        plain = recommend(mature, shirt, disclosure_level=level).to_json()
        assert recommend(shown_in_inches, shirt, disclosure_level=level).to_json() == plain, level


def test_morphology_is_descriptive_here(mature, shirt):
    """morphology says what measurements miss, sloped shoulders or a long torso, but there is no
    defensible way to turn "above average" into centimetres of ease, and this implementation does
    not try: the most extreme traits change nothing, at any level. A trait still carries its
    source, as every value does, and the examples use only sources that can say how a trait was
    judged."""
    import copy

    extreme = copy.deepcopy(mature)
    extreme["body"]["morphology"] = {
        trait: {"value": "much_above_average", "source": "self_reported"}
        for trait in ("shoulder_slope", "torso_length", "posture", "limb_length")
    }
    for level in ("result_only", "explained", "scoped", "full"):
        plain = recommend(mature, shirt, disclosure_level=level).to_json()
        assert recommend(extreme, shirt, disclosure_level=level).to_json() == plain, level

    judged = {"self_reported", "scan_3d", "inferred_from_history", "imported_from_retailer"}
    for name in ("profile-mature.json", "profile-cold-start.json"):
        profile = json.loads((EXAMPLES / name).read_text())
        for trait in ((profile.get("body") or {}).get("morphology") or {}).values():
            assert trait.get("source") in judged, name


def test_a_reference_to_a_cut_profile_is_read_without_the_spaces_around_it(mature, shirt):
    """A size sent back and recorded against "sartoria-esempio:OXF-CLASSIC:2026 ", with a space
    at the end, used to point at no document, and the size came back recommended. Spaces around
    an identifier do not make another one. Its capitals do, since an identifier may be a URL or a
    key where they count, and an empty reference points at nothing. The same return written
    twice, once with the space, is one event."""
    import copy

    first = recommend(mature, shirt).to_json()["recommended_size"]
    cut_id = shirt["cut_profile_id"]

    def returned_as(*references):
        profile = copy.deepcopy(mature)
        for reference in references:
            entry = _returned(shirt, first)
            entry["garment_ref"].update(cut_profile_id=reference, category="shirts")
            profile["history"].append(entry)
        return recommend(profile, shirt, disclosure_level="explained").to_json()

    def noted_as_returned(report):
        return {
            alt["size_label"]
            for alt in report["alternatives"]
            if alt.get("note") == "Already returned for this garment."
        }

    exact = returned_as(cut_id)
    assert noted_as_returned(exact) == {first}
    assert returned_as(cut_id + " ") == exact
    assert returned_as(" " + cut_id + " ") == exact
    for elsewhere in (cut_id.upper(), ""):
        assert noted_as_returned(returned_as(elsewhere)) == set(), elsewhere
    assert returned_as(cut_id, cut_id + " ") == exact

    # The garment's own identifier is read the same way.
    spaced = dict(copy.deepcopy(shirt), cut_profile_id=cut_id + " ")
    history = copy.deepcopy(mature)
    history["history"].append(_returned(shirt, first))
    report = recommend(history, spaced, disclosure_level="explained").to_json()
    assert noted_as_returned(report) == {first}


def test_based_on_counts_what_the_answer_used(mature, cold, shirt):
    """based_on counted what the profile holds: seven measurements and four preferences for a
    shirt compared on five and decided by two, as if the inseam, or a preference about trousers,
    had a part in it. At every level, that told the verifier how full the profile is. It counts
    what the answer rests on: the measurements compared, the preferences that decided a zone
    compared, the purchases read, and whether what they taught moved a zone compared. A cold
    start rests on the purchases of this brand it was derived from, and on nothing else."""
    import copy

    assert recommend(mature, shirt).based_on == {
        "body_signals": 5,
        "preference_signals": 2,
        "history_signals": 3,
        "brand_specific_history_signals": 3,
        "learned_offset_applied": True,
    }

    # A preference that decides no zone is not counted: the declared one decides overall.
    undecided = copy.deepcopy(mature)
    overall = next(
        p for p in undecided["preferences"] if (p["category"], p["zone"]) == ("shirts", "overall")
    )
    undecided["preferences"].append(
        dict(overall, preference="relaxed", source="inferred_from_history")
    )
    assert recommend(undecided, shirt).based_on["preference_signals"] == 2

    # Without the shoulders measured, neither the preference about them nor what the history
    # taught about them is used.
    unmeasured = copy.deepcopy(mature)
    del unmeasured["body"]["measurements"]["shoulder_width"]
    assert recommend(unmeasured, shirt).based_on == {
        "body_signals": 4,
        "preference_signals": 1,
        "history_signals": 3,
        "brand_specific_history_signals": 3,
        "learned_offset_applied": False,
    }

    alone = {
        "body_signals": 0,
        "preference_signals": 0,
        "history_signals": 1,
        "brand_specific_history_signals": 1,
        "learned_offset_applied": False,
    }
    assert recommend(cold, shirt).based_on == alone
    # A return to another brand, and a purchase of this one labelled in another size system,
    # are not what the answer was derived from.
    elsewhere = copy.deepcopy(cold)
    other_brand = copy.deepcopy(cold["history"][0])
    other_brand["garment_ref"]["brand"] = "SomeoneElse"
    other_brand["outcome"] = "returned_too_small"
    other_system = copy.deepcopy(cold["history"][0])
    other_system["garment_ref"].update(size_label="16", size_system="US")
    elsewhere["history"] += [other_brand, other_system]
    assert recommend(elsewhere, shirt).based_on == alone


def test_a_layer_in_never_share_leaves_its_counts_out(mature, shirt):
    """With history in never_share, every report still told the verifier how many purchases
    the person had made in this category, and how many of this brand. A layer the person lists
    leaves its counts out of based_on, at every level, rather than give them as zero, which
    would say that nothing of the kind was used, and a measurement listed alone is not counted.
    The answer is computed the same: what the list governs is what leaves."""
    import copy

    plain = recommend(mature, shirt)
    counts = plain.based_on
    layers = {
        "body": {"body_signals"},
        "preferences": {"preference_signals"},
        "history": {"history_signals", "brand_specific_history_signals", "learned_offset_applied"},
    }
    for layer, keys in layers.items():
        profile = copy.deepcopy(mature)
        profile["disclosure_defaults"]["never_share"] = [layer]
        for level in ("result_only", "explained", "scoped", "full"):
            report = recommend(profile, shirt, disclosure_level=level)
            assert (report.recommended_size, report.confidence) == (
                plain.recommended_size,
                plain.confidence,
            )
            left = {key: value for key, value in counts.items() if key not in keys}
            assert report.based_on == left, (layer, level)
            shown = None if level == "result_only" else left
            assert report.to_json().get("based_on") == shown, (layer, level)

    chest = copy.deepcopy(mature)
    chest["disclosure_defaults"]["never_share"] = ["chest_circumference"]
    assert recommend(chest, shirt).based_on == dict(counts, body_signals=4)


def _said(out):
    """Every sentence a serialised report says: caveats, suggestions and notes."""
    return (
        out["caveats"]
        + out.get("improve_by", [])
        + [alt["note"] for alt in out.get("alternatives", []) if "note" in alt]
        + [line["note"] for line in out.get("explanation", []) if "note" in line]
    )


def test_a_layer_in_never_share_is_not_told_through_the_reasoning(mature, cold, shirt):
    """With the history in never_share and the 41 sent back, every report still said "Sizes
    already returned for this exact garment were removed from the candidates: 41.", at
    result_only too, and a constraint or measurements estimated from size labels were told the
    same way. A caveat or a note about a layer the person listed whole does not leave, and a size
    set aside for such a reason leaves the alternatives with it: its score, often the highest,
    would say that it was set aside. The answer is the same. From explained up one sentence says that
    part of the reasoning was kept back, and at result_only nothing, as for the zones."""
    import copy

    returned = copy.deepcopy(mature)
    returned["history"].append(_returned(shirt, "41"))
    every_size = copy.deepcopy(mature)
    every_size["history"] += [_returned(shirt, size["size_label"]) for size in shirt["sizes"]]
    broad = copy.deepcopy(mature)
    broad["body"]["measurements"]["chest_circumference"]["value"] = 112
    estimated = copy.deepcopy(mature)
    for key in ("shoulder_width", "neck_circumference"):
        estimated["body"]["measurements"][key]["source"] = "estimated_from_size_labels"
    wide_neck = copy.deepcopy(mature)
    wide_neck["body"]["measurements"]["neck_circumference"]["value"] = 46
    wide_neck_returned = copy.deepcopy(wide_neck)
    wide_neck_returned["history"].append(_returned(shirt, "42"))
    wide_chest = copy.deepcopy(mature)
    wide_chest["body"]["measurements"]["chest_circumference"]["value"] = 120
    no_arm = copy.deepcopy(mature)
    del no_arm["body"]["measurements"]["arm_length"]

    cases = [
        ("history", returned, "already returned"),
        ("history", every_size, "already been returned"),
        ("history", cold, "purchase"),
        ("history", wide_neck_returned, "every other size"),
        ("preferences", _constraint(broad, "chest", "regular"), "limit the person has set"),
        ("preferences", _constraint(mature, "chest", "relaxed"), "limit the person has set"),
        ("body", estimated, "estimated from size labels"),
        ("body", wide_neck, "cannot be let out"),
        ("body", _constraint(mature, "chest", "relaxed"), "limit the person has set"),
        ("body", wide_chest, "not one that fits"),
        ("body", no_arm, "no matching"),
        ("body", cold, "profile has no measurements"),
    ]
    notes = {
        "history": {"Already returned for this garment."},
        "preferences": {"Outside a limit the person has set."},
        "body": {"Outside a limit the person has set.", "Too tight where it cannot be let out."},
    }
    kept_back = "Some of the reasoning is not given here, at the person's request."
    zones = "Some zones are not explained here, at the person's request."
    for layer, profile, told in cases:
        said = _said(recommend(profile, shirt, disclosure_level="full").to_json())
        assert any(told in sentence.lower() for sentence in said), told
        listed = copy.deepcopy(profile)
        listed.setdefault("disclosure_defaults", {})["never_share"] = [layer]
        for level in ("result_only", "explained", "scoped", "full"):
            plain = recommend(profile, shirt, disclosure_level=level)
            held = recommend(listed, shirt, disclosure_level=level)
            assert (held.recommended_size, held.confidence) == (
                plain.recommended_size,
                plain.confidence,
            ), (told, level)
            plain_out, held_out = plain.to_json(), held.to_json()
            assert not any(told in sentence.lower() for sentence in _said(held_out)), (told, level)
            assert [alt["size_label"] for alt in held_out.get("alternatives", [])] == [
                alt["size_label"]
                for alt in plain_out.get("alternatives", [])
                if alt.get("note") not in notes[layer]
            ], (told, level)
            assert (kept_back in held_out["caveats"]) == (level != "result_only"), (told, level)
            assert kept_back not in plain_out["caveats"]
            if layer != "body":
                assert zones not in held_out["caveats"], (told, level)


def test_a_history_kept_private_is_not_asked_for(mature, shirt):
    """"Record how past garments actually fitted" was offered only when the history is empty, so
    with the history in never_share its absence told the verifier that there is one. It is not
    offered when the history is listed, whether it is empty or not."""
    import copy

    def asks(profile):
        return any("past garments" in s for s in recommend(profile, shirt).improve_by)

    empty = copy.deepcopy(mature)
    empty["history"] = []
    assert asks(empty) and not asks(mature)
    for profile in (empty, mature):
        listed = copy.deepcopy(profile)
        listed["disclosure_defaults"]["never_share"] = ["history"]
        assert not asks(listed)


def test_who_recorded_an_outcome_does_not_change_its_weight(mature, shirt):
    """Most of the mature profile's history came from a shop's export. The same outcomes written
    by the person, or by a marketplace, say the same thing about the same garments, and the
    reports are the same at every level: who recorded an outcome is not how much it counts, as
    who published a Cut Profile is not."""
    import copy

    for source in ("user", "retailer_import", "marketplace_import"):
        recorded = copy.deepcopy(mature)
        for entry in recorded["history"]:
            entry["source"] = source
        for level in ("result_only", "explained", "scoped", "full"):
            plain = recommend(mature, shirt, disclosure_level=level).to_json()
            assert recommend(recorded, shirt, disclosure_level=level).to_json() == plain, (
                source,
                level,
            )


def test_an_import_reference_never_leaves(mature, shirt):
    """import_ref names a batch, so that the person can delete it in one action. One written
    from a shop's customer code, which the specification forbids, still never reaches a report,
    at any level, and changes nothing in it."""
    import copy

    coded = copy.deepcopy(mature)
    for entry in coded["history"]:
        entry["import_ref"] = "shop-customer-8812345"
    for level in ("result_only", "explained", "scoped", "full"):
        out = recommend(coded, shirt, disclosure_level=level).to_json()
        assert "8812345" not in json.dumps(out), level
        assert out == recommend(mature, shirt, disclosure_level=level).to_json(), level


def test_a_band_leaves_only_at_full_and_never_with_a_private_layer(mature, shirt):
    """The band a zone was judged against is the garment's, moved by the person's preferences and
    by what their history taught, and the shop knows the band it published. At scoped, Luca's
    shoulders came out at 0.5 to 2.5 cm against the 0 to 2 of the Oxford, which told it about the
    shirts he sent back; with relaxed shirts in a profile that keeps its preferences private, the
    chest came out at 14.2 to 22.2 against 12 to 20. scoped promises the measurements a garment
    needs, so the band leaves only at full, and with preferences or history in never_share at no
    level, from no zone. The ease and the judgement stay."""
    import copy

    def lines(profile, level):
        return recommend(profile, shirt, disclosure_level=level).to_json()["explanation"]

    assert all("ease_cm" in l and "intended_ease_cm" not in l for l in lines(mature, "scoped"))
    shoulders = next(l for l in lines(mature, "full") if l["zone"] == "shoulders")
    assert shoulders["intended_ease_cm"] == [0.5, 2.5]

    relaxed = copy.deepcopy(mature)
    for pref in relaxed["preferences"]:
        if (pref["category"], pref["zone"]) == ("shirts", "overall"):
            pref["preference"] = "relaxed"
    chest = next(l for l in lines(relaxed, "full") if l["zone"] == "chest")
    assert chest["intended_ease_cm"] == [14.2, 22.2]

    kept_back = "Some of the reasoning is not given here, at the person's request."
    for layer in ("preferences", "history"):
        listed = copy.deepcopy(relaxed)
        listed["disclosure_defaults"]["never_share"] = [layer]
        for level in ("scoped", "full"):
            out = recommend(listed, shirt, disclosure_level=level).to_json()
            plain = recommend(relaxed, shirt, disclosure_level=level).to_json()
            assert all("intended_ease_cm" not in l for l in out["explanation"]), (layer, level)
            assert [(l["zone"], l["assessment"], l["ease_cm"]) for l in out["explanation"]] == [
                (l["zone"], l["assessment"], l["ease_cm"]) for l in plain["explanation"]
            ], (layer, level)
            assert (kept_back in out["caveats"]) == (level == "full"), (layer, level)


def test_each_level_carries_only_what_it_may(mature, cold, shirt):
    """spec/04 says what a report may carry at each level: no explanation and no alternatives at
    result_only, no ease at explained, no band at scoped. The schema of this version checks none
    of it, and a report from another producer that breaks the rule still validates, so the rule
    is checked here as it is written, on reports of every kind, at every level."""
    import copy

    returned = copy.deepcopy(mature)
    returned["history"].append(_returned(shirt, "41"))
    wide_neck = copy.deepcopy(mature)
    wide_neck["body"]["measurements"]["neck_circumference"]["value"] = 46
    profiles = (mature, cold, returned, wide_neck, _constraint(mature, "chest", "relaxed"))
    for profile in profiles:
        for level in ("result_only", "explained", "scoped", "full"):
            out = recommend(profile, shirt, disclosure_level=level).to_json()
            lines = out.get("explanation", [])
            if level == "result_only":
                assert not {"explanation", "alternatives", "based_on", "improve_by"} & set(out)
            if level in ("result_only", "explained"):
                assert not any("ease_cm" in line for line in lines), level
            if level != "full":
                assert not any("intended_ease_cm" in line for line in lines), level


def test_result_only_says_what_kind_of_answer_it_is(mature, shirt):
    """result_only carried what the answer rests on and what would improve it, and the same counts
    and the same suggestion, reaching every shop Luca asked for a shirt, were nearly a signature.
    They describe the profile, not the answer: they stay on the report, for the person, and leave
    from explained up. The caveats stay, because they say what kind of answer it is."""
    import copy

    report = recommend(mature, shirt, disclosure_level="result_only")
    out = report.to_json()
    assert "based_on" not in out and "improve_by" not in out
    assert report.based_on and report.improve_by
    for level in ("explained", "scoped", "full"):
        out = recommend(mature, shirt, disclosure_level=level).to_json()
        assert (out["based_on"], out["improve_by"]) == (report.based_on, report.improve_by), level

    wide_neck = copy.deepcopy(mature)
    wide_neck["body"]["measurements"]["neck_circumference"]["value"] = 46
    out = recommend(wide_neck, shirt, disclosure_level="result_only").to_json()
    assert any("cannot be let out" in caveat for caveat in out["caveats"])


def test_a_zone_the_garment_leaves_out_is_named_and_not_blamed_on_the_profile(mature, shirt):
    """A shirt that did not publish its shoulders was reported as "Some zones could not be
    evaluated because the profile has no matching measurement.", though the profile had them, and
    the zone went unnamed, which requirement 7 of spec/03 asks against. The garment's own gaps are
    named at every level. A measurement the profile lacks is named only where an explanation is
    sent: at result_only its name would tell the verifier what the profile lacks."""
    import copy

    without = copy.deepcopy(shirt)
    for size in without["sizes"]:
        del size["finished_measurements"]["shoulder_width"]
    for level in ("result_only", "explained"):
        caveats = recommend(mature, without, disclosure_level=level).to_json()["caveats"]
        assert any("garment does not publish" in c and "shoulders" in c for c in caveats), level
        assert not any("profile has no matching measurement" in c for c in caveats), level

    no_neck = copy.deepcopy(mature)
    del no_neck["body"]["measurements"]["neck_circumference"]
    caveats = recommend(no_neck, shirt, disclosure_level="result_only").to_json()["caveats"]
    assert any("profile has no matching measurement" in c for c in caveats)
    assert not any("neck" in c for c in caveats)
    out = recommend(no_neck, shirt, disclosure_level="explained").to_json()
    assert [line["zone"] for line in out["explanation"] if line["assessment"] == "unknown"] == [
        "neck"
    ]


def test_a_suggestion_asks_only_for_what_the_garment_uses(mature, cold, shirt):
    """improve_by went through the whole vocabulary in alphabetical order. For a shirt it asked
    Luca for his thigh and to measure his inseam again, which no shirt uses, and asked a new
    profile for its arm, chest and hips, leaving out the neck and the shoulders, the two zones a
    shirt cannot be let out at. It asks for what this garment uses, critical zones first."""
    assert recommend(mature, shirt).improve_by == ["Re-measure with a tape: arm_length."]
    assert recommend(cold, shirt).improve_by == [
        "Add a measurement for neck circumference.",
        "Add a measurement for shoulder width.",
        "Add a measurement for arm length.",
    ]


# --------------------------------------------------------------------- the waist of trousers


def _jeans():
    """Two sizes of a jean laid flat, apart only at the waist: the hips are the same in both, so
    the waist alone decides between them."""
    return {
        "schema_version": "0.2.0",
        "cut_profile_id": "test-jeans-waist",
        "category": "jeans",
        "size_system": "EU",
        "measurement_method": "flat_laid",
        "provenance": {"published_by": "brand"},
        "sizes": [
            {
                "size_label": label,
                "finished_measurements": {
                    "waist_width": {"value": waist, "unit": "cm"},
                    "hip_width": {"value": 55, "unit": "cm"},
                },
            }
            for label, waist in (("46", 44.5), ("48", 47))
        ],
    }


def _worn_low(mature):
    """The mature profile with a natural waist of 88 cm and trousers worn at 94, keeping nothing
    private, so that every zone can be read in the explanation."""
    import copy

    profile = copy.deepcopy(mature)
    measurements = profile["body"]["measurements"]
    measurements["waist_circumference"]["value"] = 88
    measurements["trouser_waist_circumference"]["value"] = 94
    profile["disclosure_defaults"]["never_share"] = []
    return profile


def test_a_waistband_is_compared_with_where_trousers_are_worn(mature, monkeypatch):
    """The waist of a jean was judged against the natural waist, the one a shirt is cut for.
    Laid flat at 44.5 cm, a waistband is 89 cm round: five short of where this person wears
    trousers, and one more than the natural waist, so it came out as cut, and the jean that does
    not close was the one recommended."""
    profile = _worn_low(mature)
    report = recommend(profile, _jeans())
    assert report.recommended_size == "48"
    waist = next(line for line in report.explanation if line.zone == "waist")
    assert waist.ease_cm == 0.0, "47 laid flat is 94 round, against 94"

    # The counterproof: compared with the natural waist, as before, the smaller one wins.
    monkeypatch.setattr("agiofit.mapping.BODY_KEY_BY_CATEGORY", {})
    assert recommend(profile, _jeans()).recommended_size == "46"


def test_without_a_trouser_waist_a_waistband_is_not_judged(mature):
    """Falling back on the natural waist would bring back, without a word, the error the
    trouser waist corrects. Without one, the waist of a jean is left unjudged, as a zone without
    its measurement always is; it is critical, so it still counts against the answer, and the
    person is asked for it."""
    import copy

    profile = _worn_low(mature)
    without = copy.deepcopy(profile)
    del without["body"]["measurements"]["trouser_waist_circumference"]

    report = recommend(without, _jeans())
    waist = next(line for line in report.explanation if line.zone == "waist")
    assert waist.assessment == "unknown" and waist.critical and waist.ease_cm is None
    assert report.confidence < recommend(profile, _jeans()).confidence

    # Not judged on the natural waist in any way: moving it changes nothing at all.
    elsewhere = copy.deepcopy(without)
    elsewhere["body"]["measurements"]["waist_circumference"]["value"] = 120
    for level in ("result_only", "explained", "scoped", "full"):
        assert (
            recommend(elsewhere, _jeans(), disclosure_level=level).to_json()
            == recommend(without, _jeans(), disclosure_level=level).to_json()
        ), level

    out = recommend(without, _jeans(), disclosure_level="explained").to_json()
    assert "Add a measurement for trouser waist circumference." in out["improve_by"]


def test_a_trouser_waist_kept_private_leaves_the_jeans_and_not_the_shirt(mature, shirt):
    """A zone goes with the measurement it is compared against. Kept private, the trouser waist
    takes the waist out of every explanation of a jean, and is never named or counted; the
    waist of a shirt, judged on the natural waist, stays where it is. The measurement still
    counts towards the answer."""
    profile = _worn_low(mature)
    profile["disclosure_defaults"]["never_share"] = ["trouser_waist_circumference"]

    for level in ("explained", "scoped", "full"):
        jeans = recommend(profile, _jeans(), disclosure_level=level).to_json()
        zones = {line["zone"]: line["assessment"] for line in jeans["explanation"]}
        assert "waist" not in zones, level
        # The thigh and the inseam, which these jeans do not publish, are lines of their own.
        assert {zone for zone, verdict in zones.items() if verdict != "unknown"} == {"hip"}, level
        assert jeans["based_on"]["body_signals"] == 1, level
        shirts = recommend(profile, shirt, disclosure_level=level).to_json()
        assert "waist" in {line["zone"] for line in shirts["explanation"]}, level

    for level in ("result_only", "explained", "scoped", "full"):
        said = json.dumps(recommend(profile, _jeans(), disclosure_level=level).to_json())
        assert "trouser_waist" not in said and "trouser waist" not in said, level

    assert recommend(profile, _jeans()).recommended_size == "48"


def test_how_sure_an_answer_about_a_jean_is_rests_on_the_trouser_waist(mature):
    """How far an answer can lean on its measurements, and how far label estimates cap it, are
    judged on the measurements compared. For a jean that is the trouser waist: one estimated from
    size labels makes the answer less sure, and a natural waist estimated from them changes
    nothing, neither the confidence nor what the caveats say."""
    import copy

    profile = _worn_low(mature)
    base = recommend(profile, _jeans(), disclosure_level="full").to_json()

    natural = copy.deepcopy(profile)
    natural["body"]["measurements"]["waist_circumference"]["source"] = "estimated_from_size_labels"
    assert recommend(natural, _jeans(), disclosure_level="full").to_json() == base

    worn = copy.deepcopy(profile)
    worn["body"]["measurements"]["trouser_waist_circumference"]["source"] = (
        "estimated_from_size_labels"
    )
    assert recommend(worn, _jeans()).confidence < base["confidence"]


def test_the_trouser_waist_is_a_name_this_implementation_knows(mature, shirt):
    """Only trousers and jeans read the trouser waist, but the name is known whatever the
    garment: no answer lists it among the names this implementation does not know, and a date on
    it that cannot be read stops the answer for a shirt, as one on the inseam, which no shirt
    reads either, already did."""
    import copy

    for garment in (shirt, _jeans()):
        out = recommend(mature, garment, disclosure_level="explained").to_json()
        assert not any("does not know" in c for c in out["caveats"])

    for key in ("trouser_waist_circumference", "inseam"):
        profile = copy.deepcopy(mature)
        profile["body"]["measurements"][key]["observed_at"] = "14/03/2026"
        with pytest.raises(UnreadableDate, match=key + r"\.observed_at"):
            recommend(profile, shirt)


def test_the_trouser_waist_changes_nothing_for_a_shirt(mature, shirt):
    """A shirt is judged on the natural waist, as it always was: the example profile gives the
    same report at every level with its trouser waist and without it."""
    import copy

    without = copy.deepcopy(mature)
    del without["body"]["measurements"]["trouser_waist_circumference"]
    for level in ("result_only", "explained", "scoped", "full"):
        assert (
            recommend(mature, shirt, disclosure_level=level).to_json()
            == recommend(without, shirt, disclosure_level=level).to_json()
        ), level


# --------------------------------------------------------------------- what a garment leaves out

STRETCH_ASSUMED = "does not say whether its fabric stretches"
TOLERANCE_ASSUMED = "does not declare a production tolerance"


def _assumed(out):
    """Which of the two assumptions a serialised report says it made."""
    return [
        phrase
        for phrase in (STRETCH_ASSUMED, TOLERANCE_ASSUMED)
        if any(phrase in caveat for caveat in out["caveats"])
    ]


def test_a_garment_that_leaves_out_its_fabric_or_its_tolerance_is_told_and_counted(mature, shirt):
    """Without its fabric, or without its production tolerance, the example shirt used to get the
    answer and the confidence of the shirt that declares both, judged rigid and within 1 cm
    without a word. The judgement is the same, since rigid and 1 cm are what the example
    declares, but each assumption is said, at every level, and costs 0.03."""
    import copy

    base = recommend(mature, shirt)
    no_fabric = copy.deepcopy(shirt)
    del no_fabric["fabric"]
    no_tolerance = copy.deepcopy(shirt)
    del no_tolerance["production_tolerance"]
    neither = copy.deepcopy(no_fabric)
    del neither["production_tolerance"]

    cases = (
        (shirt, [], 0.0),
        (no_fabric, [STRETCH_ASSUMED], 0.03),
        (no_tolerance, [TOLERANCE_ASSUMED], 0.03),
        (neither, [STRETCH_ASSUMED, TOLERANCE_ASSUMED], 0.06),
    )
    for garment, assumed, cost in cases:
        report = recommend(mature, garment)
        assert report.confidence == pytest.approx(base.confidence - cost), assumed
        assert report.explanation == base.explanation, "the calculation is the one of before"
        for level in ("result_only", "explained", "scoped", "full"):
            out = recommend(mature, garment, disclosure_level=level).to_json()
            assert _assumed(out) == assumed, (assumed, level)

    # Without its ease bands, as the builder writes a shirt for its owner, the answer is at the
    # cap of what category defaults cost already, and the two assumptions cost on top of it.
    bandless = copy.deepcopy(shirt)
    del bandless["intended_ease"]
    bare = copy.deepcopy(bandless)
    del bare["fabric"], bare["production_tolerance"]
    expected = recommend(mature, bandless).confidence - 0.06
    assert recommend(mature, bare).confidence == pytest.approx(expected)


def test_a_fabric_declared_rigid_is_not_a_fabric_nobody_described(mature, shirt):
    """What is undeclared is whether the fabric gives across: by class, or by a percentage
    across. A shirt that says it does not stretch is a shirt about which that is known; one that
    gives its composition, or how far it stretches lengthwise, has still not said it."""
    import copy

    base = recommend(mature, shirt).confidence
    for fabric, assumed in (
        ({"stretch_class": "none"}, []),
        ({"stretch_pct": {"horizontal": 0}}, []),
        ({"composition": "100% cotton"}, [STRETCH_ASSUMED]),
        ({"stretch_pct": {"vertical": 4}}, [STRETCH_ASSUMED]),
    ):
        garment = copy.deepcopy(shirt)
        garment["fabric"] = fabric
        report = recommend(mature, garment)
        assert _assumed(report.to_json()) == assumed, fabric
        assert report.confidence == pytest.approx(base - 0.03 * len(assumed)), fabric


def test_a_tolerance_given_measurement_by_measurement_is_a_declared_one(mature, shirt):
    """A garment without a production tolerance assumes 1 cm only for the measurements it
    compares without a tolerance of their own. With one on every measurement nothing is
    assumed; a measurement that was not compared, because the profile has nothing to compare it
    with, assumes nothing either."""
    import copy

    each = copy.deepcopy(shirt)
    del each["production_tolerance"]
    for size in each["sizes"]:
        for measurement in size["finished_measurements"].values():
            measurement.setdefault("tolerance", 1.0)
    report = recommend(mature, each)
    assert _assumed(report.to_json()) == []
    assert report.confidence == recommend(mature, shirt).confidence

    one_left = copy.deepcopy(each)
    del one_left["sizes"][0]["finished_measurements"]["chest_width"]["tolerance"]
    assert _assumed(recommend(mature, one_left).to_json()) == [TOLERANCE_ASSUMED]

    # The sleeves without a tolerance, and a profile without the arm to compare them with.
    sleeves = copy.deepcopy(each)
    for size in sleeves["sizes"]:
        del size["finished_measurements"]["sleeve_length"]["tolerance"]
    armless = copy.deepcopy(mature)
    del armless["body"]["measurements"]["arm_length"]
    assert _assumed(recommend(armless, sleeves).to_json()) == []
    assert _assumed(recommend(mature, sleeves).to_json()) == [TOLERANCE_ASSUMED]


def test_what_a_garment_leaves_out_counts_only_where_it_was_assumed(mature, cold, shirt):
    """A cold start compares nothing of the garment, so it assumes nothing about it: the same
    report, word for word, for a shirt that declares neither its fabric nor its tolerance. The
    fabric changes only a girth, so an answer that compared lengths alone assumed nothing about
    it either, until a girth is compared."""
    import copy

    neither = copy.deepcopy(shirt)
    del neither["fabric"], neither["production_tolerance"]
    for level in ("result_only", "explained", "scoped", "full"):
        assert (
            recommend(cold, neither, disclosure_level=level).to_json()
            == recommend(cold, shirt, disclosure_level=level).to_json()
        ), level

    no_fabric = copy.deepcopy(shirt)
    del no_fabric["fabric"]
    lengths = copy.deepcopy(mature)
    measurements = lengths["body"]["measurements"]
    lengths["body"]["measurements"] = {
        key: measurements[key] for key in ("shoulder_width", "arm_length")
    }
    assert _assumed(recommend(lengths, no_fabric).to_json()) == []
    lengths["body"]["measurements"]["chest_circumference"] = measurements["chest_circumference"]
    assert _assumed(recommend(lengths, no_fabric).to_json()) == [STRETCH_ASSUMED]


def test_an_assumption_is_said_where_a_cap_hides_what_it_costs(mature, shirt):
    """Held to the cold start ceiling, an answer about a shirt it calls too tight at the chest
    is at 0.40 whatever the garment declares, so the 0.06 of two assumptions does not show. The
    two are said all the same, at every level."""
    import copy

    broad = copy.deepcopy(mature)
    broad["body"]["measurements"]["chest_circumference"]["value"] = 120
    neither = copy.deepcopy(shirt)
    del neither["fabric"], neither["production_tolerance"]

    assert recommend(broad, shirt).confidence == 0.40
    assert recommend(broad, neither).confidence == 0.40
    for level in ("result_only", "explained", "scoped", "full"):
        out = recommend(broad, neither, disclosure_level=level).to_json()
        assert _assumed(out) == [STRETCH_ASSUMED, TOLERANCE_ASSUMED], level


LEFT_OUT = "does not publish a measurement for these zones"
SHIRT_KEYS = (
    "neck_circumference",
    "shoulder_width",
    "chest_width",
    "waist_width",
    "sleeve_length",
)


def _as_its_owner_measures_it(shirt, *keys, sizes=("41",), category="shirts"):
    """The example shirt as the builder writes one for its owner: no ease bands, no critical
    zones, no production tolerance, and only the measurements and the sizes named."""
    import copy

    garment = copy.deepcopy(shirt)
    del garment["intended_ease"], garment["critical_zones"], garment["production_tolerance"]
    garment["category"] = category
    garment["sizes"] = [size for size in garment["sizes"] if size["size_label"] in sizes]
    for size in garment["sizes"]:
        size["finished_measurements"] = {
            key: value for key, value in size["finished_measurements"].items() if key in keys
        }
    return garment


def test_a_garment_that_measures_less_is_not_surer_for_it(mature, shirt):
    """It used to be. A zone the garment did not publish, unless critical, left every
    denominator, and each zone compared against a category default cost 0.03: the one shirt its
    owner measured at five places came out at 0.70, at the collar, the shoulders and the chest
    at 0.77, and at the collar and the shoulders alone at 0.80. A zone a garment of its kind has
    is now a line of the explanation whether it was published or not, named at every level and
    never put down to the profile. No absolute number is asserted: the direction is the point."""
    every_size = ("39", "40", "41", "42")
    for sizes in (("41",), every_size):
        five, three, two = (
            recommend(mature, _as_its_owner_measures_it(shirt, *keys, sizes=sizes)).confidence
            for keys in (SHIRT_KEYS, SHIRT_KEYS[:3], SHIRT_KEYS[:2])
        )
        assert five > three > two, sizes

    # A sweater cut raglan leaves its shoulders and its sleeve out, as spec/02 asks: the answer
    # says nothing of either, and is less sure than one about a sweater measured at four places.
    knit = SHIRT_KEYS[1:]
    four, raglan, chest_only = (
        recommend(mature, _as_its_owner_measures_it(shirt, *keys, category="knitwear")).confidence
        for keys in (knit, ("chest_width", "waist_width"), ("chest_width",))
    )
    assert four > raglan > chest_only

    partial = _as_its_owner_measures_it(shirt, *SHIRT_KEYS[:3])
    for level in ("result_only", "explained", "scoped", "full"):
        caveats = recommend(mature, partial, disclosure_level=level).to_json()["caveats"]
        assert [c for c in caveats if LEFT_OUT in c] == [
            "The garment does not publish a measurement for these zones, so they were not "
            "evaluated: sleeve_length, waist."
        ], level
        assert not any("critical zones" in c for c in caveats), level
        assert not any("profile has no matching measurement" in c for c in caveats), level

    out = recommend(mature, partial, disclosure_level="explained").to_json()
    unknown = {
        line["zone"]: line for line in out["explanation"] if line["assessment"] == "unknown"
    }
    assert set(unknown) == {"waist", "sleeve_length"}
    assert not any(line["critical"] for line in unknown.values())

    # A critical zone left out keeps the sentence of its own, and the two are not mixed.
    no_shoulders = _as_its_owner_measures_it(shirt, "neck_circumference", "chest_width")
    caveats = recommend(mature, no_shoulders).to_json()["caveats"]
    assert any("critical zones" in c and c.endswith(": shoulders.") for c in caveats)
    assert any(LEFT_OUT in c and c.endswith(": sleeve_length, waist.") for c in caveats)


def test_an_ease_band_left_out_costs_once_whatever_the_sizes(mature, shirt):
    """Judging a zone against a category default used to cost 0.03 for every size it was judged
    on, up to 0.15: on the four sizes of the example the first band left out cost 0.12, the
    second the rest, and the other three nothing. It is a share of the zones compared, so each
    band costs what the one before did, on one size as on four. The bands declared here are the
    category defaults themselves, so that leaving one out changes no judgement, only the cost."""
    import copy

    from agiofit.mapping import DEFAULT_EASE

    declared = copy.deepcopy(shirt)
    declared["intended_ease"] = {
        zone: {"min": lo, "max": hi, "unit": "cm"}
        for (category, zone), (lo, hi) in DEFAULT_EASE.items()
        if category == "shirts"
    }
    assert set(declared["intended_ease"]) == set(shirt["intended_ease"])
    zones = sorted(declared["intended_ease"])

    for sizes in (("41",), ("39", "40", "41", "42")):
        garment = copy.deepcopy(declared)
        garment["sizes"] = [size for size in garment["sizes"] if size["size_label"] in sizes]
        base = recommend(mature, garment)
        for left_out, zone in enumerate(zones, start=1):
            del garment["intended_ease"][zone]
            report = recommend(mature, garment)
            assert report.explanation == base.explanation, "the judgement is the one of before"
            assert report.confidence == pytest.approx(base.confidence - 0.03 * left_out), (
                sizes,
                left_out,
            )

    # Nor is a band cheaper to leave out on a garment that publishes less: with no band at all,
    # the shirt measured at the collar and the shoulders alone pays what the whole shirt pays.
    for keys in (SHIRT_KEYS, SHIRT_KEYS[:2]):
        bare = _as_its_owner_measures_it(shirt, *keys)
        banded = copy.deepcopy(bare)
        banded["intended_ease"] = copy.deepcopy(declared["intended_ease"])
        cost = recommend(mature, banded).confidence - recommend(mature, bare).confidence
        assert cost == pytest.approx(0.15), keys


def test_a_zone_the_category_does_not_have_is_not_expected(mature, shirt):
    """A zone left out counts only where something named it: the category, through the zones a
    garment of its kind has, its critical zones or its default bands, or the garment itself. A
    shirt is not marked down for its inseam, a top for a sleeve that may be short, and a
    category with no list of its own for anything but what was named."""
    import copy

    from agiofit.mapping import expected_zones

    def lines(garment):
        # The report as the person has it: the example profile keeps its hips to itself, and a
        # zone judged on them does not leave, published or not.
        return {line.zone: line.assessment for line in recommend(mature, garment).explanation}

    whole = lines(_as_its_owner_measures_it(shirt, *SHIRT_KEYS))
    assert set(whole) == {"neck", "shoulders", "chest", "waist", "sleeve_length"}
    assert "unknown" not in whole.values()

    tee = lines(_as_its_owner_measures_it(shirt, "chest_width", "waist_width", category="tops"))
    assert tee["hip"] == tee["shoulders"] == "unknown"
    assert "sleeve_length" not in tee and "neck" not in tee

    for category in ("jeans", "trousers"):
        legs = lines(dict(_jeans(), category=category))
        assert legs["thigh"] == legs["inseam"] == "unknown", category
        assert not {"neck", "chest", "shoulders", "sleeve_length"} & set(legs), category

    # Outerwear has no list of its own: only its critical zones are expected, and what the
    # garment names. An ease band declared for a zone is a zone named.
    coat = _as_its_owner_measures_it(shirt, "chest_width", category="outerwear")
    assert lines(coat) == {"chest": "as_cut", "shoulders": "unknown"}
    assert expected_zones("outerwear", coat) == {"chest", "shoulders"}
    assert expected_zones("outerwear", dict(coat, critical_zones=["hip"])) == {"hip"}
    lined = copy.deepcopy(coat)
    lined["intended_ease"] = {"waist": {"min": 10, "max": 30, "unit": "cm"}}
    assert lines(lined)["waist"] == "unknown"
    caveats = recommend(mature, lined).to_json()["caveats"]
    assert any(LEFT_OUT in c and c.endswith(": waist.") for c in caveats)
    assert recommend(mature, lined).confidence < recommend(mature, coat).confidence


def test_what_a_category_is_expected_to_publish_is_what_it_can_be_judged_on():
    """The third table of category defaults, held to the other two. A zone expected of a category
    has a mapping, or leaving it out would cost a document for something nothing here reads; and
    a zone the category calls critical, or has a default band for, is one it is expected to
    have."""
    from agiofit.mapping import CRITICAL_ZONES, DEFAULT_EASE, EXPECTED_ZONES, MAPPED_ZONES

    categories = set(
        json.loads((SCHEMAS / "cut-profile.schema.json").read_text())["properties"]["category"]["enum"]
    )
    assert set(EXPECTED_ZONES) <= categories
    for category, zones in EXPECTED_ZONES.items():
        assert len(set(zones)) == len(zones), category
        assert set(zones) <= MAPPED_ZONES, category
        assert set(CRITICAL_ZONES.get(category, ())) & MAPPED_ZONES <= set(zones), category
        assert {zone for (cat, zone) in DEFAULT_EASE if cat == category} <= set(zones), category


# --------------------------------------------------------------------------- custody
# What 04-privacy.md asks of a vault, as far as an implementation that holds nothing can show
# it: the match is computed here, the profile is left alone, and one report leaves.

EVERY_LEVEL = ("result_only", "explained", "scoped", "full")


def test_matching_needs_no_network(mature, cold, shirt, monkeypatch, capsys):
    """A match is computed where the profile is. The package imports nothing that reaches a
    network or starts another program, and the whole path, the command line included, runs with
    the network taken away."""
    import ast
    import socket

    from agiofit.cli import main

    reaching_out = {
        "asyncio", "ftplib", "http", "imaplib", "multiprocessing", "poplib", "smtplib",
        "socket", "socketserver", "ssl", "subprocess", "telnetlib", "urllib", "webbrowser",
        "xmlrpc", "httpx", "requests",
    }
    package = ROOT / "reference" / "agiofit"
    sources = sorted(package.glob("*.py"))
    assert sources, "the package was not found"
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in reaching_out, (source.name, name)

    def no_network(*args, **kwargs):
        raise AssertionError("matching opened a socket")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    for profile in (mature, cold):
        for level in EVERY_LEVEL:
            assert recommend(profile, shirt, disclosure_level=level).to_json()
    assert main([str(EXAMPLES / "profile-mature.json"), str(EXAMPLES / "cut-shirt.json")]) == 0
    assert json.loads(capsys.readouterr().out)["recommended_size"] == "41"


def test_a_report_names_neither_the_profile_nor_the_person(mature, cold, shirt):
    """A report reaches a verifier, and the same identifier reaching two of them would let them
    recognise one person. Nothing that identifies the profile is in it, at any level: not its
    id, not the moment it was last written, not the name of an import."""
    for profile in (mature, cold):
        marks = {profile["profile_id"], profile["updated_at"]}
        history = profile.get("history", [])
        marks |= {entry["import_ref"] for entry in history if "import_ref" in entry}
        assert len(marks) >= 2
        for level in EVERY_LEVEL:
            sent = json.dumps(recommend(profile, shirt, disclosure_level=level).to_json())
            for mark in marks:
                assert mark not in sent, (level, mark)
    assert any("import_ref" in entry for entry in mature["history"]), "the example lost its import"


def test_what_leaves_is_one_match_report(capsys):
    """In answer to a request one document leaves, a Match Report at one level, and nothing with
    it. The command line prints exactly that: one JSON document, valid against the schema, with
    no key the schema does not name."""
    import jsonschema

    from agiofit.cli import main

    schema = json.loads((SCHEMAS / "match-report.schema.json").read_text(encoding="utf-8"))
    for example in ("profile-mature.json", "profile-cold-start.json"):
        for level in EVERY_LEVEL:
            assert main([str(EXAMPLES / example), str(EXAMPLES / "cut-shirt.json"), level]) == 0
            printed = capsys.readouterr()
            assert printed.err == ""
            report = json.loads(printed.out)
            assert isinstance(report, dict)
            jsonschema.validate(report, schema)
            assert set(report) <= set(schema["properties"]), (example, level)
            assert report["disclosure_level"] == level
            profile = json.loads((EXAMPLES / example).read_text(encoding="utf-8"))
            assert profile["profile_id"] not in printed.out, (example, level)
            assert profile["updated_at"] not in printed.out, (example, level)


def test_a_match_leaves_the_profile_as_it_was(mature, cold, shirt, tmp_path, monkeypatch):
    """The profile is the person's, and answering a request is not a reason to change it.
    Neither document is altered by a match, at any level, and nothing is written to disk."""
    import copy

    monkeypatch.chdir(tmp_path)
    for profile in (mature, cold):
        for level in EVERY_LEVEL:
            before = copy.deepcopy(profile), copy.deepcopy(shirt)
            recommend(profile, shirt, disclosure_level=level).to_json()
            assert (profile, shirt) == before, level
    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------------------------- match request
# The document a verifier sends to ask for a report, and what the reference implementation does
# with one. The authorisation these tests pass is an input, as it is to the implementation: they
# show what is done with an authorisation, not that a person gave it.

MARK = "zq7-told-apart"


@pytest.fixture
def request_for_shirt():
    return json.loads((EXAMPLES / "match-request.json").read_text(encoding="utf-8"))


def _request_schema():
    return json.loads((SCHEMAS / "match-request.schema.json").read_text(encoding="utf-8"))


def _asking(request, level, justification="A tailor is altering this shirt."):
    """The example request asking for a level, or for none; with its justification at full."""
    import copy

    asked = copy.deepcopy(request)
    asked.pop("disclosure_level", None)
    asked.pop("justification", None)
    if level is not None:
        asked["disclosure_level"] = level
    if level == "full":
        asked["justification"] = justification
    return asked


def _level_shown(sent):
    """The highest level a serialised report gives away, from what it carries (spec/04)."""
    lines = sent.get("explanation", [])
    if any("intended_ease_cm" in line for line in lines):
        return "full"
    if any("ease_cm" in line for line in lines):
        return "scoped"
    if {"explanation", "alternatives", "based_on", "improve_by"} & set(sent):
        return "explained"
    return "result_only"


def test_the_example_request_is_a_match_request(request_for_shirt, shirt):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(request_for_shirt, _request_schema(), format_checker=_formats(jsonschema))
    assert request_problems(request_for_shirt, shirt) == []
    assert request_for_shirt["cut_profile_id"] == shirt["cut_profile_id"]


def test_the_schema_and_the_reference_agree_on_what_a_request_is(request_for_shirt):
    """The shape of a request is checked twice: by the schema, for anyone, and by hand in the
    reference implementation, which keeps no dependency. Each request here gets the same verdict
    from both. This is the structural check, and all of it: that a verifier sends the same
    request to everyone is a fact about the verifier, and no schema shows it."""
    import copy

    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(
        _request_schema(), format_checker=_formats(jsonschema)
    )

    def changed(**fields):
        request = copy.deepcopy(request_for_shirt)
        for key, value in fields.items():
            if value is None:
                request.pop(key, None)
            else:
                request[key] = value
        return request

    good = [
        request_for_shirt,
        changed(disclosure_level=None),
        changed(cut_profile_uri=None),
        changed(verifier={"name": "Sartoria Esempio"}),
        changed(disclosure_level="full", justification="A tailor is altering this shirt."),
        changed(justification="Shown with the fit notes on the product page."),
        changed(cut_profile_uri="https://shop.example"),
        changed(cut_profile_uri="https://shop.example/a/b@c.json"),
        changed(verifier={"name": "x" * 120}),
        changed(disclosure_level="scoped", justification="j" * 500),
    ]
    bad = [
        changed(customer_id="C-10442"),
        changed(request_id="r-1"),
        changed(schema_version="0.1.0"),
        changed(schema_version="0.2.1"),
        changed(schema_version=2),
        changed(schema_version=None),
        changed(cut_profile_id=None),
        changed(cut_profile_id="short"),
        changed(cut_profile_id="has a space in it"),
        changed(cut_profile_uri="http://shop.example/cut.json"),
        changed(cut_profile_uri="https://shop.example/cut.json?customer=10442"),
        changed(cut_profile_uri="https://shop.example/cut.json#10442"),
        changed(cut_profile_uri="https://user:secret@shop.example/cut.json"),
        changed(cut_profile_uri="https://shop.example/cut .json"),
        changed(cut_profile_uri="shop.example/cut.json"),
        changed(cut_profile_uri=12),
        changed(verifier=None),
        changed(verifier="Sartoria Esempio"),
        changed(verifier={}),
        changed(verifier={"name": ""}),
        changed(verifier={"name": "   "}),
        changed(verifier={"name": "x" * 121}),
        changed(verifier={"name": "Sartoria Esempio", "account": "10442"}),
        changed(verifier={"name": "Sartoria Esempio", "uri": "https://shop.example/?u=10442"}),
        changed(disclosure_level="everything"),
        changed(disclosure_level="full"),
        changed(justification=""),
        changed(justification="j" * 501),
        changed(justification=7),
    ]
    for request in good:
        assert validator.is_valid(request), request
        assert request_problems(request) == [], request
    for request in bad:
        assert not validator.is_valid(request), request
        assert request_problems(request), request
    assert request_problems(["not", "an", "object"]) and not validator.is_valid([])


def test_the_request_schema_stands_alone_and_is_closed():
    """Validating a request takes one file, as for the other three schemas: nothing in it points
    to another. And it is closed at both levels, so a field about the person has nowhere to go."""
    schema = _request_schema()

    def refs(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref":
                    yield value
                else:
                    yield from refs(value)
        elif isinstance(node, list):
            for item in node:
                yield from refs(item)

    found = list(refs(schema))
    assert found and all(ref.startswith("#/") for ref in found)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["verifier"]["additionalProperties"] is False


def test_the_levels_are_the_same_in_every_schema():
    """Three schemas and the reference implementation name the disclosure levels, by copy rather
    than by reference. The lists are the same, in the same order, least to most."""
    from agiofit.match import DISCLOSURE_LEVELS

    fit = json.loads((SCHEMAS / "fit-profile.schema.json").read_text(encoding="utf-8"))
    report = json.loads((SCHEMAS / "match-report.schema.json").read_text(encoding="utf-8"))
    lists = (
        fit["$defs"]["disclosure_level"]["enum"],
        report["properties"]["disclosure_level"]["enum"],
        _request_schema()["properties"]["disclosure_level"]["enum"],
    )
    for levels in lists:
        assert tuple(levels) == DISCLOSURE_LEVELS == EVERY_LEVEL


def test_a_report_is_at_the_lower_of_the_level_asked_and_the_level_authorised(
    mature, shirt, request_for_shirt
):
    """spec/04, AC3, in every combination: the level asked (none, or each of the four), the level
    authorised (none in particular, or each of the four), and the person's default (none, or each
    of the four). 125 cases. Where the request names no level the level asked is the default;
    where the person authorised without naming one, the level authorised is the default; the
    report is at the lower of the two, says so, and carries nothing a higher level would."""
    import copy

    order = EVERY_LEVEL.index
    cases = 0
    for default in (None,) + EVERY_LEVEL:
        profile = copy.deepcopy(mature)
        if default is None:
            profile.pop("disclosure_defaults", None)
        else:
            profile["disclosure_defaults"] = {"default_level": default}
        fallback = default or "result_only"
        for asked in (None,) + EVERY_LEVEL:
            request = _asking(request_for_shirt, asked)
            for authorised in (True,) + EVERY_LEVEL:
                granted = fallback if authorised is True else authorised
                expected = min(asked or fallback, granted, key=order)
                case = (default, asked, authorised)

                assert effective_level(profile, asked, authorised) == expected, case
                report = answer(profile, shirt, request, authorised=authorised)
                assert report is not None, case
                sent = report.to_json()
                assert sent["disclosure_level"] == expected, case
                assert order(_level_shown(sent)) <= order(expected), case
                assert order(expected) <= order(asked or fallback), case
                assert order(expected) <= order(granted), case
                cases += 1
    assert cases == 125

    with pytest.raises(UnknownDisclosureLevel):
        answer(mature, shirt, request_for_shirt, authorised="everything")
    with pytest.raises(UnknownDisclosureLevel):
        effective_level(mature, "everything", True)


def test_without_an_authorisation_there_is_no_report(
    mature, cold, shirt, request_for_shirt, capsys
):
    """Declining is sending no report: not an empty one, not one with a reason in it. A request
    that was not authorised gets nothing, whatever it asks, and the command line prints nothing
    where a report would go."""
    from agiofit.cli import main

    for profile in (mature, cold):
        for asked in (None,) + EVERY_LEVEL:
            request = _asking(request_for_shirt, asked)
            assert answer(profile, shirt, request) is None
            assert answer(profile, shirt, request, authorised=None) is None
            assert answer(profile, shirt, request, authorised=False) is None

    files = [str(EXAMPLES / "profile-mature.json"), str(EXAMPLES / "cut-shirt.json")]
    assert main(files + ["--request", str(EXAMPLES / "match-request.json")]) != 0
    printed = capsys.readouterr()
    assert printed.out == ""
    assert "No report" in printed.err

    # An authorisation with no request to authorise, or a level beside a request, is a misuse.
    assert main(files + ["--authorise"]) == 2
    assert main(files + ["explained", "--request", str(EXAMPLES / "match-request.json")]) == 2
    assert capsys.readouterr().out == ""


def test_a_request_for_full_says_why_or_gets_nothing(mature, shirt, request_for_shirt):
    """full is for a tailor and for exceptional cases, and the person is shown the reason before
    they authorise it. A request for full with no justification is declined, even with full
    authorised; with one, it is answered at full; and a request that asked for less is never
    answered at full, whatever was authorised."""
    silent = _asking(request_for_shirt, "full")
    del silent["justification"]
    assert answer(mature, shirt, silent, authorised="full") is None
    assert answer(mature, shirt, silent, authorised=True) is None

    said = _asking(request_for_shirt, "full")
    assert answer(mature, shirt, said, authorised="full").to_json()["disclosure_level"] == "full"

    for asked in (None, "result_only", "explained", "scoped"):
        report = answer(mature, shirt, _asking(request_for_shirt, asked), authorised="full")
        assert report.to_json()["disclosure_level"] != "full", asked


def test_a_request_is_answered_about_the_cut_profile_it_names(mature, shirt, request_for_shirt):
    """A request names one Cut Profile. Handed another, the reference implementation declines
    rather than answer about a garment nobody asked about."""
    import copy

    other = copy.deepcopy(shirt)
    other["cut_profile_id"] = "sartoria-esempio:OXF-SLIM:2026"
    assert answer(mature, other, request_for_shirt, authorised=True) is None
    assert request_problems(request_for_shirt, other)
    assert answer(mature, shirt, request_for_shirt, authorised=True) is not None

    elsewhere = copy.deepcopy(request_for_shirt)
    elsewhere["cut_profile_id"] = other["cut_profile_id"]
    assert answer(mature, shirt, elsewhere, authorised=True) is None
    assert answer(mature, other, elsewhere, authorised=True) is not None


def test_a_request_that_is_not_one_gets_nothing(mature, shirt, request_for_shirt):
    """A request with a field it should not have, an address that could carry something about
    the person, or no word on who is asking, is declined whatever was authorised."""
    import copy

    for change in (
        {"customer_id": "C-10442"},
        {"cut_profile_uri": "https://shop.example/cut.json?customer=10442"},
        {"verifier": {"name": "Sartoria Esempio", "account": "10442"}},
        {"verifier": {"name": ""}},
        {"schema_version": "0.1.0"},
        {"disclosure_level": "everything"},
    ):
        request = copy.deepcopy(request_for_shirt)
        request.update(change)
        assert answer(mature, shirt, request, authorised="full") is None, change
    assert answer(mature, shirt, "not a request", authorised=True) is None


def test_nothing_a_request_says_ends_up_in_the_report(mature, cold, shirt, request_for_shirt):
    """A vault treats what a request says as something to show the person and nothing more. A
    mark written into every text and address of a request is in no report, at any level: what a
    report repeats is the identifier of the Cut Profile, which is the garment's and not the
    request's."""
    request = _asking(request_for_shirt, "full", justification=f"For the tailor, {MARK}.")
    request["verifier"] = {"name": f"Atelier {MARK}", "uri": f"https://{MARK}.example"}
    request["cut_profile_uri"] = f"https://shop.example/{MARK}/cut.json"
    assert request_problems(request, shirt) == []

    for profile in (mature, cold):
        for authorised in (True,) + EVERY_LEVEL:
            sent = json.dumps(answer(profile, shirt, request, authorised=authorised).to_json())
            assert MARK not in sent, authorised
            for said in ("Atelier", "tailor", "shop.example"):
                assert said not in sent, (authorised, said)


def test_the_whole_path_runs_on_one_machine_with_no_network(tmp_path, monkeypatch, capsys):
    """What ROADMAP.md asks of this version: a profile in a file the person keeps, a request, an
    authorisation given as input, and a report at the lower of the level asked and the level
    authorised, with the network taken away and nothing else written or changed."""
    import shutil
    import socket

    from agiofit.cli import main

    def no_network(*args, **kwargs):
        raise AssertionError("answering a request opened a socket")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)

    kept = tmp_path / "kept"
    kept.mkdir()
    names = ("profile-mature.json", "cut-shirt.json", "match-request.json")
    for name in names:
        shutil.copy(EXAMPLES / name, kept / name)
    before = {name: (kept / name).read_bytes() for name in names}
    files = [str(kept / "profile-mature.json"), str(kept / "cut-shirt.json")]
    asking = ["--request", str(kept / "match-request.json")]
    monkeypatch.chdir(tmp_path)

    # The example asks for explained; the person's default is result_only.
    for flag, expected in (
        ("--authorise", "result_only"),
        ("--authorise=result_only", "result_only"),
        ("--authorise=explained", "explained"),
        ("--authorise=full", "explained"),
    ):
        assert main(files + asking + [flag]) == 0
        printed = capsys.readouterr()
        assert printed.err == ""
        report = json.loads(printed.out)
        assert report["disclosure_level"] == expected, flag
        assert report["recommended_size"] == "41"
        assert "verifier" not in printed.out and "sartoria-esempio.example" not in printed.out

    assert {name: (kept / name).read_bytes() for name in names} == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["kept"]
    assert sorted(path.name for path in kept.iterdir()) == sorted(names)


def test_the_cli_writes_its_report_in_utf8_whatever_the_console(tmp_path, monkeypatch):
    """On Windows, a report sent to a file with > was written in the console's code page,
    cp1252, so an id or a size label with an accent made a JSON file that whoever opens it as
    UTF-8 cannot read. The report is UTF-8 whatever the console."""
    import io
    import sys

    from agiofit.cli import main

    garment = json.loads((EXAMPLES / "cut-shirt.json").read_text(encoding="utf-8"))
    garment["cut_profile_id"] = "maglificio-città:camicia:2026"
    accented = tmp_path / "cut-shirt.json"
    accented.write_text(json.dumps(garment, ensure_ascii=False), encoding="utf-8")
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)

    assert main([str(EXAMPLES / "profile-cold-start.json"), str(accented), "explained"]) == 0
    console.flush()
    report = json.loads(console.buffer.getvalue().decode("utf-8"))
    assert report["cut_profile_id"] == "maglificio-città:camicia:2026"
