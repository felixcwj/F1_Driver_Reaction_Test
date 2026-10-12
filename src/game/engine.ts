/**
 * Start-sequence engine.
 *
 * Deliberately framework-free: the timing-critical work (switching the start lights and
 * stamping the moment they go out) happens inside requestAnimationFrame callbacks and writes
 * straight to the DOM through `setLights`. React is only notified on coarse UI transitions
 * (intro -> running -> result), never on the frame where the lights go out.
 *
 * Clock: everything uses the monotonic `performance.now()` timeline. rAF timestamps and
 * `Event.timeStamp` share that timeline in all current browsers.
 */

export type Phase =
  | 'INTRO'
  | 'ARMED'
  | 'COUNTDOWN'
  | 'WAITING_FOR_LIGHTS_OUT'
  | 'REACTION_WINDOW'
  | 'RESULT'
  | 'FALSE_START'

/** What the UI layer needs to know. Changes only a handful of times per attempt. */
export type UiPhase = 'INTRO' | 'RUNNING' | 'RESULT' | 'FALSE_START'

export interface Snapshot {
  ui: UiPhase
  /** Increments on every new attempt so stale results can never be shown. */
  attempt: number
  /** Rounded integer milliseconds, only set in RESULT. */
  reactionMs: number | null
  /** Set when an attempt was cancelled (tab hidden, frame stall, viewport swap). */
  aborted: boolean
}

export interface Timeline {
  sequenceStartTime: number
  /** Scheduled switch-on time of each light (absolute, drift-free). */
  lightSchedule: number[]
  /** Frame timestamps at which each light was actually committed. */
  lightCommitTimes: number[]
  fifthLightTime: number | null
  holdMs: number
  lightsOutDeadline: number | null
  /** rAF timestamp of the frame in which the lights were switched off in the DOM. */
  lightsOutCommitTime: number | null
  /** Timestamp of the following frame ≈ when the dark lights were first on screen. */
  lightsOutTime: number | null
  inputTime: number | null
  reactionRaw: number | null
}

export interface EngineDeps {
  setLights: (count: number) => void
  onChange: (s: Snapshot) => void
  raf?: (cb: FrameRequestCallback) => number
  caf?: (id: number) => void
  random?: () => number
}

export const LIGHT_INTERVAL_MS = 1000
export const ARM_DELAY_MIN_MS = 900
export const ARM_DELAY_MAX_MS = 1500
export const HOLD_MIN_MS = 200
export const HOLD_MAX_MS = 3000
/** Two presses closer than this are one physical input (bounce / duplicated event). */
export const DUPLICATE_WINDOW_MS = 40
/** Results can't be dismissed for this long, so a follow-up tap can't skip them. */
export const RESULT_LOCK_MS = 700
/** A frame arriving this late means the sequence was not displayed faithfully. */
export const STALL_ABORT_MS = 250

export const EASTER_EGG_THRESHOLD_MS = 100

export function isEasterEgg(reactionMs: number | null): boolean {
  return reactionMs !== null && reactionMs < EASTER_EGG_THRESHOLD_MS
}

/** Uniform random in [0, 1) from the CSPRNG when available. */
export function secureRandom(): number {
  const c = globalThis.crypto
  if (c?.getRandomValues) {
    const buf = new Uint32Array(1)
    c.getRandomValues(buf)
    return buf[0] / 2 ** 32
  }
  return Math.random()
}

export class StartEngine {
  private phase: Phase = 'INTRO'
  private ready = false
  private attempt = 0
  private reactionMs: number | null = null
  private aborted = false
  private litCount = 0
  private rafId: number | null = null
  private lastInputTime = -Infinity
  private resultShownAt = -Infinity
  private pendingInput: number | null = null
  private lastUi: UiPhase | null = null
  private tl: Timeline = StartEngine.emptyTimeline()

  private readonly raf: (cb: FrameRequestCallback) => number
  private readonly caf: (id: number) => void
  private readonly random: () => number

  private readonly deps: EngineDeps

  constructor(deps: EngineDeps) {
    this.deps = deps
    this.raf = deps.raf ?? ((cb) => requestAnimationFrame(cb))
    this.caf = deps.caf ?? ((id) => cancelAnimationFrame(id))
    this.random = deps.random ?? secureRandom
  }

  private static emptyTimeline(): Timeline {
    return {
      sequenceStartTime: 0,
      lightSchedule: [],
      lightCommitTimes: [],
      fifthLightTime: null,
      holdMs: 0,
      lightsOutDeadline: null,
      lightsOutCommitTime: null,
      lightsOutTime: null,
      inputTime: null,
      reactionRaw: null,
    }
  }

  get currentPhase(): Phase {
    return this.phase
  }

  get timeline(): Readonly<Timeline> {
    return this.tl
  }

  /** Inputs are ignored until the scene's graphics are decoded. */
  setReady(ready: boolean): void {
    if (this.ready === ready) return
    this.ready = ready
    if (!ready) this.abort()
  }

  snapshot(): Snapshot {
    return { ui: this.uiPhase(), attempt: this.attempt, reactionMs: this.reactionMs, aborted: this.aborted }
  }

  /**
   * One physical press (pointerdown / Space keydown). `t` is the event's own timestamp on the
   * performance.now() timeline, which is earlier and more accurate than handler time.
   */
  press(t: number): void {
    if (!this.ready) return
    if (t - this.lastInputTime < DUPLICATE_WINDOW_MS) return
    this.lastInputTime = t

    switch (this.phase) {
      case 'INTRO':
        this.start(t)
        return
      case 'ARMED':
      case 'COUNTDOWN':
      case 'WAITING_FOR_LIGHTS_OUT':
        this.falseStart(t)
        return
      case 'REACTION_WINDOW':
        if (this.tl.lightsOutTime === null) {
          // Lights are off in the DOM but that frame isn't confirmed on screen yet:
          // decide on the next frame, with a single comparison.
          if (this.pendingInput === null) this.pendingInput = t
        } else {
          this.resolve(t)
        }
        return
      case 'RESULT':
      case 'FALSE_START':
        if (t - this.resultShownAt >= RESULT_LOCK_MS) this.start(t)
        return
    }
  }

  /** Cancel a running attempt and return to the intro (tab hidden, stall, layout swap). */
  abort(): void {
    const running = this.isRunning()
    this.stopLoop()
    this.pendingInput = null
    this.setLit(0)
    if (running) {
      this.aborted = true
      this.phase = 'INTRO'
      this.emit()
    }
  }

  destroy(): void {
    this.stopLoop()
    this.pendingInput = null
  }

  // ---------------------------------------------------------------------------

  private isRunning(): boolean {
    return (
      this.phase === 'ARMED' ||
      this.phase === 'COUNTDOWN' ||
      this.phase === 'WAITING_FOR_LIGHTS_OUT' ||
      this.phase === 'REACTION_WINDOW'
    )
  }

  private uiPhase(): UiPhase {
    if (this.phase === 'INTRO') return 'INTRO'
    if (this.phase === 'RESULT') return 'RESULT'
    if (this.phase === 'FALSE_START') return 'FALSE_START'
    return 'RUNNING'
  }

  private emit(): void {
    const s = this.snapshot()
    // Only coarse UI changes reach React; internal light phases never re-render anything.
    if (s.ui === this.lastUi && s.ui === 'RUNNING') return
    this.lastUi = s.ui
    this.deps.onChange(s)
  }

  private setLit(n: number): void {
    if (n === this.litCount) return
    this.litCount = n
    this.deps.setLights(n)
  }

  private start(t: number): void {
    this.stopLoop()
    this.attempt += 1
    this.reactionMs = null
    this.aborted = false
    this.pendingInput = null
    this.setLit(0)

    const armDelay = ARM_DELAY_MIN_MS + this.random() * (ARM_DELAY_MAX_MS - ARM_DELAY_MIN_MS)
    const first = t + armDelay
    this.tl = {
      ...StartEngine.emptyTimeline(),
      sequenceStartTime: t,
      lightSchedule: [0, 1, 2, 3, 4].map((k) => first + k * LIGHT_INTERVAL_MS),
      holdMs: HOLD_MIN_MS + this.random() * (HOLD_MAX_MS - HOLD_MIN_MS),
    }
    this.phase = 'ARMED'
    this.emit()
    this.rafId = this.raf(this.tick)
  }

  private falseStart(t: number): void {
    this.stopLoop()
    this.tl.inputTime = t
    this.pendingInput = null
    this.setLit(0)
    this.reactionMs = null
    this.phase = 'FALSE_START'
    this.resultShownAt = t
    this.emit()
  }

  private resolve(t: number): void {
    const out = this.tl.lightsOutTime
    if (out === null) return
    if (t < out) {
      // Pressed before the dark lights could have been seen: that is a jump start.
      this.falseStart(t)
      return
    }
    this.stopLoop()
    this.tl.inputTime = t
    this.tl.reactionRaw = t - out
    this.reactionMs = Math.round(t - out)
    this.phase = 'RESULT'
    this.resultShownAt = t
    this.emit()
  }

  private stopLoop(): void {
    if (this.rafId !== null) {
      this.caf(this.rafId)
      this.rafId = null
    }
  }

  private readonly tick = (ts: number): void => {
    this.rafId = null
    const tl = this.tl

    if (this.phase === 'ARMED' || this.phase === 'COUNTDOWN') {
      let next = this.litCount
      while (next < 5 && ts >= tl.lightSchedule[next]) next += 1
      if (next !== this.litCount) {
        // A frame far behind schedule means lights would not appear 1 s apart.
        if (ts - tl.lightSchedule[next - 1] > STALL_ABORT_MS || next - this.litCount > 1) {
          this.abort()
          return
        }
        this.setLit(next)
        tl.lightCommitTimes.push(ts)
        if (next === 5) {
          tl.fifthLightTime = ts
          // Hold is measured from the scheduled fifth light so frame jitter doesn't leak in.
          tl.lightsOutDeadline = tl.lightSchedule[4] + tl.holdMs
          this.phase = 'WAITING_FOR_LIGHTS_OUT'
        } else {
          this.phase = 'COUNTDOWN'
        }
      }
    } else if (this.phase === 'WAITING_FOR_LIGHTS_OUT') {
      if (tl.lightsOutDeadline !== null && ts >= tl.lightsOutDeadline) {
        if (ts - tl.lightsOutDeadline > STALL_ABORT_MS) {
          this.abort()
          return
        }
        this.setLit(0)
        tl.lightsOutCommitTime = ts
        this.phase = 'REACTION_WINDOW'
      }
    } else if (this.phase === 'REACTION_WINDOW') {
      if (tl.lightsOutTime === null) {
        // First frame after the lights-off commit: the previous frame is now being shown.
        tl.lightsOutTime = ts
        if (this.pendingInput !== null) {
          const p = this.pendingInput
          this.pendingInput = null
          this.resolve(p)
          return
        }
      }
      // Clock is running; nothing more to do per frame.
      return
    } else {
      return
    }
    this.rafId = this.raf(this.tick)
  }
}
