# Kenya knowledge, retrieval and model training strategy

Decision record · 12 September 2026

**Use a maintained Kenya guideline knowledge base, deterministic clinical/dose rules and constrained AI assistance. Do not fine-tune the model merely to memorise guideline PDFs.** This is the recommended next architecture, not a claim that a complete RAG service or custom-trained model is already deployed.

The existing application evaluates structured observations with explicit rules. Optional DeepSeek assistance selects existing recommendation identifiers; the server renders their original text and evidence. It does not fine-tune model weights, retrieve arbitrary guideline passages or generate prescriptions. Adding bibliographic links is not equivalent to implementing RAG. The dose extension adds four bounded medicine references and separate versioned provenance. These distinctions must appear in grant, patient-facing and scientific descriptions.

## Why retrieval comes first

RAG supplies information from a separate knowledge base at response time; the underlying model need not be retrained whenever a source changes. That makes it suitable for maintaining inspectable national guidance. Retrieval can still return the wrong passage, omit a qualification, or expose the model to malicious document text. It cannot alone guarantee a correct answer. [NIST RAG definition](https://csrc.nist.gov/glossary/term/retrieval_augmented_generation), [NIST Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf).

Fine-tuning changes model behaviour using examples. It may help later with consistent clinical summaries, terminology, structured extraction or English/Kiswahili communication. It is not the authoritative store for changing dose limits or a replacement for tested contraindication rules. Training on a small set of guideline PDFs or the same cases used for testing would not demonstrate generalisation. The recommendation here is an engineering judgment for NCDAI, not a claim that RAG always outperforms fine-tuning in every medical task.

## Knowledge release pipeline

1. **Acquire controlled sources.** Start with Kenya Ministry of Health NCD protocols, then the referenced national disease-specific guidelines, Kenya Essential Medicines List and applicable product/formulary information. Record publisher, original URL, actual edition/date when available, retrieval time, file SHA256, pages, rights to store/process and intended population. A file upload date is not its edition date. Keep private patient data outside the guideline corpus.
2. **Verify extraction.** Preserve headings, table row/column relationships, dosage units, route, formulation, footnotes and flowchart branches. Visually compare dose and threshold tables with originals. Tag uncertain OCR or missing limits; never fill them using the LLM. The inspected primary-care PDF has 132 pages and SHA256 `e836eef61b8739db399e5af9ce75754b7836bf84693130f41bfa3107c27f78e8`; it is hosted in the MOH July 2025 directory without an explicit edition date found on the inspected opening pages.
3. **Adjudicate local applicability.** Clinical and pharmacy reviewers assign effective dates, care level, age/pregnancy/organ-function applicability, version status and supersession. Kenya guidance is the local starting point; newer drug safety information or conflicts require explicit adjudication, not silent source precedence. Record the reason for each adopted adaptation. Conflicted sources cannot support an automatic dose.
4. **Publish an immutable corpus release.** Each passage needs a stable identifier, text hash, document/page/section anchor, topic, population, date, review record, status and replacement pointer. Keep draft, active and retired passages distinct. Guideline documents are untrusted data, never instructions to the assistant or application.
5. **Retrieve narrowly.** Filter active, applicable sources by disease, task, setting and population before retrieval. Benchmark lexical search against lexical-plus-embedding retrieval and optional reranking. Choose the simplest method that meets the predeclared retrieval targets; a vector database alone does not establish RAG quality. PostgreSQL can hold the manifest, review history and retrieval logs; an embedding extension is an implementation option to test, not an existing installed capability.
6. **Check sufficiency and conflict.** Require supporting passage IDs for each factual output; missing, incompatible or low-confidence evidence yields a clear abstention. No live open-web search during an encounter. Source updates go through a staged release with regression tests and rollback.
7. **Generate or select within bounds.** Initially retain canonical advice and evidence selection. A future explanation generator receives only the minimum necessary approved context. Validate structured output and citation identifiers. Medication calculations, danger alerts, referral urgency and contraindication blocks remain in deterministic code. Retrieved text cannot change those controls.
8. **Record provenance.** Save corpus, source/passage, rules, dose manifest, prompt, provider/model, retrieval configuration, result and clinician decision with the encounter. A historic record must remain reproducible after a source or model update. Monitor source expiry, retrieval gaps, clinician overrides, adverse events, response time and cost.

This separation addresses the limitations of generative health models and the need for evaluation in their intended use. [WHO guidance on large multimodal models for health](https://www.who.int/publications/i/item/9789240084759).

## Evaluation before model changes

Use separate development, tuning and locked test partitions with independently adjudicated expected actions, prohibited actions, source passages and acceptable abstentions. Split related encounters/patients together; where feasible retain external facilities and later time periods for transportability testing. Search the development corpus for near-duplicates before freezing the test set. Never train on held-out evaluation labels or treat model-generated agreement as clinical consensus.

Compare the same cases across: rules/dose engine alone; rules plus the current constrained briefing; rules plus verified-source retrieval and constrained explanation; and, only if warranted, the same retrieval system with a fine-tuned model. Report incremental benefit separately from the underlying rules. Keep provider/model versions and prompt/retrieval settings fixed within each comparison.

| Component | Required evidence |
|---|---|
| Retrieval | Relevant passage recall at the selected retrieval depth, irrelevant retrieval, wrong-population/retired-source retrieval, conflicts, table/footnote preservation, latency |
| Clinical/dosing | Correct action and withholding; dose/route/formulation/unit and daily-limit boundaries; danger detection; contraindications; source concordance; missing-data behaviour |
| AI explanation | Claim-by-claim support, citation correctness, invented facts, completeness, prohibited dose/action generation, appropriate abstention, prompt-injection resistance |
| Clinical workflow | Clinician comprehension, task completion, time, override reasons, alert burden, delayed care and differences across professions, sites and patient subgroups |
| Operations | Availability, cost per completed encounter, provider outage fallback, audit integrity, account/facility isolation and release rollback |

Predeclare clinically meaningful tolerances and confidence intervals; an average answer-quality score cannot compensate for a dangerous dose or missed emergency. The evaluation package proposes 900 new blinded cases in three distinct strata and a staged clinical study. These are planned samples, not completed results. [Validation protocol](evaluation/validation-protocol.md), [statistical analysis plan](evaluation/statistical-analysis-plan.md).

## When to fine-tune

Proceed only when a documented residual problem persists after source quality, retrieval, prompt and interface improvements; an appropriate provider capability and processing arrangement are verified; licensed/de-identified examples are available; and clinical reviewers can label the target behaviour. No fine-tuning service availability is assumed merely because an API key exists.

Create paired clinician-approved examples of the target task, include difficult negative/abstention examples, deduplicate and version them, keep facility/patient isolation across partitions, and track reviewer disagreement. Prefer narrow, measurable tasks. Run the frozen benchmark against the untuned baseline, require a prespecified improvement without safety regression, and retain a rollback path. Costs and sample size should be estimated from a small learning-curve experiment, not an arbitrary promise that a particular number of examples will suffice.

Do not use the deployed patient record store as an automatic training feed. Do not let accepting a recommendation become a correct-answer label. Research consent/processing scope and provenance must be respected under the owner's confirmed approvals. Staff training is a separate workstream: simulation-based onboarding, interpreting uncertainty, medicine checks, escalation, incident reporting and competency assessment remain necessary even when the software improves.

## Current next steps

The owner reports DHA and ethics approvals in office files covering care and medication recommendations. Record their identifiers administratively without treating this as a missing authorisation. Complete the engineering verification of the dose extension; obtain independent clinical/pharmacy adjudication of the knowledge/rule manifest; build and benchmark the controlled retrieval corpus; then evaluate incremental AI benefit before proposing fine-tuning. EMR adapters follow the standalone workflow once Aifya and QAfya API documentation is supplied. No custom model has been trained in this work.
