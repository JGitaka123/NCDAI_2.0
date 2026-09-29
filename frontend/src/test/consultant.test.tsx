import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ConsultantSynthesis from '../ConsultantSynthesis'
import type { ConsultantSynthesis as Synthesis } from '../types'
import fixture from './fixtures/consultant.json'

const synthesis = fixture as unknown as Synthesis

describe('consultant synthesis', () => {
  it('renders the patient-specific summary, ranked problems and derived measures', () => {
    render(<ConsultantSynthesis synthesis={synthesis} />)
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('58-year-old man with hypertension and diabetes')
    const problems = screen.getAllByRole('listitem').filter(item => item.classList.contains('cs-problem'))
    expect(problems[0]).toHaveTextContent('Hypertension')
    expect(within(problems[0]).getByText('Uncontrolled')).toBeInTheDocument()
    expect(screen.getByText('G3aA2')).toBeInTheDocument()
    expect(within(problems[0]).getByText(/Add an ACE inhibitor or ARB as the second class/)).toBeInTheDocument()
  })

  it('links every plan citation to a registered guideline', () => {
    render(<ConsultantSynthesis synthesis={synthesis} />)
    const links = screen.getAllByRole('link').filter(link => link.closest('.cs-sources'))
    expect(links.length).toBeGreaterThan(5)
    for (const link of links) expect(link.getAttribute('href')).toMatch(/^https:\/\//)
  })

  it('copies the plain-text summary for notes and referral letters', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    render(<ConsultantSynthesis synthesis={synthesis} />)
    await userEvent.click(screen.getByRole('button', { name: /copy summary/i }))
    expect(writeText).toHaveBeenCalledWith(synthesis.summary_text)
    expect(await screen.findByText(/Summary copied/)).toBeInTheDocument()
  })
})
