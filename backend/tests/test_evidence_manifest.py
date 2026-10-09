from app import evidence_manifest


def test_manifest_is_reproducible_and_never_enables_unapproved_retrieval():
    first = evidence_manifest.manifest()
    assert first == evidence_manifest.manifest()
    assert len(first["manifest_sha256"]) == 64
    assert all(not item["retrieval_enabled"] for item in first["sources"])
    assert any(item["document_sha256"] is None for item in first["sources"])
    kenya = next(item for item in first["sources"] if item["source_id"] == "KENYA_NCD_PROTOCOLS")
    assert kenya["document_sha256"] == "e836eef61b8739db399e5af9ce75754b7836bf84693130f41bfa3107c27f78e8"


def test_source_change_changes_manifest_hash(monkeypatch):
    before = evidence_manifest.manifest()
    package = evidence_manifest.registry()
    package["sources"][0]["section"] += "; proposed revision"
    monkeypatch.setattr(evidence_manifest, "registry", lambda: package)
    assert evidence_manifest.manifest()["manifest_sha256"] != before["manifest_sha256"]


def test_ordering_is_invariant(monkeypatch):
    before = evidence_manifest.manifest()
    package = evidence_manifest.registry()
    package["sources"].reverse()
    monkeypatch.setattr(evidence_manifest, "registry", lambda: package)
    assert evidence_manifest.manifest() == before


def test_malformed_document_hash_is_missing(monkeypatch):
    package = evidence_manifest.registry()
    for source in package["sources"]:
        source["version"] = "SHA256 " + "a" * 65
    monkeypatch.setattr(evidence_manifest, "registry", lambda: package)
    assert all(source["document_sha256"] is None for source in evidence_manifest.manifest()["sources"])
