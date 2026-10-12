import { useEffect, useRef, useState } from 'react'
import { StartEngine, VIBRATION_PX, type Snapshot } from './game/engine'
import { attachInput } from './game/input'
import { Stage, type StageHandle } from './scene/Stage'
import { useSceneLoader, useVariantName } from './scene/useScene'
import { Overlay } from './ui/Overlay'
import { Loading } from './ui/Loading'

declare global {
  interface Window {
    /** Only present with ?debug — exposes the engine for automated timing checks. */
    __lightsOut?: StartEngine
  }
}

export default function App() {
  const variantName = useVariantName()
  const { scene, progress, error } = useSceneLoader(variantName)
  const stageRef = useRef<StageHandle>(null)
  const engineRef = useRef<StartEngine | null>(null)
  const [snap, setSnap] = useState<Snapshot>({ ui: 'INTRO', attempt: 0, reactionMs: null, aborted: false })

  // One engine per mount; Strict Mode's double effect simply creates and destroys one extra.
  useEffect(() => {
    const engine = new StartEngine({
      setLights: (n) => stageRef.current?.setLights(n),
      onPhase: (p) => stageRef.current?.setVibration(VIBRATION_PX[p]),
      onChange: setSnap,
    })
    engineRef.current = engine
    const detach = attachInput(engine)
    if (new URLSearchParams(location.search).has('debug')) window.__lightsOut = engine
    return () => {
      detach()
      engine.destroy()
      engineRef.current = null
      if (window.__lightsOut === engine) delete window.__lightsOut
    }
  }, [])

  // Only accept input once the visible scene matches the viewport and is fully decoded.
  const ready = scene !== null && scene.variant.name === variantName
  useEffect(() => {
    engineRef.current?.setReady(ready)
  }, [ready])

  return (
    <main className="stage-root fixed inset-0 touch-none overflow-hidden bg-black text-white">
      {scene && <Stage ref={stageRef} scene={scene} />}
      {scene ? <Overlay snap={snap} /> : <Loading progress={progress} error={error} />}
      {scene && !ready && <Loading progress={progress} error={error} subtle />}
    </main>
  )
}
