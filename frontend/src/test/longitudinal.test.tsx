import { cleanup, render, screen, within } from '@testing-library/react'
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

it('hides the comparison for zero or one encounter', () => {
  const { rerender, container } = render(<LongitudinalMeasures records={[]} />)
  expect(container).toBeEmptyDOMElement()
  rerender(<LongitudinalMeasures records={[{ id: 'single' } as Encounter]} />)
  expect(container).toBeEmptyDOMElement()
})

it('limits to five created encounters without reordering the input or using updated or observation time', () => {
  cleanup()
  const records = Array.from({ length: 6 }, (_, i) => ({
    id: String(i), created_at: `2026-10-0${i + 1}`, updated_at: `2026-10-0${6 - i}`,
    status: i % 2 ? 'reviewed' : 'draft',
    data: { ...emptyClinicalData(), observed_at: `2026-09-0${6 - i}`, systolic_bp: 100 + i },
  })) as Encounter[]
  render(<LongitudinalMeasures records={records} />)
  const rows = screen.getAllByRole('row').slice(1)
  expect(rows).toHaveLength(5)
  expect(rows.map(row => within(row).getByText(/^10[1-5]$/).textContent)).toEqual(['105', '104', '103', '102', '101'])
  expect(within(rows[0]).getByText('2026-09-01')).toBeVisible()
  expect(within(rows[0]).getByText('Created: 2026-10-06')).toBeVisible()
  expect(within(rows[0]).getByText('reviewed')).toBeVisible()
  expect(within(rows[1]).getByText('draft')).toBeVisible()
  expect(records.map(record => record.id)).toEqual(['0', '1', '2', '3', '4', '5'])
})
