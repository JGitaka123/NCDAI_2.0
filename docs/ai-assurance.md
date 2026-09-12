# Optional AI briefing: implementation and assurance

NCDAI 2.0 uses an optional language model to select a short, coherent consultation briefing from the current deterministic assessment. For example, a clinician can see kidney-function and medication-safety items together, followed by missing information to obtain. This is a limited organizational aid. It is not a second diagnostic opinion, an independent treatment recommendation, a replacement for the complete assessment, or evidence of improved clinical outcomes.

The standalone application works with the provider disabled. No AI provider participates in generating or suppressing the clinical rules. The current release accepts synthetic records only.

## Data flow and safety contract

1. A clinician explicitly requests a briefing for a current assessment. The application checks facility access, role, synthetic-record status, assessment ID and encounter version.
2. The adapter accepts only recognized rule IDs, categories, severities, missing-information IDs, the current evidence version and exact registry sources. New clinical rules or evidence changes require updating and testing this boundary.
3. The provider receives rule/category/severity identifiers, coded missing-information identifiers and the deterministic urgency. It receives no patient or encounter identifier, age, sex, numerical measurements, notes, phone number, medication text, allergy text, or recommendation prose. Coded rules still convey health-related information; this is data minimization, not an assertion of anonymity for future clinical use.
4. The model returns only two arrays: up to three existing non-critical rule IDs and up to four existing missing-information IDs. The response schema has no narrative, diagnosis, medicine, dose, urgency, URL, source-generation or tool-execution field.
5. The server rejects malformed JSON, duplicate keys, extra fields, null lists, invented IDs, duplicated selections, critical IDs selected in the wrong field, an empty actionable shortlist, incomplete output, changed model family and invalid token metadata.
6. The renderer retrieves all text and evidence from the original server assessment. Every critical recommendation is retained before any provider request. The model cannot remove those items or lower urgency. The full original recommendation list remains available and unchanged.
7. The saved result identifies the exact assessment, evidence version, requested/returned model name, prompt version, status, safe failure reason, timing and token counts when available. The endpoint rechecks the current encounter and authorization after the network request and rejects a stale result. Reviewed encounters are immutable.

The model may select a suboptimal shortlist despite complying with this schema. That residual risk requires clinician usability evaluation; structured output alone cannot establish clinical usefulness. A successful model request proves only the constrained integration contract exercised here.

## Provider configuration

Set configuration in the backend process environment. Never put API keys into browser code, URLs, repository files or patient notes.

| Setting | Purpose |
|---|---|
| `NCDAI_AI_PROVIDER` | `disabled` by default; opt in with `deepseek` or `openai` |
| `DEEPSEEK_API_KEY` | Server-only DeepSeek credential |
| `NCDAI_AI_MODEL` | Explicit model; DeepSeek defaults to verified `deepseek-v4-pro`; OpenAI requires an explicit compatible model |
| `OPENAI_API_KEY` | Server-only OpenAI credential when that provider is selected |

On 12 September 2026, a credentialed read-only DeepSeek model-discovery request returned `deepseek-flash` and `deepseek-v4-pro`. The tests used `deepseek-v4-pro`. This name is a provider-controlled model identifier, not an immutable model-weight snapshot. Re-run the provider acceptance suite after any model, prompt, schema or rule change.

DeepSeek uses its documented Chat Completions JSON-object mode, an explicit JSON-only prompt, disabled thinking for this small selection task, a 600-token output cap and local strict schema validation. JSON mode does not itself guarantee the application schema. See [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) and [JSON Output](https://api-docs.deepseek.com/guides/json_mode/), retrieved 12 September 2026.

The OpenAI adapter uses Responses with a strict JSON schema under `text.format`, `store: false`, and an 800-token output cap. It does not create a conversation, use previous-response IDs or expose tools. Its request/response contract has simulated transport tests; no live OpenAI request was made in this workstream. `store: false` is an API request setting, not a claim of zero provider retention. See [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), retrieved 12 September 2026.

## Failure and operating limits

At most one request is allowed per invocation, with a 20-second overall deadline, a 5-second connection timeout, and a 64 KiB response-body limit. When no eligible non-critical item or missing-information choice exists, the adapter makes no paid request and returns `disabled / no_selectable_items` with the established critical items. There are no automatic retries, provider switching, HTTP redirects, tool calls or environment-proxy inheritance. A failed request returns a safe reason code and the already established critical items. Provider errors and raw response bodies are not returned to the application or logged by the adapter. The credential is excluded from the settings representation.

The endpoint must enforce authenticated usage, preserve an audit event and concurrency checks, and avoid holding a database transaction across the network call. Provider spend limits, capacity controls, retention agreements and production monitoring must be established before real clinical use. The code's synthetic-only guard is deliberately mandatory for this release.

## Reproducible assurance

From `backend`, run the normal test suite; `tests/test_ai.py` runs deterministic mock-transport tests and skips paid live calls. To explicitly enable the eight live synthetic tests, set `NCDAI_LIVE_AI_TESTS=1` and provide `DEEPSEEK_API_KEY`, then run that test file. The live test output contains case ID, status, safe reason, model/prompt version, timing, token counts and selected canonical IDs. It contains no credential or patient identity.

The final eight live cases span severe BP, raised BP and adherence, missing diabetes measurements, kidney disease with metformin, chronic respiratory disease, cancer warning symptoms, pregnancy with severe BP, and unreviewed medication/allergy histories. Unit tests additionally cover hypoglycaemia, severe kidney impairment, hypoxemia, empty selection tasks, input injection and a provider outage. Full standalone encounter-workflow testing is reported separately; these eight are provider-contract tests, not eight clinical validations.

The first live v1.0 run accepted seven of eight outputs and rejected one malformed hypoxemia response. The original emergency assessment was unchanged. An isolated repeat returned valid JSON. The same run exposed occasional empty selections despite available warning rules. Version 1.1 added an explicit non-empty requirement and rejected one empty actionable shortlist in its eight-case run; all critical items remained present. Version 1.2 separates eligible selections from locked critical IDs in the request and skips selection tasks with no useful choice. The final case set therefore covers eight actual selection tasks. There is no automatic retry to hide failures; the earlier failures remain part of the development evidence.

Final execution on 12 September 2026: **50 deterministic assurance tests and eight real DeepSeek synthetic selection tests passed** (58 total). The provider returned `deepseek-v4-pro`, prompt `ncdai-briefing-select-v1.2`. No original assessment changed; all critical items and urgency were preserved in every test. The eight calls used 2,571 input tokens and 250 output tokens (2,821 total). Observed latency ranged from 2.016 to 2.703 seconds in this small run; this is not a production latency guarantee.

| Case | Scenario | Provider status | Latency, ms | Input / output tokens |
|---|---|---|---:|---:|
| NCD-003 | Severe BP and missing repeat measurement | Ready | 2,016 | 298 / 26 |
| NCD-011 | Raised BP, diabetes confirmation and adherence | Ready | 2,141 | 352 / 43 |
| NCD-023 | Missing diabetes measurements | Ready | 2,531 | 314 / 34 |
| NCD-029 | Kidney disease and metformin review | Ready | 2,140 | 327 / 25 |
| NCD-046 | Chronic respiratory disease and tobacco use | Ready | 2,703 | 329 / 22 |
| NCD-049 | Cancer warning symptoms | Ready | 2,422 | 307 / 28 |
| NCD-055 | Pregnancy with severe BP | Ready | 2,610 | 324 / 34 |
| NCD-060 | Medication and allergy history not reviewed | Ready | 2,188 | 320 / 38 |

The final live responses passed the **selection-safety contract**, not a clinician-rated completeness or usefulness benchmark. For example, the chronic respiratory case's model focus selected a diabetes-confirmation item while the full canonical respiratory recommendation remained on the assessment. This illustrates why the shortlist must never replace review of every recommendation and why clinical usability evaluation is still required.

## Required evidence before clinical deployment

Independent clinical approval of the underlying rules; clinician assessment of shortlist usefulness and omitted context; repeated-run provider stability and multilingual evaluation; prospective human-factors testing; privacy and cross-border processing review for the chosen provider contract; operational rate/spend limits and monitoring; and prospective clinical validation remain separate release gates. Synthetic engineering tests do not satisfy those gates.
