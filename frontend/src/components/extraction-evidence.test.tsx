import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExtractionEvidence, ExtractionStatus } from './extraction-evidence'
import { CaseProgress } from './case-progress'

const evidence = {
  status: 'conflict', reasons: [],
  conflicts: [{ field: 'amount', observations: [{ source: 'ocr', value: 10000 }, { source: 'vlm_http', value: '100000.00' }] }],
  stages: [{ stage: 'ocr', outcome: 'insufficient', reasons: ['missing bank'] }, { stage: 'vlm_http', outcome: 'accepted' }],
  sources: [{ provider: 'ocr', fields: { amount: 10000 }, original_text: 'Deposit Amount: INR|10000.00' },
    { provider: 'vlm_http', fields: { amount: '100000.00' }, original_text: '' }],
}

describe('cascade evidence', () => {
  it('shows both conflicting values and preserves the original OCR text', () => {
    render(<ExtractionEvidence evidence={evidence}/> )
    expect(screen.getByText('OCR: 10000')).toBeInTheDocument()
    expect(screen.getByText('VLM: 100000.00')).toBeInTheDocument()
    expect(screen.getByText(/Extraction sources disagree/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Extraction stages and original source values'))
    expect(screen.getByText(/OCR: Insufficient/)).toBeVisible()
    fireEvent.click(screen.getByText('Original text from OCR'))
    expect(screen.getByText('Deposit Amount: INR|10000.00')).toBeVisible()
  })

  it('does not label an incomplete result Completed', () => {
    render(<ExtractionStatus doc={{ category: 'instrument', processing_status: 'completed', extraction: { evidence: { status: 'incomplete' } } }}/> )
    expect(screen.getByText('Incomplete extraction')).toBeInTheDocument()
    expect(screen.queryByText('Completed')).not.toBeInTheDocument()
  })

  it('does not change queued status based on an old extraction result', () => {
    render(<ExtractionStatus doc={{ category: 'instrument', processing_status: 'queued', extraction: { evidence } }}/> )
    expect(screen.getByText('Queued')).toBeInTheDocument()
  })

  it('does not show extraction complete when the latest receipt needs review', () => {
    render(<CaseProgress role="institution" deposit={{ instrument: { id: 'inst' }, submitted_at: '2026-01-01', discrepancies: [],
      documents: [
        { instrument_id: 'inst', category: 'instrument', processing_status: 'completed', extraction: { evidence: { status: 'complete' } } },
        { instrument_id: 'inst', category: 'instrument', processing_status: 'completed', extraction: { evidence } },
      ],
    }}/> )
    expect(within(screen.getByText('Extraction').closest('li')!).getByText('Pending')).toBeInTheDocument()
  })
})
