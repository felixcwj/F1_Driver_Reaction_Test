import { memo, useState, type ReactNode } from 'react'
import { isEasterEgg, type Snapshot } from '../game/engine'
import { UI_ATTR } from '../game/input'

const uiProps = { [UI_ATTR]: '' }

function Kicker({ children, tone = 'red' }: { children: ReactNode; tone?: 'red' | 'muted' }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className={`h-[0.9em] w-[3px] ${tone === 'red' ? 'bg-race' : 'bg-white/50'}`} />
      <span className="text-[11px] font-semibold uppercase tracking-[0.32em] text-white/80 sm:text-xs">{children}</span>
    </div>
  )
}

function Prompt({ children }: { children: ReactNode }) {
  return (
    <p className="prompt mt-7 text-[11px] font-semibold uppercase tracking-[0.34em] text-white/85 sm:text-[13px]">
      {children}
    </p>
  )
}

function Intro({ aborted }: { aborted: boolean }) {
  return (
    <div className="panel-in flex flex-col items-center text-center">
      <Kicker>SINGAPORE • NIGHT RACE</Kicker>
      <h1 className="mt-4 text-[clamp(44px,11vw,104px)] leading-[0.9] font-black tracking-[-0.01em] text-white italic">
        LIGHTS OUT
      </h1>
      <p className="mt-3 text-[15px] font-normal text-white/75 sm:text-lg">How fast can you react?</p>
      <Prompt>TAP ANYWHERE TO START</Prompt>
      <p className="desktop-only mt-2.5 text-[11px] tracking-[0.2em] text-white/45 uppercase">
        or press <kbd className="rounded-[3px] border border-white/25 px-1.5 py-0.5 font-sans text-white/70">Space</kbd>
      </p>
      {aborted && (
        <p className="mt-5 text-xs text-white/55">Start cancelled — the page was hidden. Ready when you are.</p>
      )}
    </div>
  )
}

function Result({ ms }: { ms: number }) {
  const egg = isEasterEgg(ms)
  return (
    <div className="panel-in flex flex-col items-center text-center">
      <Kicker>LIGHTS OUT</Kicker>
      <div className="mt-3 flex items-baseline gap-2 font-black text-white tabular-nums">
        <span className="text-[clamp(84px,24vw,200px)] leading-[0.85] tracking-[-0.03em]" data-testid="reaction-ms">
          {ms}
        </span>
        <span className="text-[clamp(22px,5vw,40px)] font-semibold text-white/80">ms</span>
      </div>
      <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.34em] text-white/60 sm:text-xs">Reaction Time</p>
      {egg && (
        <p className="egg mt-6 text-[15px] font-semibold text-white sm:text-lg" data-testid="easter-egg">
          Are you Max Verstappen?
        </p>
      )}
      <Prompt>TAP ANYWHERE TO RETRY</Prompt>
    </div>
  )
}

function FalseStart() {
  return (
    <div className="panel-in flex flex-col items-center text-center">
      <Kicker>JUMP START</Kicker>
      <h2 className="mt-4 text-[clamp(48px,13vw,120px)] leading-[0.88] font-black text-race italic" data-testid="false-start">
        FALSE START
      </h2>
      <p className="mt-3 text-[15px] text-white/75 sm:text-lg">You jumped the start.</p>
      <Prompt>TAP ANYWHERE TO RETRY</Prompt>
    </div>
  )
}

function Info() {
  const [open, setOpen] = useState(false)
  return (
    <div {...uiProps} className="pointer-events-auto absolute right-3 bottom-[max(12px,env(safe-area-inset-bottom))] flex flex-col items-end gap-2 sm:right-5">
      {open && (
        <div
          id="about"
          className="max-w-[320px] rounded-md border border-white/10 bg-black/75 p-4 text-left text-[12px] leading-relaxed text-white/75 backdrop-blur-md"
        >
          <p>
            Your time runs from the first displayed frame with the lights out to the moment of your tap, click or Space
            press, using the browser&apos;s high-resolution clock. Screen, touch-panel and input-device latency are part
            of every result, so treat it as a fun estimate rather than a lab measurement.
          </p>
          <p className="mt-2 text-white/50">
            Prototype imagery: reference still of a Singapore night grid, used for visual development only.
            Third-party marks belong to their owners.
          </p>
        </div>
      )}
      <button
        type="button"
        aria-expanded={open}
        aria-controls="about"
        onClick={() => setOpen((o) => !o)}
        className="grid h-8 w-8 place-items-center rounded-full border border-white/20 bg-black/40 text-[13px] font-semibold text-white/70 backdrop-blur-sm transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-white/70"
      >
        {open ? '×' : 'i'}
        <span className="sr-only">{open ? 'Close info' : 'About this test'}</span>
      </button>
    </div>
  )
}

export const Overlay = memo(function Overlay({ snap }: { snap: Snapshot }) {
  const { ui } = snap
  const showInfo = ui === 'INTRO' || ui === 'RESULT' || ui === 'FALSE_START'
  return (
    <div className="pointer-events-none absolute inset-0 select-none">
      <div className={`dim absolute inset-0 ${ui === 'RUNNING' ? 'opacity-0' : ui === 'INTRO' ? 'opacity-60' : 'opacity-100'}`} />
      <div
        className="absolute inset-x-0 bottom-[22%] flex justify-center px-4 sm:bottom-[16%]"
        role="status"
        aria-live="polite"
      >
        {ui === 'INTRO' && <Intro aborted={snap.aborted} />}
        {ui === 'RESULT' && snap.reactionMs !== null && <Result key={snap.attempt} ms={snap.reactionMs} />}
        {ui === 'FALSE_START' && <FalseStart key={snap.attempt} />}
      </div>
      {showInfo && <Info />}
    </div>
  )
})
