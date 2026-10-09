"""Reproducible provenance for a proposed evidence package; no network or approval."""
from hashlib import sha256
import json
import re
from .evidence import registry

SCHEMA_VERSION = "ncdai-evidence-manifest-1"
CANONICALIZATION = "json-sort-keys-ascii-compact-utf8-1"


def manifest() -> dict:
    package = registry()
    records = []
    for source in sorted(package["sources"], key=lambda item: item["source_id"]):
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        document_hash = re.search(r"\bSHA256 ([a-f0-9]{64})(?![a-f0-9])", source["version"])
        records.append({
            **source,
            "metadata_sha256": sha256(canonical.encode()).hexdigest(),
            "document_sha256": document_hash.group(1) if document_hash else None,
            "retrieval_enabled": False,
        })
    payload = {"schema_version": SCHEMA_VERSION, "canonicalization": CANONICALIZATION,
               "evidence_version": package["version"], "review_status": package["review_status"],
               "reviewed_on": package["reviewed_on"], "sources": records}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {**payload, "manifest_sha256": sha256(canonical.encode()).hexdigest(),
            "boundary": "Metadata provenance only. Document hashes are registry assertions, not independently verified source bytes. Metadata hashes cover every original source field; the manifest hash covers schema_version, canonicalization, evidence_version, review_status, reviewed_on and sorted sources including their hashes and retrieval_enabled. Missing document hashes are explicit. No source approval, document ingestion or retrieval is implied."}
