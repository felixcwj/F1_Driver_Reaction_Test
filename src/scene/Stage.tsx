import { forwardRef, useImperativeHandle, useLayoutEffect, useRef } from 'react'
import type { LoadedScene } from './useScene'
import { Ambience } from './Ambience'

export interface StageHandle {
  /** Show `count` lit start-light columns (0–5). Direct DOM write, no React render. */
  setLights: (count: number) => void
}

/**
 * The onboard camera plate plus the start-light states, composited from the same render.
 * Each light overlay is the exact crop of the gantry with k columns lit, so switching is a
 * single opacity flip on a pre-decoded image.
 */
export const Stage = forwardRef<StageHandle, { scene: LoadedScene; flashes: boolean }>(function Stage({ scene, flashes }, ref) {
  const { variant, plateUrl } = scene
  const rootRef = useRef<HTMLDivElement>(null)
  const plateRef = useRef<HTMLDivElement>(null)
  const lightRefs = useRef<(HTMLImageElement | null)[]>([])
  const litRef = useRef(0)

  useImperativeHandle(
    ref,
    () => ({
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
  return (
    <div ref={rootRef} className="absolute inset-0 overflow-hidden bg-black" aria-hidden="true">
      <div ref={plateRef} className="absolute">
        {/* The camera is completely still: no transform or animation on the scene, ever. */}
        <div className="absolute inset-0">
          <img
            src={plateUrl}
            alt=""
            draggable={false}
            className="absolute inset-0 h-full w-full select-none"
            decoding="sync"
          />
          {variant.fx && <Ambience fx={variant.fx} flashes={flashes} />}
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
              className="start-light absolute select-none"
              style={{
                left: `${L.left * 100}%`,
                top: `${L.top * 100}%`,
                width: `${L.width * 100}%`,
                height: `${L.height * 100}%`,
                opacity: 0,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  )
})
