# Browser and accessibility verification

Checked 12 September 2026 against the standalone local application, with the actual backend and a synthetic test account. The interface keeps the NCDAI patient-and-encounter workflow while improving readable clinical content, explicit review, and referral follow-through.

## Observed results

| Check | Result | Scope |
|---|---|---|
| Browser suite | 5 tests passed | Bundled Chromium 153; reproducible Playwright tests |
| Complete care workflow | Passed at all three viewports | One representative emergency scenario repeated at desktop 1366×900, tablet 768×1024 and mobile 375×812 |
| Automated accessibility | 20 rendered-view audits; zero reported violations | Six views at each viewport, mobile navigation and the administrator audit screen |
| Keyboard workflow | Passed | Login, mobile menu focus containment, reverse/forward Tab wrapping, Escape and focus restoration, patient navigation, required-field handling |
| Administrator interface | Passed | Simulated administrator response; only audit navigation rendered and no clinical API request issued |
| Frontend unit checks | 21 passed | Separate tests for clinical input handling, review behavior and interface safety |
| Production build | Passed | TypeScript and Vite build |

The complete browser workflow creates a fictional patient, records current BP, pulse, oxygen saturation, respiratory rate, symptoms, NCD history, glucose, HbA1c, eGFR, potassium and medication/allergy review. It confirms emergency escalation, inspects each supporting source, checks that incomplete review is rejected, records a decision for every recommendation, verifies the locked encounter, creates a referral, accepts and completes it, verifies the patient name and record ID, and downloads a FHIR Bundle containing the patient resource.

This is one clinical scenario tested across three screen sizes. It is additional to the repository's broader synthetic case catalogue and API workflow tests; it is not 50 distinct browser cases.

## Problems corrected during testing

- Local sign-in failed when the development proxy changed the request host. The proxy now preserves the host; the backend also supports an explicitly configured public origin.
- Subdued supporting text and clinical badges failed contrast checks. Text and badge colors were corrected and small supporting text enlarged.
- A visually hidden patient-table heading escaped its scroll container and widened mobile/tablet pages. The table now has a containing block, with scrolling confined to the table.
- Closed mobile navigation remained available to keyboard and accessibility traversal. It now becomes inert and hidden, contains focus when open, closes on Escape and restores focus.
- Clinical tabs now support arrow keys, Home and End, with associated panel semantics.
- Administrator accounts now open the audit workspace and do not expose clinical navigation.
- Referral cards identify the patient by name and record ID, reducing reliance on internal identifiers.
- Review validation messages clear when the clinician changes a decision, avoiding a stale message after the missing decisions have been supplied.

## Screenshots and evidence

The screenshots contain fictional records only.

| View | Desktop | Tablet | Mobile |
|---|---|---|---|
| Sign-in | [Image](images/desktop-login.png) | [Image](images/tablet-login.png) | [Image](images/mobile-login.png) |
| Overview | [Image](images/desktop-dashboard.png) | [Image](images/tablet-dashboard.png) | [Image](images/mobile-dashboard.png) |
| Clinical intake | [Image](images/desktop-intake.png) | [Image](images/tablet-intake.png) | [Image](images/mobile-intake.png) |
| Assessment | [Image](images/desktop-assessment.png) | [Image](images/tablet-assessment.png) | [Image](images/mobile-assessment.png) |
| Referral follow-through | [Image](images/desktop-referrals.png) | [Image](images/tablet-referrals.png) | [Image](images/mobile-referrals.png) |

See the [machine-readable accessibility summary](quality/browser-accessibility-summary.json) and [reproduction instructions](../frontend/tests/browser/README.md). Detailed local Playwright and axe outputs remain in ignored test directories. No credentials are included in committed reports.

## Limits of this evidence

Automated rules cannot establish full accessibility. Axe returned some contrast checks for manual review; their identifiers and counts are retained in the summary. Representative screenshots were visually inspected, but testing with screen-reader users, clinician usability sessions, text magnification and additional browsers remains necessary. These results are not a WCAG certification, clinical validation, or proof of safe patient-care performance.

These browser tests do not make external AI calls or connect to an EMR. Provider verification and the broader backend case suite have separate evidence. Referral status records workflow progress; it does not transmit a message to the receiving service.
