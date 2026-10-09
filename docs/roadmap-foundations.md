# Review foundations, 9 October 2026

This branch is a proposed clinical-review release. Do not deploy it for clinical testing until the clinical lead approves the changed missing-input behavior and the release evidence. Engineering test success does not establish clinical validity.

## Implemented for review

- Numeric Framingham estimates require explicit current, former or never tobacco status. Absent, null and unknown status no longer become non-smoking. Established-disease categories remain available. The consultant reasoning version is `ncdai-consultant-1.1.0-review`; Python and offline JavaScript change together. The model remains Framingham and remains explicitly not calibrated for Kenya. Other model-input missingness and regional model selection need separate adjudication.
- The longitudinal overview adds the five most recently saved visits in a measurement table. It distinguishes observation timestamps from save timestamps, retains missing values, shows draft/review status and does not interpret change or carry values forward. Encounter listing is capped by the existing API; this is not a complete lifetime history.
- `python scripts/build_evidence_manifest.py` exports deterministic source metadata hashes, the evidence-package hash, proposed review status and document hashes where recorded. Missing document checksums remain null and retrieval stays disabled. Metadata checksums are not proof that a linked source document is unchanged, clinically approved or licensed for ingestion.

## Staged next work

1. Controlled Kenyan guideline retrieval: obtain authoritative permitted copies, hash exact documents, preserve page/chunk provenance, record clinician-approved indication and exclusion coverage, then evaluate citation correctness and abstention before enabling retrieval. The existing source registry already supplies citations; this branch adds package provenance rather than claiming a completed RAG service.
2. Longitudinal reasoning: clinician-reviewed observation chronology, explicit units and measurement provenance, pagination of all visits and adjudicated trend/trajectory rules. The new table is observational only.
3. Medication reconciliation: verify the existing renal/contraindication checks; add approved local formulary availability, reconciliation discrepancies and review provenance. Do not generate new doses or replace the four bounded dose references without pharmacy validation.
4. Regional risk: compare a versioned WHO Eastern sub-Saharan model against published reference cases and local calibration data. Missing tobacco is addressed here; comprehensive required-input and scope checks remain a separate validation task.
5. Clinical evaluation dashboard: predefine denominators for rule sensitivity, false alerts, clinician overrides, missing inputs and referral completion, separating synthetic engineering tests from prospective adjudicated clinical outcomes. Use facility-scoped aggregates and suppression of small groups; do not transmit patient-level data to analytics services.

## Operational findings

The manual production workflow accepts arbitrary refs and deploys before its smoke tests. It does not enforce successful quality jobs for that SHA. The engineering release was gated manually on all three successful CI jobs; encode the same gate before a future workflow release.

Hosted backup/PITR retention remains unverified in the existing operational documentation. A successful logical fictional restore is not proof of managed production backup retention or measured cloud RPO/RTO. Verify both primary and consultant recovery settings with the owner.

Audit hash chains exist, but external anchoring of retained head hashes is still required to detect whole-history replacement or tail deletion. Existing roles, scoped reads, reviewed-snapshot immutability, CSRF and cookie controls are implemented; this review does not constitute a penetration test.
