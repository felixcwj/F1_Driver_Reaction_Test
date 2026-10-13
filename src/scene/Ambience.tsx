import { memo, useEffect, useRef } from 'react'
import type { SceneFx } from './assets'

/**
 * Subtle signs of life on the still photo. Every effect only changes opacity of small layers
 * fixed in place over the background — the camera, cockpit, halo, wheel and gantry never move
 * and nothing is ever drawn over them.
 *
 *  - shimmer   floodlights / building / city lights breathe by a few percent, each on its own
 *              irregular cycle (2.3–6.9 s), so the whole never repeats visibly
 *  - leds      rear rain lights of the cars ahead vary by ~5–10 % (1.1–1.9 s cycles)
 *  - haze      three sub-pixel heat-shimmer copies of the far straight cross-fade (3–6 s)
 *  - flashes   a rare, tiny camera flash in the stands or pit building: one every 4–11 s,
 *              160 ms long, and only while no start sequence is running
 *
 * Everything is off with prefers-reduced-motion.
 */

/** Deterministic pseudo-random in [0, 1) per index, so layouts are stable between renders. */
function hash(i: number, salt: number): number {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

const pct = (v: number) => `${v * 100}%`

export const Ambience = memo(function Ambience({ fx, flashes }: { fx: SceneFx; flashes: boolean }) {
  const flashRef = useRef<HTMLDivElement>(null)
  const flashesRef = useRef(flashes)
  useEffect(() => {
    flashesRef.current = flashes
  }, [flashes])

  // Camera flashes: scheduled with timers, played with the Web Animations API on one element.
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let timer = 0
    const schedule = () => {
      timer = window.setTimeout(fire, 4000 + Math.random() * 7000)
    }
    const fire = () => {
      const el = flashRef.current
      if (el && flashesRef.current && document.visibilityState === 'visible' && fx.flashZones.length) {
        const z = fx.flashZones[Math.floor(Math.random() * fx.flashZones.length)]
        el.style.left = pct(z.left + Math.random() * z.width)
        el.style.top = pct(z.top + Math.random() * z.height)
        const pulse = (delay: number, peak: number) =>
          el.animate(
            [{ opacity: 0 }, { opacity: peak, offset: 0.1 }, { opacity: 0 }],
            { duration: 160, delay, easing: 'ease-out' },
          )
        // some cameras fire a weaker pre-flash first
        if (Math.random() < 0.25) pulse(0, 0.45)
        pulse(Math.random() < 0.25 ? 110 : 0, 0.9)
      }
      schedule()
    }
    schedule()
    return () => window.clearTimeout(timer)
  }, [fx])

  return (
    <div className="ambience pointer-events-none absolute inset-0" aria-hidden="true">
      {fx.haze.urls.map((src, i) => (
        <img
          key={src}
          src={src}
          alt=""
          draggable={false}
          className="fx-haze absolute select-none"
          style={{
            left: pct(fx.haze.left),
            top: pct(fx.haze.top),
            width: pct(fx.haze.width),
            height: pct(fx.haze.height),
            animationDuration: `${3.1 + i * 1.4}s`,
            animationDelay: `${-hash(i, 1) * 6}s`,
          }}
        />
      ))}
      {fx.shimmer.map((p, i) => (
        <span
          key={`s${i}`}
          className="fx-glow fx-shimmer"
          style={{
            left: pct(p.x - p.r),
            top: pct(p.y),
            // percentage margins resolve against the plate width, like `r`
            marginTop: pct(-p.r),
            width: pct(p.r * 2),
            animationDuration: `${2.3 + hash(i, 2) * 4.6}s`,
            animationDelay: `${-hash(i, 3) * 7}s`,
          }}
        />
      ))}
      {fx.leds.map((p, i) => (
        <span
          key={`l${i}`}
          className="fx-glow fx-led"
          style={{
            left: pct(p.x - p.r),
            top: pct(p.y),
            marginTop: pct(-p.r),
            width: pct(p.r * 2),
            animationDuration: `${1.1 + hash(i, 4) * 0.8}s`,
            animationDelay: `${-hash(i, 5) * 2}s`,
          }}
        />
      ))}
      <div ref={flashRef} className="fx-flash" />
    </div>
  )
})
