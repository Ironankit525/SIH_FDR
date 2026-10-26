import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { IntegrityChecks } from './integrity-checks'

const clean = {
  version: 2, signals: [], ocr_crosscheck: 'completed', compared_fields: ['number', 'amount'], text_fields: ['number', 'amount'],
  metadata: { producer: 'Core Banking eReceipt 4.2', creator: 'Branch Teller Terminal', creationDate: 'D:20260101103000', modDate: 'D:20260101103000' },
  structure: { pages: 1, saves: 1, linearised: false, text_layer: true },
}
const doc = (forensics: unknown, fields: Record<string, unknown> = { number: 'FDR-1', amount: 3500000 }) => ({
  id: 'doc-1', sha256: 'abc', category: 'instrument', content_type: 'application/pdf', processing_status: 'completed', forensics, extraction: { fields },
})
const row = (name: string) => screen.getByText(name).closest('li')!

describe('document integrity checks', () => {
  it('shows what passed and why, collapsed when nothing was found', () => {
    render(<IntegrityChecks doc={doc(clean)} tasks={[]}/>)
    expect(screen.getByText(/no findings/)).toBeInTheDocument()
    expect(screen.getByText(/no findings/).closest('details')).not.toHaveAttribute('open')
    expect(within(row('Saved again after creation')).getByText('Passed')).toBeInTheDocument()
    expect(within(row('Visible page matches hidden text')).getByText(/matched the hidden text for: number, amount/)).toBeInTheDocument()
    expect(within(row('Receipt arithmetic')).getByText('Not applicable')).toBeInTheDocument()
  })

  it('opens on findings and links document checks to their review tasks', () => {
    const edited = { ...clean, structure: { ...clean.structure, saves: 2 },
                     signals: [{ code: 'incremental_update', severity: 'warning', detail: 'The PDF was saved 1 more time(s) after creation.' }] }
    const tasks = [{ code: 'maturity_value_inconsistent:doc-1', status: 'open', severity: 'high', description: 'Maturity value does not fit.' }]
    render(<IntegrityChecks doc={doc(edited, { number: 'FDR-1', amount: 3500000, maturity_value: 1600000 })} tasks={tasks}/>)
    expect(screen.getByText(/2 findings/).closest('details')).toHaveAttribute('open')
    expect(within(row('Saved again after creation')).getByText('Finding')).toBeInTheDocument()
    expect(within(row('Receipt arithmetic')).getByText('Review task open · high severity')).toBeInTheDocument()
  })

  it('shows a declaration mismatch and the figures the arithmetic used', () => {
    const tasks = [{ code: 'mismatch_amount:doc-1', status: 'open', severity: 'high', description: 'Submitted amount (3500000) differs from document evidence (1500000).' }]
    render(<IntegrityChecks doc={doc(clean, { number: 'FDR-1', amount: 1500000, maturity_value: 1819500, rate: 7.1 })} tasks={tasks}/>)
    expect(within(row("Matches the institution's declaration")).getByText(/differs from document evidence/)).toBeInTheDocument()
    expect(within(row('Receipt arithmetic')).getByText(/principal ₹15,00,000, maturity value ₹18,19,500 at 7.1%/)).toBeInTheDocument()
  })

  it('renders nothing for institutions and explains older or pending documents', () => {
    const { container, rerender } = render(<IntegrityChecks doc={doc(undefined)} tasks={[]}/>)
    expect(container).toBeEmptyDOMElement()
    rerender(<IntegrityChecks doc={doc({})} tasks={[]}/>)
    expect(screen.getByText(/uploaded before these checks existed/)).toBeInTheDocument()
    rerender(<IntegrityChecks doc={{ ...doc(clean), processing_status: 'processing' }} tasks={[]}/>)
    expect(screen.getByText(/run once extraction finishes/)).toBeInTheDocument()
  })
})
