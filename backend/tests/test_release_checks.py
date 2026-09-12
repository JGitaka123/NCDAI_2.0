"""Deployment readiness and clinician-identifiable referral regression checks."""
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import create_app
from app.config import Settings
from app.db import Base, SCHEMA_REVISION
from conftest import encounter


def test_readiness_requires_deployed_migration_version(tmp_path):
    app = create_app(Settings(environment="test", database_url=f"sqlite:///{tmp_path / 'readiness.db'}"))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert client.get("/api/health/ready").status_code == 503
        with app.state.engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": SCHEMA_REVISION})
        assert client.get("/api/health/ready").status_code == 200
        with app.state.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'unexpected_old_revision'"))
        assert client.get("/api/health/ready").status_code == 503
        assert client.get("/api/health/live").status_code == 200


def test_referral_responses_include_confirmable_patient_identity(client):
    record = encounter(client)
    response = client.post(f"/api/encounters/{record['id']}/referrals", json={
        "reason": "Synthetic referral identity check", "destination": "Synthetic clinic", "urgency": "soon"})
    assert response.status_code == 201
    referral = response.json()
    assert referral["patient_name"] == "Synthetic Patient"
    assert referral["patient_external_id"] == "SYN-001"
    listed = client.get("/api/referrals").json()
    assert listed[0]["patient_external_id"] == referral["patient_external_id"]
    updated = client.patch(f"/api/referrals/{referral['id']}", json={"status": "accepted"})
    assert updated.status_code == 200
    assert updated.json()["patient_name"] == referral["patient_name"]
