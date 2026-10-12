import manifest from './scenes.json'

export type VariantName = 'landscape' | 'portrait'

interface RawVariant {
  width: number
  height: number
  focus: [number, number]
  plates: { file: string; w: number }[]
  lights: { x: number; y: number; w: number; h: number; files: string[] }
}

export interface SceneVariant {
  name: VariantName
  width: number
  height: number
  /** Point of the plate (0–1) kept on screen when cropping to the viewport. */
  focus: [number, number]
  plates: { url: string; w: number }[]
  /** Light overlay crop, as fractions of the plate. */
  lights: { left: number; top: number; width: number; height: number; urls: string[] }
}

const files = import.meta.glob('../assets/scene/*.{webp,jpg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>

function url(file: string): string {
  const u = files[`../assets/scene/${file}`]
  if (!u) throw new Error(`Missing scene asset ${file}`)
  return u
}

function build(name: VariantName, v: RawVariant): SceneVariant {
  return {
    name,
    width: v.width,
    height: v.height,
    focus: v.focus,
    plates: v.plates.map((p) => ({ url: url(p.file), w: p.w })).sort((a, b) => a.w - b.w),
    lights: {
      left: v.lights.x / v.width,
      top: v.lights.y / v.height,
      width: v.lights.w / v.width,
      height: v.lights.h / v.height,
      urls: v.lights.files.map(url),
    },
  }
}

const raw = manifest as Record<VariantName, RawVariant>

export const VARIANTS: Record<VariantName, SceneVariant> = {
  landscape: build('landscape', raw.landscape),
  portrait: build('portrait', raw.portrait),
}

/** Below this width/height ratio the portrait camera is used. */
export const PORTRAIT_BELOW_ASPECT = 0.82

export function pickVariant(w: number, h: number): VariantName {
  return w / h < PORTRAIT_BELOW_ASPECT ? 'portrait' : 'landscape'
}

/** Smallest plate that still covers the viewport at device resolution. */
export function pickPlate(v: SceneVariant, viewportW: number, viewportH: number, dpr: number): string {
  const scale = Math.max(viewportW / v.width, viewportH / v.height)
  const needed = v.width * scale * Math.min(dpr, 2)
  const hit = v.plates.find((p) => p.w >= needed * 0.9)
  return (hit ?? v.plates[v.plates.length - 1]).url
}
