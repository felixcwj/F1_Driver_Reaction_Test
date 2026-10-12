import { useEffect, useState } from 'react'
import { VARIANTS, pickPlate, pickVariant, type SceneVariant, type VariantName } from './assets'

function viewport() {
  const vv = window.visualViewport
  return { w: vv?.width ?? window.innerWidth, h: vv?.height ?? window.innerHeight }
}

/** Landscape or portrait camera, switching only when the viewport crosses the threshold. */
export function useVariantName(): VariantName {
  const [name, setName] = useState<VariantName>(() => {
    const { w, h } = viewport()
    return pickVariant(w, h)
  })
  useEffect(() => {
    const update = () => {
      const { w, h } = viewport()
      setName(pickVariant(w, h))
    }
    window.addEventListener('resize', update)
    window.visualViewport?.addEventListener('resize', update)
    return () => {
      window.removeEventListener('resize', update)
      window.visualViewport?.removeEventListener('resize', update)
    }
  }, [])
  return name
}

export interface LoadedScene {
  variant: SceneVariant
  plateUrl: string
}

const decoded = new Map<string, Promise<void>>()

function decode(src: string): Promise<void> {
  let p = decoded.get(src)
  if (!p) {
    const img = new Image()
    img.decoding = 'async'
    img.src = src
    p = img.decode().catch(
      () =>
        new Promise<void>((resolve, reject) => {
          if (img.complete && img.naturalWidth > 0) resolve()
          else {
            img.onload = () => resolve()
            img.onerror = () => reject(new Error(`Failed to load ${src}`))
          }
        }),
    )
    decoded.set(src, p)
  }
  return p
}

/**
 * Preloads and decodes every image the start sequence needs (plate + five light states)
 * before the scene is reported as ready, so no light can ever wait on the network or decoder.
 */
export function useSceneLoader(name: VariantName) {
  const [state, setState] = useState<{ scene: LoadedScene | null; progress: number; error: string | null }>({
    scene: null,
    progress: 0,
    error: null,
  })

  useEffect(() => {
    let cancelled = false
    const variant = VARIANTS[name]
    const { w, h } = viewport()
    const plateUrl = pickPlate(variant, w, h, window.devicePixelRatio || 1)
    const all = [plateUrl, ...variant.lights.urls]
    let done = 0
    Promise.all(
      all.map((src) =>
        decode(src).then(() => {
          done += 1
          if (!cancelled) setState((s) => ({ ...s, progress: done / all.length }))
        }),
      ),
    )
      .then(() => {
        if (!cancelled) setState({ scene: { variant, plateUrl }, progress: 1, error: null })
      })
      .catch((e: unknown) => {
        if (!cancelled) setState((s) => ({ ...s, error: e instanceof Error ? e.message : String(e) }))
      })
    return () => {
      cancelled = true
    }
  }, [name])

  return state
}
