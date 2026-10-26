// Springs described the way Apple's tools describe them: damping ratio (1 = no overshoot) and
// response (seconds to reach the target), not mass/stiffness. A spring keeps its value and velocity,
// so a new target continues from where it is on screen, at the speed it is moving: interruptible.

export const SPRING = {
  default: { damping: 1, response: 0.35 },   // most UI: settles without overshoot
  momentum: { damping: 0.8, response: 0.3 }, // only after a flick or drag release (drawers, sheets)
}

export const prefersReducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export class Spring {
  value: number
  velocity = 0
  private target: number
  private frame = 0
  private last = 0
  private resolve?: () => void

  constructor(value: number, private onUpdate: (value: number) => void) {
    this.value = value
    this.target = value
  }

  set(value: number) {
    this.stop()
    this.value = this.target = value
    this.velocity = 0
    this.onUpdate(value)
  }

  // velocity in units per second, e.g. the pointer's speed at release.
  to(target: number, { damping, response }: { damping: number; response: number } = SPRING.default, velocity?: number): Promise<void> {
    this.target = target
    if (velocity !== undefined) this.velocity = velocity
    if (prefersReducedMotion()) { this.set(target); return Promise.resolve() }
    const stiffness = (2 * Math.PI / response) ** 2
    const friction = (4 * Math.PI * damping) / response
    cancelAnimationFrame(this.frame)
    this.resolve?.()
    this.last = performance.now()
    return new Promise(resolve => {
      this.resolve = resolve
      const step = (now: number) => {
        // Fixed sub-steps keep the integration stable on slow frames.
        let dt = Math.min((now - this.last) / 1000, 0.064)
        this.last = now
        while (dt > 0) {
          const h = Math.min(dt, 1 / 240)
          const force = -stiffness * (this.value - this.target) - friction * this.velocity
          this.velocity += force * h
          this.value += this.velocity * h
          dt -= h
        }
        if (Math.abs(this.velocity) < 0.5 && Math.abs(this.value - this.target) < 0.5) {
          this.value = this.target; this.velocity = 0; this.onUpdate(this.value); this.resolve = undefined; resolve(); return
        }
        this.onUpdate(this.value)
        this.frame = requestAnimationFrame(step)
      }
      this.frame = requestAnimationFrame(step)
    })
  }

  stop() {
    cancelAnimationFrame(this.frame)
    this.resolve?.()
    this.resolve = undefined
  }
}

// Where a flick would come to rest, as scrolling decelerates (Apple's projection, not v²/2a).
export function project(velocity: number, deceleration = 0.998) {
  return (velocity / 1000) * deceleration / (1 - deceleration)
}

// Past an edge the element follows less and less: soft resistance instead of a hard stop.
export function rubberband(overshoot: number, dimension: number, constant = 0.55) {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot))
}

// Recent pointer positions, for the velocity at release.
export class VelocityTracker {
  private samples: { t: number; v: number }[] = []
  add(value: number) {
    const t = performance.now()
    this.samples.push({ t, v: value })
    this.samples = this.samples.filter(s => t - s.t < 100)
  }
  velocity() {
    const first = this.samples[0], last = this.samples[this.samples.length - 1]
    if (!first || !last || last.t === first.t) return 0
    return ((last.v - first.v) / (last.t - first.t)) * 1000
  }
  reset() { this.samples = [] }
}
