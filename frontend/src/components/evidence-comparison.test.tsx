import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { EvidenceComparison } from './evidence-comparison'
import { CaseProgress } from './case-progress'

function fixture() {
  return {
    instrument: { id: 'instrument', bank: 'Submitted Bank', number: 'ABC', amount: '100.00', verification_status: 'mock_confirmed' },
    documents: [{ id: 'doc', instrument_id: 'instrument', category: 'instrument', filename: 'receipt.pdf', processing_status: 'completed',
      extraction: { id: 'extraction', provider: 'ocr', method: 'pdf_text', fields: { bank: 'Parser Bank', amount: '100.00' }, confidences: { bank: 0.9, amount: 0 } },
      corrections: [{ id: 'correction', field: 'bank', corrected_value: 'Reviewed Bank', reason: 'Read original receipt' }] }],
    verifications: [{ instrument_id: 'instrument', evidence: { simulated: true, finding: 'confirmed', confirmed_fields: { bank: 'Submitted Bank', amount: '100.00' } } }],
    requirement_snapshot: { illustrative: true }, required_amount: 100, discrepancies: [], submitted_at: '2026-01-01',
    mock_verification_permitted: false,
  }
}

describe('independent evidence display', () => {
  it('preserves the raw value and distinguishes human corrections from parser confidence', () => {
    render(<EvidenceComparison deposit={fixture()} canCorrect onCorrect={vi.fn()}/> )
    const bank = screen.getByRole('row', { name: /Bank Submitted Bank Reviewed Bank/ })
    expect(within(bank).getByText('Original extraction: Parser Bank')).toBeInTheDocument()
    expect(within(bank).queryByText(/90%/)).not.toBeInTheDocument()
    expect(screen.getByText('0% parser confidence')).toBeInTheDocument()
    expect(screen.getByText('SIMULATED bank evidence')).toBeInTheDocument()
    expect(within(bank).getByText('Values differ')).toBeInTheDocument()
  })

  it('does not show an older extraction as the result of a newer failed receipt', () => {
    const deposit: any = fixture()
    deposit.documents.push({ id: 'new', instrument_id: 'instrument', category: 'instrument', filename: 'new.pdf', processing_status: 'failed' })
    render(<EvidenceComparison deposit={deposit} canCorrect={false} onCorrect={vi.fn()}/> )
    expect(screen.getByText(/latest receipt has no extraction result/)).toBeInTheDocument()
    expect(screen.queryByText('Reviewed Bank')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Record correction' })).not.toBeInTheDocument()
  })

  it('marks Verified only after the officer signs it off, not on a bank finding alone', () => {
    const { unmount } = render(<CaseProgress deposit={fixture()} role="authority"/> )
    expect(within(screen.getByText('Verified').closest('li')!).getByText('Pending')).toBeInTheDocument()
    unmount()
    render(<CaseProgress deposit={{ ...fixture(), verified_at: '2026-01-02' }} role="authority"/> )
    expect(within(screen.getByText('Verified').closest('li')!).getByText('Complete')).toBeInTheDocument()
  })
})
