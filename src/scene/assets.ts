import manifest from './scenes.json'

export type VariantName = 'landscape' | 'portrait'

interface RawPoint {
  x: number
  y: number
  r: number
}

interface RawRect {
  x: number
  y: number
  w: number
  h: number
}

interface RawVariant {
  width: number
  height: number
  focus: [number, number]
  plates: { file: string; w: number }[]
  lights: RawRect & { files: string[] }
  fx?: {
    haze: RawRect & { files: string[] }
    shimmer: RawPoint[]
    leds: RawPoint[]
    flashZones: RawRect[]
  }
}

/** Point in plate fractions; `r` is a fraction of the plate width. */
export interface FxPoint {
  x: number
  y: number
  r: number
}

export interface FxRect {
  left: number
  top: number
  width: number
  height: number
}

/** Ambient light effects on the background. Opacity-only: nothing in the scene moves. */
export interface SceneFx {
  haze: FxRect & { urls: string[] }
  shimmer: FxPoint[]
  leds: FxPoint[]
  flashZones: FxRect[]
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
  fx: SceneFx | null
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

function buildFx(v: RawVariant): SceneFx | null {
  if (!v.fx) return null
  const rect = (r: RawRect): FxRect => ({
    left: r.x / v.width,
    top: r.y / v.height,
    width: r.w / v.width,
    height: r.h / v.height,
  })
  const point = (p: RawPoint): FxPoint => ({ x: p.x / v.width, y: p.y / v.height, r: p.r / v.width })
  return {
    haze: { ...rect(v.fx.haze), urls: v.fx.haze.files.map(url) },
    shimmer: v.fx.shimmer.map(point),
    leds: v.fx.leds.map(point),
    flashZones: v.fx.flashZones.map(rect),
  }
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
    fx: buildFx(v),
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
