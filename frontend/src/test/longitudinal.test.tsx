import { render, screen, within } from '@testing-library/react'
import { expect, it } from 'vitest'
import LongitudinalMeasures from '../LongitudinalMeasures'
import { emptyClinicalData } from '../clinical'
import type { Encounter } from '../types'

it('keeps missing values and observation timestamps distinct from save time', () => {
  const records = [
    { id: 'older', created_at: '2026-09-01', status: 'reviewed', data: { ...emptyClinicalData(), observed_at: '2026-08-30', systolic_bp: 140 } },
    { id: 'newer', created_at: '2026-10-01', status: 'draft', data: { ...emptyClinicalData(), observed_at: null, systolic_bp: 0 } },
  ] as Encounter[]
  render(<LongitudinalMeasures records={records} />)
  const rows = screen.getAllByRole('row')
  expect(within(rows[1]).getByText('Observation time not recorded')).toBeVisible()
  expect(within(rows[1]).getByText('0')).toBeVisible()
  expect(within(rows[1]).getAllByText('Not recorded')).toHaveLength(3)
  expect(within(rows[2]).getByText('2026-08-30')).toBeVisible()
  expect(records[0].id).toBe('older')
})
