"""FHIR R4 export contract; not national-profile conformance certification."""
import base64
from datetime import datetime, timezone


def iso(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def patient_resource(patient):
    resource = {"resourceType": "Patient", "id": patient.id, "active": True,
        "meta": {"tag": [{"system": "https://ncdai.example/fhir/CodeSystem/data-classification", "code": "synthetic", "display": "Synthetic test record"}]},
        "identifier": [{"system": f"urn:ncdai:facility:{patient.facility_id}:patient", "value": patient.external_id}],
        "name": [{"use": "official", "family": patient.family_name, "given": [patient.given_name]}],
        "gender": patient.sex, "birthDate": patient.date_of_birth.isoformat()}
    if patient.phone:
        resource["telecom"] = [{"system": "phone", "value": patient.phone}]
    return resource


def encounter_bundle(patient, encounter):
    if encounter.status == "reviewed" and not encounter.review:
        raise ValueError("Cannot export a final record without its clinician review")
    reviewed = encounter.status == "reviewed" and bool(encounter.review)
    # A final export must reflect exactly the data on which the clinician acted.
    # Missing snapshots indicate a corrupt record; never substitute current data.
    data = encounter.review["input_snapshot"] if reviewed else encounter.data
    assessment = encounter.review["assessment_snapshot"] if reviewed else encounter.assessment
    patient_ref = f"Patient/{patient.id}"
    encounter_ref = f"Encounter/{encounter.id}"
    resources = [patient_resource(patient), {
        "resourceType": "Encounter", "id": encounter.id,
        "status": "finished" if encounter.status == "reviewed" else "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"},
        "subject": {"reference": patient_ref}, "period": {"start": iso(encounter.created_at)},
    }]
    observed = data.get("observed_at")
    def observation(suffix, code, display):
        item = {"resourceType": "Observation", "id": f"{encounter.id}-{suffix}",
                "status": "final" if encounter.status == "reviewed" else "preliminary",
                "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
                "subject": {"reference": patient_ref}, "encounter": {"reference": encounter_ref}}
        if observed:
            item["effectiveDateTime"] = observed
        else:
            # FHIR effective[x] is optional. Record entry time is not collection time.
            item["note"] = [{"text": "Measurement time was not recorded; record creation time must not be interpreted as measurement time."}]
        dated_lab = data.get("dosing_context", {}).get({"egfr": "renal_observed_at", "potassium": "potassium_observed_at"}.get(suffix, ""))
        if dated_lab:
            item["effectiveDateTime"] = dated_lab
            item.pop("note", None)
        if suffix == "bp-repeat":
            item.setdefault("note", []).append({"text": "Repeat blood pressure; a distinct repeat measurement time was not captured."})
        return item
    def quantity(value, unit, code):
        return {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": code}
    for prefix, suffix in [("", "bp"), ("repeat_", "bp-repeat")]:
        components = []
        for key, code, display in [("systolic_bp", "8480-6", "Systolic blood pressure"), ("diastolic_bp", "8462-4", "Diastolic blood pressure")]:
            if data.get(prefix + key) is not None:
                components.append({"code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]}, "valueQuantity": quantity(data[prefix + key], "mmHg", "mm[Hg]")})
        if components:
            item = observation(suffix, "85354-9", "Blood pressure panel with all children optional")
            item["component"] = components
            resources.append(item)
    fields = [("pulse", "8867-4", "Heart rate", "/min", "/min"),
              ("respiratory_rate", "9279-1", "Respiratory rate", "/min", "/min"),
              ("oxygen_saturation", "59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry", "%", "%"),
              ("hba1c", "4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%", "%"),
              ("potassium", "2823-3", "Potassium [Moles/volume] in Serum or Plasma", "mmol/L", "mmol/L")]
    for key, code, display, unit, ucum in fields:
        if data.get(key) is not None:
            item = observation(key.replace("_", "-"), code, display)
            item["valueQuantity"] = quantity(data[key], unit, ucum)
            resources.append(item)
    if data.get("glucose") is not None:
        unit = data.get("glucose_unit")
        if unit not in {"mg/dL", "mmol/L"}:
            raise ValueError("Cannot export glucose without a supported recorded unit")
        # Generic blood glucose, without asserting a capillary device or serum assay.
        # LOINC 2339-0 (mass/volume) and 15074-8 (moles/volume) were checked against loinc.org.
        item = observation("glucose", "2339-0" if unit == "mg/dL" else "15074-8",
                           "Glucose [Mass/volume] in Blood" if unit == "mg/dL" else "Glucose [Moles/volume] in Blood")
        item["valueQuantity"] = quantity(data["glucose"], unit, unit)
        resources.append(item)
    if data.get("egfr") is not None:
        # The calculation method is not captured: use a generic local code, never assert CKD-EPI/MDRD.
        item = observation("egfr", "", "Estimated glomerular filtration rate; method unspecified")
        item["code"] = {"coding": [{"system": "urn:ncdai:observation", "code": "egfr-unspecified-method"}], "text": "Estimated glomerular filtration rate; method unspecified"}
        item["valueQuantity"] = quantity(data["egfr"], "mL/min/1.73m2", "mL/min/{1.73_m2}")
        resources.append(item)
    if reviewed:
        lines = ["NCDAI clinician-reviewed decision record. Acceptance is not a safety determination.",
                 f"Reviewed by: {encounter.review['reviewer_name']}",
                 f"Reviewed at: {encounter.review['reviewed_at']}",
                 f"Assessment: {encounter.review['assessment_id']}; input version: {encounter.review['input_version']}",
                 f"Evidence version: {assessment.get('evidence_version', 'not recorded')}"]
        decisions = {d["recommendation_id"]: d for d in encounter.review["decisions"]}
        if assessment.get("dosing", {}).get("results"):
            lines.append(f"Dose engine: {assessment['dosing']['version']}; manifest: {assessment['dosing']['manifest_sha256']}")
        for recommendation in assessment["recommendations"]:
            decision = decisions[recommendation["id"]]
            lines.append(f"{decision['action'].upper()}: {recommendation['title']} — {decision.get('modified_text') or recommendation['detail']}")
            if decision.get("reason"):
                lines.append("Clinician rationale: " + decision["reason"])
            lines.append("Rule: " + recommendation["rule_id"])
            for source in recommendation.get("evidence", []):
                lines.append(f"Source: {source['title']} | {source.get('section', '')} | {source.get('version', '')} | {source['url']}")
        if encounter.review.get("note"):
            lines.append("Clinician review note: " + encounter.review["note"])
        resources.append({"resourceType": "DocumentReference", "id": f"{encounter.id}-review", "status": "current", "docStatus": "final",
                          "subject": {"reference": patient_ref}, "date": encounter.review["reviewed_at"],
                          "author": [{"identifier": {"system": f"urn:ncdai:facility:{patient.facility_id}:user", "value": encounter.review["reviewer_id"]}, "display": encounter.review["reviewer_name"]}],
                          "description": "Clinician-reviewed NCDAI decision record",
                          "context": {"encounter": [{"reference": encounter_ref}]},
                          "content": [{"attachment": {"contentType": "text/plain", "data": base64.b64encode("\n".join(lines).encode()).decode(), "title": "NCDAI reviewed decisions"}}]})
    return {"resourceType": "Bundle", "id": encounter.id, "type": "collection", "timestamp": iso(datetime.now(timezone.utc)),
            "entry": [{"fullUrl": f"https://ncdai.example/fhir/{r['resourceType']}/{r['id']}", "resource": r} for r in resources]}
