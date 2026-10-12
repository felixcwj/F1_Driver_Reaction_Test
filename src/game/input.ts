import type { StartEngine } from './engine'

/** Elements marked with this attribute are real controls and never count as a game press. */
export const UI_ATTR = 'data-ui'

function eventTime(e: Event): number {
  const now = performance.now()
  const t = e.timeStamp
  // Event.timeStamp is a high-resolution time on the performance.now() timeline in every
  // current browser. Fall back to handler time if a browser reports something implausible.
  if (Number.isFinite(t) && t > 0 && t <= now + 1 && now - t < 1000) return t
  return now
}

function fromUi(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(`[${UI_ATTR}]`) !== null
}

/**
 * Wire one physical press per gesture into the engine:
 *  - pointerdown (mouse left button, touch, pen) — fires earlier than click/touchend and
 *    is the only pointer event we listen to, so a tap can't count twice via a later click.
 *  - Space keydown, ignoring auto-repeat and requiring a release between presses, so
 *    holding the key down can never register as a fresh reaction.
 */
export function attachInput(engine: StartEngine, target: Window = window): () => void {
  let spaceHeld = false

  const onPointerDown = (e: PointerEvent) => {
    if (!e.isPrimary) return
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (fromUi(e.target)) return
    if (e.cancelable) e.preventDefault()
    engine.press(eventTime(e))
  }

  const isSpace = (e: KeyboardEvent) => e.code === 'Space' || e.key === ' ' || e.key === 'Spacebar'

  const onKeyDown = (e: KeyboardEvent) => {
    if (!isSpace(e)) return
    // A focused control handles its own Space (activation); never also start/react.
    if (fromUi(document.activeElement) || fromUi(e.target)) return
    e.preventDefault() // no page scroll
    if (e.repeat || spaceHeld) return
    spaceHeld = true
    engine.press(eventTime(e))
  }

  const onKeyUp = (e: KeyboardEvent) => {
    if (!isSpace(e)) return
    spaceHeld = false
    if (!fromUi(document.activeElement)) e.preventDefault()
  }

  const onBlur = () => {
    spaceHeld = false
  }

  const onContextMenu = (e: Event) => {
    if (!fromUi(e.target)) e.preventDefault()
  }

  const onVisibility = () => {
    if (document.visibilityState === 'hidden') engine.abort()
  }

  const onPageHide = () => engine.abort()

  const opts: AddEventListenerOptions = { passive: false, capture: true }
  target.addEventListener('pointerdown', onPointerDown, opts)
  target.addEventListener('keydown', onKeyDown, opts)
  target.addEventListener('keyup', onKeyUp, opts)
  target.addEventListener('blur', onBlur)
  target.addEventListener('contextmenu', onContextMenu)
  target.addEventListener('pagehide', onPageHide)
  document.addEventListener('visibilitychange', onVisibility)

  return () => {
    target.removeEventListener('pointerdown', onPointerDown, opts)
    target.removeEventListener('keydown', onKeyDown, opts)
    target.removeEventListener('keyup', onKeyUp, opts)
    target.removeEventListener('blur', onBlur)
    target.removeEventListener('contextmenu', onContextMenu)
    target.removeEventListener('pagehide', onPageHide)
    document.removeEventListener('visibilitychange', onVisibility)
  }
}
