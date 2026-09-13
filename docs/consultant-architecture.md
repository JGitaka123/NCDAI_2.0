# Consultant review architecture

The consultant interface is a distinct workspace at `/consultant` in the NCDAI 2.0 repository and deployment. A second repository is not required for role separation and would add interface-version coordination for this initial hospital test. The consultant records have their **own PostgreSQL database**, `ncdai_consultant`, in the approved Frankfurt Neon project, and a separate restricted credential. This is a separate logical database, not a second physical cluster or independent availability region.

## Boundaries and persistence

The primary database retains facilities, named users/sessions, patients, encounters and the append-only `consultation_requests` outbox and `consultation_dispositions`. Consultant storage retains `consultant_cases`, immutable `consultant_opinions` and its version marker. No patient directory, passwords or login sessions are replicated. The backend checks primary authentication, role and facility on every consultant request. The interface displays patient identity from the authorized primary record; the preserved consultant snapshot contains age, sex, structured case information, clinical notes and the original assessment, without copying directory names or contact fields. Clinical notes can still be identifying, so this database is health-data storage, not an anonymous dataset.

Both database credentials reside only in the backend runtime. Consultant storage grants SELECT/INSERT for its case/opinion tables, no UPDATE/DELETE or schema creation. The primary role can insert the outbox/disposition but cannot update/delete them. Database triggers enforce immutability; administrators owning databases remain a separate trusted maintenance boundary. One backend process holds both runtime credentials, so this design does not claim isolation from compromise of that process.

## Delivery and disagreement lifecycle

1. A primary clinician requests review against an exact encounter version and assessment ID. Selected rule IDs must exist. A UUID submission key and payload hash prevent duplicate or conflicting retries. The immutable snapshot includes the clinical inputs, evidence/rule/model/dose metadata, reason and immediate action. Its SHA256 is persisted with the request.
2. The request is committed and audited in the primary database first. It is the durable outbox. A separate authenticated POST copies it to the consultant database using the same ID and checks identical hashes. An outage cannot erase the request. Delivery can be retried from either workspace; there is no claim of a background delivery worker.
3. A supervisor/consultant who did not request the review signs one immutable opinion with agreement, clinical assessment, action, urgency, rationale, source references, reviewer identity and time. The database primary key prevents duplicate answers. A changed opinion requires a new consultation, not editing clinical history.
4. A different primary clinician records the action actually taken. The application checks the opinion hash and current encounter version. It requires explicit acknowledgement when the snapshot is older than the current encounter. An immutable copy of the acknowledged opinion is retained with the primary disposition for recovery and export.
5. The original assessment and clinician review are not overwritten. Urgent care is never locked pending a consultant answer. FHIR export appends a linked DocumentReference for the request and, once acknowledged, the consultant opinion and primary action.

The primary request row serializes simultaneous delivery/opinion/disposition operations. User and session locks plus renewed authorization prevent stale permissions after a lock wait. No cross-database atomic transaction is claimed: the committed outbox and idempotent delivery recover the handoff; immutable opinions survive a lost HTTP response and identical resubmission returns the saved result. A failed final disposition can be retried without rewriting the opinion.

## Traceability and evaluation

Preserved IDs link facility, patient, encounter, original assessment/version, selected recommendations, request, consultant, opinion hash, primary clinician and final action. Primary chart/consultation-detail reads and mutations are audited; consultant opinions carry immutable author/time metadata in their own database. Hash comparisons detect disagreement between the primary snapshot and consultant copy. Hashes are not digital signatures or independent external audit anchoring.

The authenticated evaluation endpoint reports request, answer, pending and closed episode counts, agreement categories, action categories and median response time. Fictional versus clinical records are explicitly separated. Unavailable remote records are identified rather than assumed unanswered; response statistics can be incomplete during an outage. No accuracy, causal benefit, all-case review compliance or outcome result is inferred from these counts.

## Recovery and operating limits

Back up and recover both databases. The primary outbox can reconstruct missing consultant case deliveries; it cannot reconstruct an unacknowledged consultant opinion that was lost from the consultant database. Completed primary dispositions contain the acknowledged opinion and its hash. Reconcile both stores and validate hashes before switching a restored service into use. Default provider retention and a successful logical snapshot are not substitutes for an agreed retention/PITR plan.

A scheduled GitHub health workflow probes both services without record data. Actual email alert delivery, 24-hour consultant staffing, high availability and an RPO/RTO guarantee are not claimed. The hospital uses direct escalation during supervised testing. [Hospital testing guide](mary-help-testing-guide.md).
