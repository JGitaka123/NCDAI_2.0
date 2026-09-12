import { readFileSync, readdirSync, statSync, mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const input = resolve('../.runtime/browser')
const run = JSON.parse(readFileSync(resolve(input, 'results.json'), 'utf8'))
const started = Date.parse(run.stats.startTime)
if (run.stats.unexpected || run.stats.skipped || run.stats.flaky || run.stats.expected !== 5) {
  throw new Error('A complete successful five-test run is required before publishing the accessibility summary.')
}
const views = readdirSync(input).filter(name => name.endsWith('-axe.json')).map(name => {
  const path = resolve(input, name)
  if (statSync(path).mtimeMs < started) throw new Error(`Stale audit result: ${name}`)
  const result = JSON.parse(readFileSync(path, 'utf8'))
  return {
    view: result.label,
    viewport: result.viewport,
    violations: result.violations.length,
    serious_or_critical: result.violations.filter(item => ['serious', 'critical'].includes(item.impact)).length,
    automated_checks_passed: result.passes,
    manual_review_checks: result.incomplete,
  }
})
if (views.length !== 20) throw new Error('Expected 20 audits from this browser run.')
const destination = resolve('../docs/quality')
mkdirSync(destination, { recursive: true })
writeFileSync(resolve(destination, 'browser-accessibility-summary.json'), JSON.stringify({
  checked_on: run.stats.startTime,
  playwright_version: run.config.version,
  browser: process.env.NCDAI_BROWSER_CHANNEL || 'Bundled Chromium',
  scope: 'Synthetic standalone application; engineering verification, not clinical validation or WCAG certification',
  test_results: run.stats,
  views,
}, null, 2) + '\n')
console.log(`Published ${views.length} current-run accessibility audits; ${views.reduce((total, view) => total + view.violations, 0)} reported violations.`)
