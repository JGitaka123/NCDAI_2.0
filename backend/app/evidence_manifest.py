"""Reproducible provenance for a proposed evidence package; no network or approval."""
from hashlib import sha256
import json
import re
from .evidence import registry


def manifest() -> dict:
    package = registry()
    records = []
    for source in sorted(package["sources"], key=lambda item: item["source_id"]):
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        document_hash = re.search(r"SHA256 ([a-f0-9]{64})", source["version"])
        records.append({
            **source,
            "metadata_sha256": sha256(canonical.encode()).hexdigest(),
            "document_sha256": document_hash.group(1) if document_hash else None,
            "retrieval_enabled": False,
        })
    payload = {"evidence_version": package["version"], "review_status": package["review_status"],
               "reviewed_on": package["reviewed_on"], "sources": records}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {**payload, "manifest_sha256": sha256(canonical.encode()).hexdigest(),
            "boundary": "Metadata provenance only. Missing document hashes are explicit. No source approval, document ingestion or retrieval is implied."}
