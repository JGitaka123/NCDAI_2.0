# Independent clinical and dose-support validation protocol

Draft 0.1 · 12 September 2026 · Prospective specification for PI review; no results claimed. The owner confirms DHA/ethical approvals cover care and medication recommendations and are held in office files. Capture their references, permitted data sources and release mapping administratively; this draft does not presume missing permission or independent certificate review.

## Objective and evaluated release

Determine whether the frozen NCDAI rules, bounded Kenya-guideline dose modules and constrained AI briefing produce clinically defensible actions and withhold unsupported advice on previously unseen cases. Separate software conformance, clinical recommendation quality and clinician-assisted performance. The primary safety question is whether the system omits a required urgent action or presents a potentially harmful dose decision. No retrospective agreement percentage is reused as ground truth.

Freeze a release manifest containing software commit, migrations, supported modules, exact evidence sections, dose mappings, required input/abstention rules, provider/model/prompt, configuration and UI. If verified-source RAG is included, also freeze permitted document/chunk hashes, retrieval/index settings, ranking and citation mappings; test whether the correct evidence reaches the model and whether unsupported claims are withheld. Source hyperlinks alone do not establish RAG. Register this protocol and a timestamped analysis plan with the institutional study record before independent labels or model outputs are compared. Record permissible model-provider version behavior; a provider change triggers a documented validation decision. No model training is assumed necessary for these functions.

## Case set and independence

Use **900 newly prepared cases**, held by the independent evaluation team, separate from developer-authored regression suites, the original study's 300 reviews and the existing 66 engineering workflows:

| Stratum | Cases | Purpose and sampling |
|---|---:|---|
| Representative clinical spectrum | 300 | Consecutive, approval-permitted deidentified encounters from contrasting proposed facilities, with a declared selection window; retain missing/incomplete cases rather than excluding difficult presentations |
| Acute-safety challenges | 300 | Independently authored or carefully abstracted cases requiring time-sensitive action, spanning cardiovascular, glucose, respiratory, renal/electrolyte and multimorbidity scenarios; source-backed expected urgency determined first |
| Dose/withholding challenges | 300 | 150 in-scope dose-option cases and 150 cases requiring withholding/escalation because of contraindication, missingness, unsupported medicine/context or ambiguity; cover every released module and exact threshold/adjacent value |

Representative cases estimate performance in their sampled clinical spectrum. Enriched challenge cases assess failure modes; do not pool them into an alleged population accuracy/prevalence estimate. Keep all cases from one person, near-duplicate vignette families and facilities used for rule development out of the held-out partition where feasible; record any unavoidable overlap before analysis. Artificial transformations of one case are a family for uncertainty analysis, not independent patients.

Before freeze, the evaluator may use a separate 30-case rubric calibration set; it is excluded from 900. Once a validation failure informs a fix, affected cases become regression tests. Validate the changed release on a newly held-out replacement set for those failure modes and report the original failure; do not report the repaired re-run as an untouched first-pass result.

## Clinical reference standard

Two independent appropriately qualified Kenyan clinicians label each case without seeing NCDAI output or model assignment. At least one pharmacist reviews all medication/dose cases. Neither primary reviewer should have authored the relevant module or have responsibility for selling the product. Disclosures, institutional appointments and evaluator access are recorded; partner participation is not presumed from earlier proposals.

The structured rubric records: in/out of scope; information sufficient for each decision; required immediate/same-day actions; acceptable optional alternatives; contraindicated actions; medicine/indication/formulation/route; acceptable dose/frequency/range and maximum when applicable; required withholding; monitoring; referral; source edition/page; and uncertainty. Scores are based on meaning and allowed clinical alternatives, not text matching. Adjudicate disagreement with a third specialty-qualified reviewer before unblinding system output; preserve initial labels and disagreement reasons. Report raw agreement and chance-corrected agreement with uncertainty, noting prevalence effects.

Unresolvable cases remain identified as indeterminate. They are excluded only from the affected evaluable-reference endpoint, with denominator and reason shown; they remain in input-quality and operational analyses. A sensitivity analysis classifies indeterminate system actions pessimistically. Do not silently discard them to improve results.

## Execution and outcomes

Run the rules/dose engine on the locked inputs, then the AI briefing using the same assessment. Record canonical output and version, abstention/reason, missingness, latency and failure status. Inspect provider payloads using synthetic sentinel values only. AI may organize existing actions but cannot alter dose arithmetic, minimum urgency or critical findings. Repeat three independent provider calls on 100 prespecified cases to quantify selection stability; these 300 calls are repeated observations, not 300 new cases.

Primary safety endpoints are (1) required acute-action detection among the 300 acute challenges, and (2) proportion of 300 dose/withholding challenges with an adjudicated potentially harmful decision. Report appropriate-offer accuracy and correct-withholding separately for their 150-case denominators. Secondary endpoints include clinically material omissions, unnecessary escalation, source/action correctness, exact unit equivalence, calibrated abstention, proportion with no usable output, required input handling and subgroup/module results. All testcases receive a disposition, including failed requests. The [SAP](statistical-analysis-plan.md) defines intervals and denominators.

Potentially harmful means a plausible risk of death, permanent impairment, hospital admission or clinically material deterioration under the stated case if acted on, classified prospectively by the safety panel. It includes unsafe doses and omitted acute escalation. Lesser errors include misleading nonurgent advice, avoidable burden and source mismatch. “No observed error” is not a guarantee of clinical safety.

## Proposed release criteria and failure handling

Before active use, require zero unresolved critical/high-severity defects; zero missed required emergency action in the acute challenge set; zero harmful dose/withholding decision; correct mandatory abstention for every critical missing-context challenge; and zero AI modification of canonical dose/critical safety content. For descriptive accuracy, propose ≥95% appropriate dose offers and ≥95% correct withholding within each relevant stratum, with confidence intervals and per-module results. These are proposed sponsor safety criteria for clinician review, not universal thresholds or regulatory standards. A stratum or module with insufficient cases cannot borrow assurance from a larger unrelated stratum.

Any high-severity defect holds the affected module from the active pilot until clinical cause review, correction and new independent evidence. Do not fix unsafe behavior by relaxing an expected label after seeing output; label correction requires a blinded source-based adjudication record. Moderate defects need documented disposition and impact analysis. The independent safety lead, PI and statistician jointly sign the final validation report, including failures, uncertainty and unresolved boundaries.

Report intended use, dataset provenance, participant/case flow, exact versions, human review, missing inputs, errors and changes. DECIDE-AI applies to the later early live phase; its checklist does not certify this preclinical validation. SPIRIT-AI helps describe input/output and human interaction explicitly. [SPIRIT-AI](https://www.nature.com/articles/s41591-020-1037-7), [DECIDE-AI](https://www.bmj.com/content/377/bmj-2022-070904).
