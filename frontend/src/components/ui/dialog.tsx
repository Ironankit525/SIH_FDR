import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import { haptic } from '@/lib/feedback'
import { SPRING, Spring, VelocityTracker, prefersReducedMotion, project, rubberband } from '@/lib/spring'

// On phones a dialog is a bottom sheet: it rises from the bottom edge, follows the finger when dragged down,
// and leaves the way it came. On larger screens it is a centred dialog that materialises over a dimmed page.
const SHEET = '(max-width: 600px)'
const useSheet = () => {
  const query = () => typeof window !== 'undefined' && !!window.matchMedia?.(SHEET).matches && !prefersReducedMotion()
  const [sheet, setSheet] = useState(query)
  useEffect(() => {
    const media = window.matchMedia?.(SHEET)
    if (!media) return
    const update = () => setSheet(query())
    media.addEventListener('change', update); return () => media.removeEventListener('change', update)
  }, [])
  return sheet
}

export function Dialog({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: ReactNode }) {
  const sheet = useSheet()
  const content = useRef<HTMLDivElement>(null)
  const overlay = useRef<HTMLDivElement>(null)
  const spring = useRef<Spring | null>(null)
  const drag = useRef<{ y: number; start: number; id: number; dragging: boolean } | null>(null)
  const tracker = useRef(new VelocityTracker())
  const [leaving, setLeaving] = useState(false)
  // Radix mounts the content a render after opening, so start the spring when the element actually exists.
  const [node, setNode] = useState<HTMLDivElement | null>(null)
  const attach = (el: HTMLDivElement | null) => { content.current = el; setNode(el) }

  const apply = (y: number) => {
    const el = content.current
    if (!el) return
    el.style.transform = `translateY(${y}px)`
    if (overlay.current) overlay.current.style.opacity = String(1 - Math.min(1, Math.max(0, y / el.offsetHeight)))
  }
  useLayoutEffect(() => {
    if (!open || !sheet || !node) return
    setLeaving(false)
    const height = node.offsetHeight
    spring.current = new Spring(height, apply)
    apply(height)
    spring.current.to(0, SPRING.default)
  }, [open, sheet, node])

  const dismiss = (velocity = 0, momentum = false) => {
    if (!sheet || !content.current || !spring.current) return onOpenChange(false)
    setLeaving(true)
    spring.current.to(content.current.offsetHeight, momentum ? SPRING.momentum : SPRING.default, velocity).then(() => onOpenChange(false))
  }
  const down = (e: PointerEvent) => {
    if (!sheet || !spring.current) return
    spring.current.stop()
    drag.current = { y: e.clientY, start: spring.current.value, id: e.pointerId, dragging: false }
    tracker.current.reset()
  }
  const move = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d || e.pointerId !== d.id || !spring.current || !content.current) return
    const dy = e.clientY - d.y
    if (!d.dragging) {
      if (Math.abs(dy) < 10) return
      d.dragging = true
      e.currentTarget.setPointerCapture(d.id)
    }
    let y = d.start + dy
    if (y < 0) y = rubberband(y, content.current.offsetHeight)  // resist being pulled above its resting place
    tracker.current.add(e.clientY)
    spring.current.set(y)
  }
  const up = () => {
    const d = drag.current
    drag.current = null
    if (!d?.dragging || !spring.current || !content.current) return
    const velocity = tracker.current.velocity()
    if (spring.current.value + project(velocity) > content.current.offsetHeight * 0.4) { haptic('snap'); dismiss(velocity, true) }
    else spring.current.to(0, SPRING.momentum, velocity)
  }

  return <DialogPrimitive.Root open={open} onOpenChange={next => next ? onOpenChange(true) : dismiss()}><DialogPrimitive.Portal>
    <DialogPrimitive.Overlay ref={overlay} className={`dialog-overlay${sheet ? ' sheet' : ''}${leaving ? ' leaving' : ''}`}/>
    <DialogPrimitive.Content ref={attach} className={`dialog-content${sheet ? ' sheet' : ''}${leaving ? ' leaving' : ''}`}>
      <div className="dialog-grab" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        {sheet && <span className="sheet-grabber" aria-hidden/>}
        <div className="dialog-heading"><DialogPrimitive.Title>{title}</DialogPrimitive.Title><DialogPrimitive.Close className="icon-button" aria-label="Close dialog"><X size={19}/></DialogPrimitive.Close></div>
      </div>
      <DialogPrimitive.Description className="muted">{description || 'Complete the fields below to record this action.'}</DialogPrimitive.Description>
      {children}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal></DialogPrimitive.Root>
}
