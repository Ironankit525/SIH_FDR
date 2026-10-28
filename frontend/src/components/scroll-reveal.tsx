import { useEffect, useRef, useState, type ReactNode, type CSSProperties } from 'react'

export interface UseInViewOptions {
  threshold?: number | number[]
  rootMargin?: string
  once?: boolean
  fallbackInView?: boolean
}

/**
 * Hook that tracks when an element enters the viewport via IntersectionObserver.
 * Defaults to triggering once and gracefully falls back to true if IntersectionObserver
 * is not available (such as in SSR or jsdom test runners).
 */
export function useInView<T extends HTMLElement = HTMLDivElement>(
  options: UseInViewOptions = {}
) {
  const {
    threshold = 0.15,
    rootMargin = '0px 0px -40px 0px',
    once = true,
    fallbackInView = true,
  } = options

  const [inView, setInView] = useState(() => {
    if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
      return fallbackInView
    }
    return false
  })

  const ref = useRef<T | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
      setInView(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          if (once) {
            observer.unobserve(el)
          }
        } else if (!once) {
          setInView(false)
        }
      },
      { threshold, rootMargin }
    )

    observer.observe(el)
    return () => {
      observer.disconnect()
    }
  }, [threshold, rootMargin, once])

  return { ref, inView }
}

export interface ScrollRevealProps extends UseInViewOptions {
  children: ReactNode | ((inView: boolean) => ReactNode)
  className?: string
  style?: CSSProperties
  delay?: number
}

/**
 * Container component that animates its children into view when scrolled to,
 * and passes the `inView` state to dynamic children (e.g. charts).
 */
export function ScrollReveal({
  children,
  className = '',
  style,
  delay = 0,
  threshold = 0.15,
  rootMargin = '0px 0px -30px 0px',
  once = true,
}: ScrollRevealProps) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold, rootMargin, once })

  return (
    <div
      ref={ref}
      className={`chart-scroll-reveal ${inView ? 'is-in-view' : ''} ${className}`}
      style={{
        ...style,
        ...(delay ? { transitionDelay: `${delay}ms` } : {}),
      }}
    >
      {typeof children === 'function' ? children(inView) : children}
    </div>
  )
}
