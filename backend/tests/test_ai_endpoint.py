"""Provider boundary integration: immutable safety output and stale-request checks."""
from copy import deepcopy
from sqlalchemy import update
from app.models import Encounter
from conftest import encounter, assess, review_payload


def prepared(client):
    e = encounter(client)
    return assess(client, e)


def test_ai_briefing_preserves_rules_and_persists_version(client, monkeypatch):
    current = prepared(client)
    snapshot = deepcopy(current["assessment"])

    async def briefing(assessment, *, synthetic):
        assert synthetic is True
        assert assessment == snapshot
        return {"status": "ready", "provider": "test-double", "focus": [assessment["recommendations"][0]], "urgency": assessment["urgency"]}

    monkeypatch.setattr("app.ai.build_briefing", briefing)
    response = client.post(f"/api/encounters/{current['id']}/ai-briefing", json={"expected_version": current["version"], "assessment_id": snapshot["id"]})
    assert response.status_code == 200, response.text
    output = response.json()
    assert output["version"] == current["version"] + 1
    assert output["assessment"]["ai_briefing"]["status"] == "ready"
    assert {k: v for k, v in output["assessment"].items() if k != "ai_briefing"} == snapshot
    saved = client.get(f"/api/encounters/{current['id']}").json()
    assert saved == output
    # A clinician must review the version that includes this stored briefing.
    stale = client.post(f"/api/encounters/{current['id']}/review", json=review_payload(current))
    assert stale.status_code == 409


def test_provider_failure_is_visible_without_losing_assessment(client, monkeypatch):
    current = prepared(client)

    async def unavailable(assessment, *, synthetic):
        return {"status": "unavailable", "reason_code": "provider_timeout", "focus": []}

    monkeypatch.setattr("app.ai.build_briefing", unavailable)
    output = client.post(f"/api/encounters/{current['id']}/ai-briefing", json={"expected_version": current["version"], "assessment_id": current["assessment"]["id"]}).json()
    assert output["assessment"]["recommendations"] == current["assessment"]["recommendations"]
    assert output["assessment"]["ai_briefing"]["status"] == "unavailable"


def test_change_during_provider_latency_cannot_overwrite_newer_record(client, app, monkeypatch):
    current = prepared(client)

    async def raced(assessment, *, synthetic):
        with app.state.session_factory() as db:
            db.execute(update(Encounter).where(Encounter.id == current["id"]).values(version=current["version"] + 1, assessment=None))
            db.commit()
        return {"status": "ready", "focus": []}

    monkeypatch.setattr("app.ai.build_briefing", raced)
    response = client.post(f"/api/encounters/{current['id']}/ai-briefing", json={"expected_version": current["version"], "assessment_id": current["assessment"]["id"]})
    assert response.status_code == 409
    output = client.get(f"/api/encounters/{current['id']}").json()
    assert output["assessment"] is None and output["version"] == current["version"] + 1


def test_reviewed_record_blocks_ai_before_external_call(client, monkeypatch):
    current = prepared(client)
    response = client.post(f"/api/encounters/{current['id']}/review", json=review_payload(current))
    assert response.status_code == 200
    reviewed = response.json()

    async def forbidden(*args, **kwargs):
        raise AssertionError("External provider should not be called")

    monkeypatch.setattr("app.ai.build_briefing", forbidden)
    response = client.post(f"/api/encounters/{current['id']}/ai-briefing", json={"expected_version": reviewed["version"], "assessment_id": reviewed["assessment"]["id"]})
    assert response.status_code == 409
