import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Eye, RefreshCw, X } from 'lucide-react'
import { api, type Row } from '@/lib/api'
import { dateLabel } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Empty, ErrorState, Loading, Panel } from './common'

// The original receipt beside the extracted fields, so a reviewer reads one against the other without a dialog in between.
// Each view asks the server for a short-lived link tied to the signed-in account, so it is only requested on demand.
export function ReceiptPreview({ deposit }: { deposit: Row }) {
  const receipt = [...deposit.documents].reverse().find((doc: Row) => doc.category === 'instrument' && doc.instrument_id === deposit.instrument.id)
  const [open, setOpen] = useState(false)
  const access = useQuery<Row>({ queryKey: ['receipt-access', receipt?.id], queryFn: () => api(`/documents/${receipt!.id}/access`), enabled: open && !!receipt, staleTime: 90_000, gcTime: 0 })
  const actions = receipt && (open
    ? <><Button variant="ghost" size="sm" aria-label="Refresh receipt link" disabled={access.isFetching} onClick={() => access.refetch()}><RefreshCw size={14}/>Refresh link</Button><Button variant="ghost" size="sm" onClick={() => setOpen(false)}><X size={14}/>Hide</Button></>
    : <Button size="sm" variant="outline" onClick={() => setOpen(true)}><Eye size={14}/>Show original receipt</Button>)
  return <Panel title="Original receipt" subtitle={receipt ? `${receipt.filename} · uploaded ${dateLabel(receipt.created_at)}` : undefined} actions={actions} className="receipt-preview">
    {!receipt ? <Empty title="No receipt uploaded" message="The original appears here once the institution uploads it."/>
      : !open ? <div className="padded"><p className="cell-subtitle">The preview link expires after two minutes and is tied to your account.</p></div>
      : access.isPending ? <Loading/>
      : access.error ? <ErrorState error={access.error} retry={() => access.refetch()}/>
      : receipt.content_type === 'application/pdf'
        ? <iframe title="Original receipt" className="document-viewer" src={access.data!.url}/>
        : <img className="document-image" alt={receipt.filename} src={access.data!.url}/>}
  </Panel>
}
