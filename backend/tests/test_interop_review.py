"""Independent export-contract checks; not an official HL7 profile validator."""
import base64
import copy
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace
from urllib.parse import urljoin

import pytest

from app.interop import encounter_bundle


def records(data=None):
    patient = SimpleNamespace(id="2d0a6c86-22be-40e5-9dc0-78da071152f0", facility_id="facility-a", external_id="SYN-001",
                              given_name="Synthetic", family_name="Patient", sex="female", date_of_birth=date(1970, 1, 1), phone=None)
    encounter = SimpleNamespace(id="7e0d0f85-c0cc-40b0-ab9f-186463f99305", status="draft", review=None,
                                created_at=datetime(2026, 8, 1, tzinfo=timezone.utc), updated_at=datetime.now(timezone.utc),
                                data=data or {}, assessment=None)
    return patient, encounter


def resources(bundle, resource_type):
    return [entry["resource"] for entry in bundle["entry"] if entry["resource"]["resourceType"] == resource_type]


def references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "reference":
                yield child
            else:
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def test_bundle_resource_identity_reference_closure_and_required_fields():
    bundle = encounter_bundle(*records({"systolic_bp": 140, "diastolic_bp": 90, "repeat_systolic_bp": 130,
                                       "repeat_diastolic_bp": 80, "glucose": 5.5, "glucose_unit": "mmol/L", "egfr": 0}))
    assert bundle["resourceType"] == "Bundle" and bundle["type"] == "collection"
    full_urls = [entry["fullUrl"] for entry in bundle["entry"]]
    assert len(full_urls) == len(set(full_urls))
    for entry in bundle["entry"]:
        resource = entry["resource"]
        assert re.fullmatch(r"[A-Za-z0-9\-.]{1,64}", resource["id"])
        assert entry["fullUrl"].endswith(f"/{resource['resourceType']}/{resource['id']}")
        base = entry["fullUrl"].rsplit("/", 2)[0] + "/"
        assert all(urljoin(base, reference) in full_urls for reference in references(resource))
        assert "request" not in entry and "response" not in entry
        if resource["resourceType"] == "Observation":
            assert resource["status"] == "preliminary" and resource["code"]
            assert "valueQuantity" in resource or "component" in resource
            assert "dataAbsentReason" not in resource


@pytest.mark.parametrize("unit,value,code", [("mg/dL", 180, "2339-0"), ("mmol/L", 10, "15074-8")])
def test_glucose_property_code_and_unit_preserved(unit, value, code):
    observation = resources(encounter_bundle(*records({"glucose": value, "glucose_unit": unit})), "Observation")[0]
    assert observation["code"]["coding"][0]["code"] == code
    assert observation["valueQuantity"] == {"value": value, "unit": unit, "code": unit, "system": "http://unitsofmeasure.org"}


@pytest.mark.parametrize("unit", [None, "g/L", ""])
def test_unknown_glucose_unit_is_not_silently_relabelled(unit):
    with pytest.raises(ValueError, match="supported recorded unit"):
        encounter_bundle(*records({"glucose": 6, "glucose_unit": unit}))


def test_unknown_measurement_time_not_invented_and_egfr_not_assumed_method():
    observation = resources(encounter_bundle(*records({"egfr": 0})), "Observation")[0]
    assert "effectiveDateTime" not in observation
    assert "Measurement time was not recorded" in observation["note"][0]["text"]
    assert observation["valueQuantity"]["value"] == 0
    assert observation["valueQuantity"]["code"] == "mL/min/{1.73_m2}"
    assert observation["code"]["coding"][0]["system"] != "http://loinc.org"
    assert "method" not in observation


def test_recorded_time_and_bp_components_preserved():
    when = "2026-08-01T10:15:00+03:00"
    observations = resources(encounter_bundle(*records({"systolic_bp": 144, "diastolic_bp": 88,
                             "repeat_systolic_bp": 134, "repeat_diastolic_bp": 82, "observed_at": when})), "Observation")
    assert len(observations) == 2
    assert all(item["effectiveDateTime"] == when for item in observations)
    assert [item["component"][0]["valueQuantity"]["value"] for item in observations] == [144, 134]
    for item in observations:
        assert [component["code"]["coding"][0]["code"] for component in item["component"]] == ["8480-6", "8462-4"]
        assert all(component["valueQuantity"]["code"] == "mm[Hg]" for component in item["component"])
    assert "distinct repeat measurement time" in observations[1]["note"][-1]["text"]


def reviewed_records():
    patient, encounter = records({"glucose": 900, "glucose_unit": "mg/dL"})
    encounter.status = "reviewed"
    encounter.assessment = {"recommendations": []}
    encounter.review = {"reviewed_at": "2026-08-01T11:00:00+03:00", "reviewer_name": "Test Clinician", "reviewer_id": "clinician-1",
                        "assessment_id": "assessment-1", "input_version": 2, "note": "Documented shared decision.",
                        "input_snapshot": {"glucose": 8, "glucose_unit": "mmol/L"},
                        "assessment_snapshot": {"evidence_version": "test-evidence-v1", "recommendations": [
                            {"id": "rec-1", "rule_id": "TEST_RULE", "title": "Original recommendation", "detail": "Original detail",
                             "evidence": [{"title": "Source title", "url": "https://example.org/source", "section": "2", "version": "2026"}]}]},
                        "decisions": [{"recommendation_id": "rec-1", "action": "modify", "reason": "Patient preference", "modified_text": "Modified plan"}]}
    return patient, encounter


def test_final_export_uses_review_snapshots_and_preserves_accountability():
    patient, encounter = reviewed_records()
    original = copy.deepcopy(encounter.review)
    bundle = encounter_bundle(patient, encounter)
    observation = resources(bundle, "Observation")[0]
    assert observation["valueQuantity"]["value"] == 8 and observation["valueQuantity"]["code"] == "mmol/L"
    document = resources(bundle, "DocumentReference")[0]
    assert document["status"] == "current" and document["docStatus"] == "final"
    assert document["author"][0]["identifier"]["value"] == "clinician-1"
    assert document["date"] == original["reviewed_at"]
    text = base64.b64decode(document["content"][0]["attachment"]["data"]).decode("utf-8")
    for expected in ["MODIFY", "Modified plan", "Clinician rationale: Patient preference", "Documented shared decision.",
                     "TEST_RULE", "https://example.org/source", "test-evidence-v1", "assessment-1"]:
        assert expected in text
    assert encounter.review == original


def test_corrupt_final_record_never_falls_back_to_current_data():
    patient, encounter = reviewed_records()
    del encounter.review["input_snapshot"]
    with pytest.raises(KeyError):
        encounter_bundle(patient, encounter)


def test_reviewed_status_without_a_review_is_not_exported_as_final():
    patient, encounter = records({"glucose": 6, "glucose_unit": "mmol/L"})
    encounter.status = "reviewed"
    with pytest.raises(ValueError, match="without its clinician review"):
        encounter_bundle(patient, encounter)


def test_bundle_timestamp_is_assembly_time_not_visit_creation():
    start = datetime.now(timezone.utc)
    bundle = encounter_bundle(*records())
    assert start <= datetime.fromisoformat(bundle["timestamp"]) <= datetime.now(timezone.utc)
