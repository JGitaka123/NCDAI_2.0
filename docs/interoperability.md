# Interoperability contract and review

NCDAI 2.0 is a standalone application. Its authenticated patient and encounter exports are a limited FHIR R4 exchange surface; Aifya EMR and QAfya are future integration targets. No vendor connection, SMART launch, CDS Hooks service, write-back, national profile conformance, or patient matching service is implemented or claimed.

## Current export semantics

`GET /api/fhir/Patient/{id}` returns a Patient. `GET /api/fhir/Bundle/{encounter_id}` returns a collection Bundle containing Patient, Encounter, populated numeric Observations and, after review, a DocumentReference with the clinician's decision record. Existing clinical permissions, facility isolation and export audit logging apply. Exports contain sensitive record content and must use approved destinations.

The collection has unique full URLs and internally resolvable patient and encounter references. `https://ncdai.example/fhir/` is a reserved, non-production identity namespace used for the export; it does not advertise a remotely accessible FHIR server. Receivers must resolve references inside the Bundle. IDs remain stable between exports, while the Bundle timestamp records assembly time. A collection is not a FHIR document Bundle or a transaction request. See [HL7 R4 Bundle](https://hl7.org/fhir/R4/bundle.html) and [references](https://hl7.org/fhir/R4/references.html).

| Measurement | Export representation |
| --- | --- |
| Blood pressure | LOINC 85354-9 panel; components 8480-6 and 8462-4; UCUM `mm[Hg]`; repeat retained as a separate observation |
| Heart and respiratory rate | LOINC 8867-4 and 9279-1; UCUM `/min` |
| Pulse oximetry | LOINC 59408-5; UCUM `%` |
| HbA1c | LOINC 4548-4; UCUM `%` |
| Potassium | LOINC 2823-3; UCUM `mmol/L` |
| Glucose | [2339-0](https://loinc.org/2339-0/) for mg/dL; [15074-8](https://loinc.org/15074-8/) for mmol/L; original value and unit preserved |
| eGFR | Explicit local code `egfr-unspecified-method`; UCUM `mL/min/{1.73_m2}`; no unsupported CKD-EPI/MDRD claim |

Unknown measurement time is omitted, with an explanatory note. Record entry time is never substituted for measurement time. A single recorded observation time currently applies to the intake; independent specimen and repeat-reading times are not captured. Repeat BP includes this limitation in a note. Receiving systems must not derive longitudinal ordering more precise than the source supports. [HL7 Observation effective time](https://hl7.org/fhir/R4/observation-definitions.html#Observation.effective_x_).

Draft observations are preliminary. Reviewed observations use the immutable reviewed input snapshot and are final for this NCDAI record; this does not establish independent laboratory verification. A reviewed Encounter is represented as finished according to the application review workflow; a receiving system must not infer hospital discharge or completion of an external episode. Patient demographics are the local current record; the reviewed clinical snapshot does not freeze a separate historical demographic copy.

The final decision document uses the immutable assessment snapshot, includes accepted/modified/deferred/rejected actions, modified text, reasons, clinician review note, reviewer local identity, review time, assessment/input version and source provenance. It does not generate medication orders or assert a digital signature. No unsupported FHIR extension or national profile is declared. See [DocumentReference](https://hl7.org/fhir/R4/documentreference-definitions.html).

Symptoms, known-condition flags, medication history, allergies, referrals and AI briefing are not yet exported as structured FHIR resources. A negative history must not be inferred from their absence. This export is not a complete medical record. Future mappings must preserve unknown, explicitly absent, recorded and clinically verified states separately.

## Future Aifya and QAfya integration requirements

After the user provides each vendor's API and sandbox, agree supported versions, authentication/scopes, patient identifiers, facility identifiers, clinical workflow and permitted read/write actions. Keep separate vendor adapters behind a common internal contract; do not guess vendor URLs or payloads.

1. Define the source of truth by field. Normally the EMR owns patient identity, source measurements, prescriptions and encounter state; NCDAI owns its decision assessment and clinician review. This must be confirmed per deployment.
2. Map identifiers using issuer plus identifier, never a bare number or name. Ambiguous patient matches require clinician resolution and an auditable crosswalk; no automatic merge.
3. Preserve source resource ID, version, collection time, units, terminology system/version and provenance. Reject incompatible units, unknown required terminology and contradictory facts into a visible reconciliation queue.
4. Use a durable outbox and idempotency key based on facility, vendor, encounter and reviewed assessment/version. Retries must not duplicate observations or orders. Record acknowledgements and delivery attempts without credential leakage.
5. Reconcile updates against the last imported/exported version; stale edits fail visibly. Never overwrite a newer clinical record using a retry. Expose disconnected, pending, failed and confirmed states to clinicians.
6. Export only explicitly clinician-approved content. Signed-off records require amendment workflows, not silent replacement. Medication recommendations remain decision records unless the vendor workflow separately authorizes prescription creation.
7. Validate against the exact agreed FHIR R4 profiles and terminology, then run sandbox contract tests for duplicate delivery, delayed/out-of-order messages, revocation, tenant mix-ups, inconsistent units, patient mismatch, time zones, source correction and partial failure.

The current targeted tests verify resource identity, references, required selected fields, glucose property/unit pairing, unknown timing, repeat BP, eGFR method uncertainty, snapshot immutability and final decision provenance. They are engineering contract checks, not the official HL7 validator, national certification, real EMR interoperability testing or clinical validation. Full profile and terminology-server validation remains an integration acceptance requirement.
