import manifest from './scenes.json'

export type VariantName = 'landscape' | 'portrait'

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

interface RawVariant {
  width: number
  height: number
  focus: [number, number]
  camera: Record<string, unknown>
  background: { file: string; w: number }[]
  foreground: { file: string; w: number }[]
  gantry: Rect & { file: string }
  lights: Rect & { files: string[] }
}

/** A layer rectangle as fractions of the full frame. */
export interface Box {
  left: number
  top: number
  width: number
  height: number
}

export interface Sized {
  url: string
  w: number
}

export interface SceneVariant {
  name: VariantName
  width: number
  height: number
  /** Point of the frame (0–1) kept on screen when cropping to the viewport. */
  focus: [number, number]
  /** Back to front: background → gantry → light glow (screen blend) → cockpit foreground. */
  background: Sized[]
  /** True when a photo from src/assets/scene/override/ replaces the rendered background. */
  backgroundIsOverride: boolean
  foreground: Sized[]
  gantry: Box & { url: string }
  lights: Box & { urls: string[] }
}

const files = import.meta.glob('../assets/scene/*.{webp,jpg,png}', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>

/**
 * Optional background plates, e.g. a licensed photograph:
 *   src/assets/scene/override/landscape-background.jpg   (any of .webp .jpg .jpeg .png .avif)
 *   src/assets/scene/override/portrait-background.jpg
 * Same aspect ratio as the rendered frame; see README "Replacing the background".
 */
const overrides = import.meta.glob('../assets/scene/override/*-background.{webp,jpg,jpeg,png,avif}', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>

function url(file: string): string {
  const u = files[`../assets/scene/${file}`]
  if (!u) throw new Error(`Missing scene asset ${file}`)
  return u
}

function overrideFor(name: VariantName): string | null {
  const hit = Object.keys(overrides).find((k) => k.split('/').pop()!.startsWith(`${name}-background.`))
  return hit ? overrides[hit] : null
}

function box(v: RawVariant, r: Rect): Box {
  return { left: r.x / v.width, top: r.y / v.height, width: r.w / v.width, height: r.h / v.height }
}

function sized(list: { file: string; w: number }[]): Sized[] {
  return list.map((p) => ({ url: url(p.file), w: p.w })).sort((a, b) => a.w - b.w)
}

function build(name: VariantName, v: RawVariant): SceneVariant {
  const override = overrideFor(name)
  return {
    name,
    width: v.width,
    height: v.height,
    focus: v.focus,
    background: override ? [{ url: override, w: v.width }] : sized(v.background),
    backgroundIsOverride: override !== null,
    foreground: sized(v.foreground),
    gantry: { ...box(v, v.gantry), url: url(v.gantry.file) },
    lights: { ...box(v, v.lights), urls: v.lights.files.map(url) },
  }
}

const raw = manifest as unknown as Record<VariantName, RawVariant>

export const VARIANTS: Record<VariantName, SceneVariant> = {
  landscape: build('landscape', raw.landscape),
  portrait: build('portrait', raw.portrait),
}

/** Below this width/height ratio the portrait camera is used. */
export const PORTRAIT_BELOW_ASPECT = 0.82

export function pickVariant(w: number, h: number): VariantName {
  return w / h < PORTRAIT_BELOW_ASPECT ? 'portrait' : 'landscape'
}

/** Smallest image that still covers the viewport at device resolution. */
export function pickSize(v: SceneVariant, list: Sized[], viewportW: number, viewportH: number, dpr: number): string {
  const scale = Math.max(viewportW / v.width, viewportH / v.height)
  const needed = v.width * scale * Math.min(dpr, 2)
  const hit = list.find((p) => p.w >= needed * 0.9)
  return (hit ?? list[list.length - 1]).url
}
