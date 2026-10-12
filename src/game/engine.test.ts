import { describe, expect, it } from 'vitest'
import {
  ARM_DELAY_MAX_MS,
  ARM_DELAY_MIN_MS,
  HOLD_MAX_MS,
  HOLD_MIN_MS,
  LIGHT_INTERVAL_MS,
  RESULT_LOCK_MS,
  StartEngine,
  isEasterEgg,
  type Snapshot,
} from './engine'

/** Deterministic 60 Hz frame clock driving the engine. */
function harness(randomValues: number[] = [0.5, 0.5]) {
  let t = 1000
  const frame = 1000 / 60
  let queue: { id: number; cb: FrameRequestCallback }[] = []
  let nextId = 1
  const lights: number[] = []
  const changes: Snapshot[] = []
  let r = 0
  const engine = new StartEngine({
    setLights: (n) => lights.push(n),
    onChange: (s) => changes.push(s),
    raf: (cb) => {
      queue.push({ id: nextId, cb })
      return nextId++
    },
    caf: (id) => {
      queue = queue.filter((q) => q.id !== id)
    },
    random: () => randomValues[r++ % randomValues.length],
  })
  engine.setReady(true)
  const step = () => {
    t += frame
    const q = queue
    queue = []
    q.forEach(({ cb }) => cb(t))
  }
  const advance = (ms: number) => {
    const end = t + ms
    while (t + frame <= end) step()
  }
  const runUntil = (pred: () => boolean, maxMs = 10000) => {
    const end = t + maxMs
    while (!pred() && t < end) step()
  }
  return {
    engine,
    lights,
    changes,
    step,
    advance,
    runUntil,
    get t() {
      return t
    },
    set t(v: number) {
      t = v
    },
    pending: () => queue.length,
  }
}

describe('StartEngine sequence', () => {
  it('stays in INTRO until the first press, and ignores input before assets are ready', () => {
    const h = harness()
    h.engine.setReady(false)
    h.engine.press(h.t)
    expect(h.engine.currentPhase).toBe('INTRO')
    h.engine.setReady(true)
    h.engine.press(h.t)
    expect(h.engine.currentPhase).toBe('ARMED')
  })

  it('lights five reds one second apart, then all go out together after a random hold', () => {
    const h = harness([0.5, 0.25])
    h.engine.press(h.t)
    h.runUntil(() => h.engine.currentPhase === 'REACTION_WINDOW')
    // 1,2,3,4,5 lights then 0 — never a partial switch-off, never more than 5
    expect(h.lights).toEqual([1, 2, 3, 4, 5, 0])
    const tl = h.engine.timeline
    const sched = tl.lightSchedule
    for (let k = 1; k < 5; k++) expect(sched[k] - sched[k - 1]).toBe(LIGHT_INTERVAL_MS)
    // committed frames land within one frame of schedule
    tl.lightCommitTimes.forEach((c, k) => {
      expect(c - sched[k]).toBeGreaterThanOrEqual(0)
      expect(c - sched[k]).toBeLessThan(1000 / 60 + 0.001)
    })
    const armDelay = sched[0] - tl.sequenceStartTime
    expect(armDelay).toBeGreaterThanOrEqual(ARM_DELAY_MIN_MS)
    expect(armDelay).toBeLessThanOrEqual(ARM_DELAY_MAX_MS)
    expect(tl.holdMs).toBeCloseTo(HOLD_MIN_MS + 0.25 * (HOLD_MAX_MS - HOLD_MIN_MS))
    expect(tl.lightsOutCommitTime! - tl.lightsOutDeadline!).toBeLessThan(1000 / 60 + 0.001)
  })

  it('hold time stays inside 0.2–3.0 s for extreme random values', () => {
    for (const v of [0, 0.999999]) {
      const h = harness([0.5, v])
      h.engine.press(h.t)
      expect(h.engine.timeline.holdMs).toBeGreaterThanOrEqual(HOLD_MIN_MS)
      expect(h.engine.timeline.holdMs).toBeLessThan(HOLD_MAX_MS)
    }
  })

  it('measures from the first frame on which the lights were off, not from the deadline', () => {
    const h = harness()
    h.engine.press(h.t)
    h.runUntil(() => h.engine.currentPhase === 'REACTION_WINDOW')
    expect(h.engine.timeline.lightsOutTime).toBeNull()
    h.step()
    const out = h.engine.timeline.lightsOutTime!
    expect(out).toBeGreaterThan(h.engine.timeline.lightsOutCommitTime!)
    h.engine.press(out + 187.4)
    expect(h.engine.currentPhase).toBe('RESULT')
    expect(h.engine.snapshot().reactionMs).toBe(187)
    expect(h.changes.at(-1)).toMatchObject({ ui: 'RESULT', reactionMs: 187 })
  })

  it('treats a press that lands before the dark frame is on screen as a jump start', () => {
    const h = harness()
    h.engine.press(h.t)
    h.runUntil(() => h.engine.currentPhase === 'REACTION_WINDOW')
    const commit = h.engine.timeline.lightsOutCommitTime!
    h.engine.press(commit + 2) // after the DOM switch, before the next frame
    expect(h.engine.currentPhase).toBe('REACTION_WINDOW')
    h.step()
    expect(h.engine.currentPhase).toBe('FALSE_START')
    expect(h.engine.snapshot().reactionMs).toBeNull()
  })
})

describe('false starts', () => {
  for (const lit of [0, 1, 3, 5]) {
    it(`press with ${lit} light(s) on is a FALSE START without a time`, () => {
      const h = harness()
      h.engine.press(h.t)
      h.runUntil(() => (h.lights.at(-1) ?? 0) === lit && h.lights.length >= lit, 8000)
      if (lit === 5) h.advance(100) // still holding with all five on
      if (lit === 0) h.advance(300) // armed, before the first light
      h.engine.press(h.t)
      expect(h.engine.currentPhase).toBe('FALSE_START')
      expect(h.engine.snapshot()).toMatchObject({ ui: 'FALSE_START', reactionMs: null })
      expect(h.lights.at(-1) ?? 0).toBe(0)
      expect(h.pending()).toBe(0) // no stale frame callbacks left behind
    })
  }

  it('the press that starts the sequence is never itself a false start', () => {
    const h = harness()
    h.engine.press(h.t)
    h.engine.press(h.t + 5) // same gesture echoed (e.g. duplicated event)
    expect(h.engine.currentPhase).toBe('ARMED')
  })
})

describe('retry and lifecycle', () => {
  it('locks the result briefly, then a press starts a fresh attempt with cleared result', () => {
    const h = harness()
    h.engine.press(h.t)
    h.runUntil(() => h.engine.currentPhase === 'REACTION_WINDOW')
    h.step()
    const out = h.engine.timeline.lightsOutTime!
    h.engine.press(out + 250)
    const attempt = h.engine.snapshot().attempt
    h.engine.press(out + 250 + RESULT_LOCK_MS / 2)
    expect(h.engine.currentPhase).toBe('RESULT')
    h.engine.press(out + 250 + RESULT_LOCK_MS + 1)
    expect(h.engine.currentPhase).toBe('ARMED')
    expect(h.engine.snapshot()).toMatchObject({ attempt: attempt + 1, reactionMs: null, ui: 'RUNNING' })
  })

  it('abort (hidden tab) cancels the run, clears the lights and leaves no timers', () => {
    const h = harness()
    h.engine.press(h.t)
    h.runUntil(() => h.lights.at(-1) === 3)
    h.engine.abort()
    expect(h.engine.currentPhase).toBe('INTRO')
    expect(h.engine.snapshot().aborted).toBe(true)
    expect(h.lights.at(-1)).toBe(0)
    expect(h.pending()).toBe(0)
  })

  it('aborts instead of showing lights late after a long frame stall', () => {
    const h = harness()
    h.engine.press(h.t)
    h.runUntil(() => h.lights.at(-1) === 2)
    h.t = h.t + 2500 // e.g. throttled tab: two lights would be skipped
    h.step()
    expect(h.engine.currentPhase).toBe('INTRO')
    expect(h.engine.snapshot().aborted).toBe(true)
  })

  it('React is not notified on the lights-out frame', () => {
    const h = harness()
    h.engine.press(h.t)
    const before = h.changes.length
    h.runUntil(() => h.engine.currentPhase === 'REACTION_WINDOW')
    h.step()
    expect(h.changes.length).toBe(before)
  })

  it('random holds differ between attempts with the real RNG', () => {
    const holds = new Set<number>()
    for (let i = 0; i < 20; i++) {
      const e = new StartEngine({ setLights: () => {}, onChange: () => {}, raf: () => 1, caf: () => {} })
      e.setReady(true)
      e.press(1000)
      holds.add(Math.round(e.timeline.holdMs))
    }
    expect(holds.size).toBeGreaterThan(15)
  })
})

describe('easter egg', () => {
  it('shows only for results under 100 ms', () => {
    expect(isEasterEgg(99)).toBe(true)
    expect(isEasterEgg(0)).toBe(true)
    expect(isEasterEgg(100)).toBe(false)
    expect(isEasterEgg(187)).toBe(false)
    expect(isEasterEgg(null)).toBe(false)
  })
})
