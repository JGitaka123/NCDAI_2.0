import { test, expect, type Page, type TestInfo } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

// NCDAI Consult at /mobile/ runs entirely on the device and needs no account, so
// these audits run wherever the suite points, including a hosted deployment.
const artifactDir = resolve(process.env.NCDAI_BROWSER_ARTIFACT_DIR || '../.runtime/browser')
mkdirSync(artifactDir, { recursive: true })

const viewports = [
  { name: 'desktop', width: 1366, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'phone', width: 375, height: 812 },
]

async function audit(page: Page, label: string, info: TestInfo) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()
  const report = { label, viewport: page.viewportSize(), violations: results.violations, passes: results.passes.length,
    incomplete: results.incomplete.map(item => ({ id: item.id, impact: item.impact, nodes: item.nodes.length })) }
  writeFileSync(resolve(artifactDir, `${label}-axe.json`), JSON.stringify(report, null, 2))
  await info.attach(`${label}-accessibility`, { body: JSON.stringify(report, null, 2), contentType: 'application/json' })
  // Guideline source links previously failed WCAG 2.2 target size at phone width.
  expect.soft(results.violations.filter(item => ['serious', 'critical'].includes(item.impact || ''))
    .map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) })),
    `${label}: serious/critical accessibility issues`).toEqual([])
  const layout = await page.evaluate(() => ({ width: window.innerWidth, scrollWidth: document.documentElement.scrollWidth }))
  expect.soft(layout.scrollWidth, `${label}: page must fit viewport without horizontal page scrolling`).toBeLessThanOrEqual(layout.width + 1)
}

for (const viewport of viewports) {
  test(`offline consult is accessible at ${viewport.name}`, async ({ page }, info) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/mobile/')
    await expect(page.getByRole('tab', { name: 'Consult' })).toBeVisible()
    await audit(page, `mobile-consult-${viewport.name}`, info)

    await page.getByRole('tab', { name: 'Patient data' }).click()
    await audit(page, `mobile-patient-${viewport.name}`, info)

    // Generating from a bundled fictional example exercises the on-device engine
    // and renders the guideline sources, plans and monitoring the audit must cover.
    await page.getByRole('tab', { name: 'Consult' }).click()
    const examples = page.locator('#examples button')
    await expect(examples.first()).toBeVisible()
    await examples.first().click()
    await page.locator('#generate').click()
    await expect(page.locator('#consult-view')).toContainText(/./)
    await audit(page, `mobile-result-${viewport.name}`, info)
  })
}
