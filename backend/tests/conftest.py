import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.models import Facility, User, uid
from app.security import hash_password

PASSWORD = "synthetic-tests-only-58!"


@pytest.fixture(scope="session")
def test_password_hash():
    return hash_password(PASSWORD)


@pytest.fixture
def app(test_password_hash, tmp_path):
    application = create_app(Settings(environment="test", database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", secret_key="test-only-not-a-production-secret", auto_create_schema=True))
    with application.state.session_factory() as db:
        a = Facility(id=uid(), name="Synthetic A")
        b = Facility(id=uid(), name="Synthetic B")
        db.add_all([a, b])
        db.flush()
        for email, role, facility in [("clinician@example.test", "clinician", a), ("supervisor@example.test", "supervisor", a), ("admin@example.test", "admin", a), ("other@example.test", "clinician", b)]:
            db.add(User(id=uid(), email=email, password_hash=test_password_hash, role=role, display_name=role.title(), facility_id=facility.id))
        db.commit()
    yield application
    application.state.engine.dispose()


def login(client, email="clinician@example.test"):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        login(client)
        yield client


def patient(client, external_id="SYN-001"):
    response = client.post("/api/patients", json={"external_id": external_id, "given_name": "Synthetic", "family_name": "Patient", "date_of_birth": "1975-01-02", "sex": "female", "synthetic": True})
    assert response.status_code == 201, response.text
    return response.json()


def encounter(client, data=None):
    record = patient(client)
    response = client.post("/api/encounters", json={"patient_id": record["id"], "data": data or {"systolic_bp": 150, "diastolic_bp": 95}})
    assert response.status_code == 201, response.text
    return response.json()


def assess(client, record):
    response = client.post(f"/api/encounters/{record['id']}/assess")
    assert response.status_code == 200, response.text
    return response.json()


def review_payload(record):
    return {"assessment_id": record["assessment"]["id"], "expected_version": record["version"],
            "decisions": [{"recommendation_id": r["id"], "action": "accept"} for r in record["assessment"]["recommendations"]]}
