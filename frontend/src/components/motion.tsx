import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import { haptic } from '@/lib/feedback'
import { SPRING, Spring, VelocityTracker, prefersReducedMotion, project, rubberband } from '@/lib/spring'

// A tab underline that springs from the current tab toward the chosen one, so the motion points at the outcome.
export function TabIndicator({ list, active }: { list: RefObject<HTMLElement | null>; active: string }) {
  const bar = useRef<HTMLSpanElement>(null)
  const springs = useRef<{ x: Spring; w: Spring } | null>(null)
  useLayoutEffect(() => {
    const el = bar.current, tabs = list.current
    if (!el || !tabs) return
    if (!springs.current) {
      const apply = () => { el.style.transform = `translateX(${springs.current!.x.value}px)`; el.style.width = `${springs.current!.w.value}px` }
      springs.current = { x: new Spring(0, apply), w: new Spring(0, apply) }
    }
    const place = (animate: boolean) => {
      const target = tabs.querySelector<HTMLElement>('[aria-selected="true"]')
      if (!target) return
      const { x, w } = springs.current!
      if (animate && w.value > 0) { x.to(target.offsetLeft); w.to(target.offsetWidth) }
      else { x.set(target.offsetLeft); w.set(target.offsetWidth) }
    }
    place(true)
    const onResize = () => place(false)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [active, list])
  return <span ref={bar} className="tab-indicator" aria-hidden/>
}

const HYSTERESIS = 10
// The mobile navigation drawer tracks the finger 1:1, rubber-bands past its open edge, and on release
// projects the flick to decide open or closed, then springs there carrying the finger's velocity.
export function useDrawerGesture(drawer: RefObject<HTMLElement | null>, scrim: RefObject<HTMLElement | null>, open: boolean, setOpen: (open: boolean) => void, ready: boolean) {
  const spring = useRef<Spring | null>(null)
  const isMobile = () => !!window.matchMedia?.('(max-width: 760px)').matches && !prefersReducedMotion()

  useEffect(() => {
    const el = drawer.current
    if (!el || !ready) return
    const width = () => el.offsetWidth
    const apply = (x: number) => {
      el.style.transform = `translateX(${x}px)`
      if (scrim.current) scrim.current.style.opacity = String(Math.max(0, Math.min(1, 1 + x / width())))
    }
    spring.current ??= new Spring(-width(), apply)
    let start: { x: number; y: number; value: number; id: number } | null = null
    let dragging = false
    const tracker = new VelocityTracker()
    const down = (e: PointerEvent) => {
      if (!isMobile() || !el.classList.contains('is-open')) return
      spring.current!.stop()
      start = { x: e.clientX, y: e.clientY, value: spring.current!.value, id: e.pointerId }
      dragging = false
      tracker.reset()
    }
    const move = (e: PointerEvent) => {
      if (!start || e.pointerId !== start.id) return
      const dx = e.clientX - start.x, dy = e.clientY - start.y
      if (!dragging) {
        if (Math.abs(dx) < HYSTERESIS) return
        if (Math.abs(dy) > Math.abs(dx)) { start = null; return }  // a vertical scroll, not ours
        dragging = true
        el.setPointerCapture(e.pointerId)
        el.classList.add('is-dragging')
      }
      let x = start.value + dx
      if (x > 0) x = rubberband(x, width())
      tracker.add(e.clientX)
      spring.current!.set(x)
    }
    const up = () => {
      if (!start) return
      start = null
      if (!dragging) return
      dragging = false
      el.classList.remove('is-dragging')
      // A drag that ends over a link must not also follow the link.
      el.addEventListener('click', swallow, { capture: true, once: true })
      const velocity = tracker.velocity()
      const resting = spring.current!.value + project(velocity)
      const stayOpen = resting > -width() / 2
      haptic('snap')
      // The scrim stays until the drawer has finished leaving.
      spring.current!.to(stayOpen ? 0 : -width(), SPRING.momentum, velocity).then(() => { if (!stayOpen) setOpen(false) })
    }
    const swallow = (e: Event) => { e.preventDefault(); e.stopPropagation() }
    const noNativeDrag = (e: Event) => e.preventDefault()  // links would otherwise start the browser's own drag and cancel ours
    const resize = () => { if (!isMobile()) { el.style.transform = ''; if (scrim.current) scrim.current.style.opacity = '' } }
    window.addEventListener('resize', resize)
    el.addEventListener('dragstart', noNativeDrag)
    el.addEventListener('pointerdown', down)
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', up)
    return () => {
      window.removeEventListener('resize', resize)
      el.removeEventListener('dragstart', noNativeDrag)
      el.removeEventListener('pointerdown', down)
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', up)
      el.removeEventListener('pointercancel', up)
    }
  }, [drawer, scrim, ready, setOpen])

  // Opening or closing by button: no momentum, so no bounce.
  useEffect(() => {
    const el = drawer.current
    if (!el || !spring.current) return
    if (!isMobile()) { el.style.transform = ''; if (scrim.current) scrim.current.style.opacity = ''; return }
    spring.current.to(open ? 0 : -el.offsetWidth, SPRING.default)
  }, [open, drawer, scrim])
}
