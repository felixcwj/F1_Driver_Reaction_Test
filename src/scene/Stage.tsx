import { forwardRef, useImperativeHandle, useLayoutEffect, useRef } from 'react'
import type { LoadedScene } from './useScene'

export interface StageHandle {
  /** Show `count` lit start-light columns (0–5). Direct DOM write, no React render. */
  setLights: (count: number) => void
  /** Peak camera vibration in CSS px; 0 stops it. Direct DOM write, no React render. */
  setVibration: (px: number) => void
}

/**
 * The onboard view, composited from layers of one render (same camera, lens and grade):
 * background, start-light gantry, light glow states and the cockpit in front. Each light state
 * is a pre-decoded image, so switching lights is a single opacity flip.
 */
export const Stage = forwardRef<StageHandle, { scene: LoadedScene }>(function Stage({ scene }, ref) {
  const { variant, backgroundUrl, foregroundUrl } = scene
  const rootRef = useRef<HTMLDivElement>(null)
  const plateRef = useRef<HTMLDivElement>(null)
  const lightRefs = useRef<(HTMLImageElement | null)[]>([])
  const litRef = useRef(0)
  const vibRef = useRef<HTMLDivElement>(null)

  useImperativeHandle(
    ref,
    () => ({
      setVibration(px: number) {
        const el = vibRef.current
        if (!el) return
        if (px > 0) {
          el.style.setProperty('--vib', `${px}px`)
          el.dataset.vib = 'on'
        } else {
          delete el.dataset.vib
        }
      },
      setLights(count: number) {
        litRef.current = count
        lightRefs.current.forEach((img, i) => {
          if (img) img.style.opacity = i + 1 === count ? '1' : '0'
        })
      },
    }),
    [],
  )

  // Re-apply the current light state when the variant (and thus the <img> set) changes.
  useLayoutEffect(() => {
    lightRefs.current.forEach((img, i) => {
      if (img) img.style.opacity = i + 1 === litRef.current ? '1' : '0'
    })
  }, [variant])

  // "cover" fit around the variant's focus point, written straight to style (no re-render).
  useLayoutEffect(() => {
    const root = rootRef.current
    const plate = plateRef.current
    if (!root || !plate) return
    const layout = () => {
      const W = root.clientWidth
      const H = root.clientHeight
      const s = Math.max(W / variant.width, H / variant.height)
      const w = variant.width * s
      const h = variant.height * s
      const [fx, fy] = variant.focus
      const left = Math.min(0, Math.max(W - w, W / 2 - fx * w))
      const top = Math.min(0, Math.max(H - h, H / 2 - fy * h))
      plate.style.width = `${w}px`
      plate.style.height = `${h}px`
      plate.style.left = `${left}px`
      plate.style.top = `${top}px`
    }
    layout()
    const ro = new ResizeObserver(layout)
    ro.observe(root)
    return () => ro.disconnect()
  }, [variant])

  const L = variant.lights
  const G = variant.gantry
  const rect = (b: { left: number; top: number; width: number; height: number }) => ({
    left: `${b.left * 100}%`,
    top: `${b.top * 100}%`,
    width: `${b.width * 100}%`,
    height: `${b.height * 100}%`,
  })
  return (
    <div ref={rootRef} className="absolute inset-0 overflow-hidden bg-black" aria-hidden="true">
      <div ref={plateRef} className="absolute">
        <div ref={vibRef} className="vibration absolute inset-0">
          {/* 1. circuit, city, car ahead — or a photo plate from src/assets/scene/override */}
          <img src={backgroundUrl} alt="" draggable={false} decoding="sync" className="layer inset-0 h-full w-full" />
          {/* 2. start-light gantry, lights dark */}
          <img src={G.url} alt="" draggable={false} decoding="sync" className="layer" style={rect(G)} />
          {/* 3. lit lamps + their glow, added on top with a screen blend */}
          {L.urls.map((src, i) => (
            <img
              key={src}
              ref={(el) => {
                lightRefs.current[i] = el
              }}
              src={src}
              alt=""
              draggable={false}
              decoding="sync"
              className="layer start-light"
              style={{ ...rect(L), opacity: 0 }}
            />
          ))}
          {/* 4. our cockpit: bodywork, halo, mirrors, steering wheel */}
          <img src={foregroundUrl} alt="" draggable={false} decoding="sync" className="layer inset-0 h-full w-full" />
        </div>
      </div>
    </div>
  )
})
