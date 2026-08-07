import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'

import Scene from './Scene'
import { Detail, Legend, Metrics, Verdict } from './Panel'
import { SURFACE } from './palette'
import type { Plan } from './types'

const SAMPLE = `${import.meta.env.BASE_URL}sample-plan.json`

/** Frames per placement when the loading animation runs. */
const STEP_MS = 90

async function fetchPlan(): Promise<Plan> {
  const planId = new URLSearchParams(window.location.search).get('plan')
  if (planId) {
    const response = await fetch(`/plans/${encodeURIComponent(planId)}`)
    if (!response.ok) {
      throw new Error(`the service returned ${response.status} for plan ${planId}`)
    }
    return response.json()
  }
  // No plan asked for: fall back to the bundled example, so the built page is
  // a working demo with no service behind it.
  const response = await fetch(SAMPLE)
  if (!response.ok) throw new Error('no plan requested and no sample bundled')
  return response.json()
}

export default function App() {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [visible, setVisible] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [transparent, setTransparent] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback((next: Plan) => {
    setPlan(next)
    setVisible(next.placements.length)
    setSelected(null)
    setError(null)
  }, [])

  useEffect(() => {
    fetchPlan()
      .then(load)
      .catch((problem: Error) => setError(problem.message))
  }, [load])

  const total = plan?.placements.length ?? 0

  useEffect(() => {
    if (!playing || total === 0) return
    const timer = window.setInterval(() => {
      setVisible((current) => {
        if (current >= total) {
          setPlaying(false)
          return current
        }
        return current + 1
      })
    }, STEP_MS)
    return () => window.clearInterval(timer)
  }, [playing, total])

  const stops = useMemo(
    () => [...new Set(plan?.placements.map((p) => p.stop) ?? [])].sort((a, b) => a - b),
    [plan],
  )
  const selectedPlacement = useMemo(
    () => plan?.placements.find((p) => p.item_uid === selected) ?? null,
    [plan, selected],
  )

  function openFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    file
      .text()
      .then((text) => load(JSON.parse(text) as Plan))
      .catch(() => setError(`${file.name} is not a plan document`))
  }

  if (error && !plan) {
    return (
      <div className="fatal">
        <h1>LoadZa</h1>
        <p>{error}</p>
        <p className="hint">
          Start the service and pass a plan id: <code>?plan=&lt;id&gt;</code>, or open a
          plan file below.
        </p>
        <input type="file" accept="application/json" onChange={openFile} />
      </div>
    )
  }

  if (!plan) return <div className="fatal">loading…</div>

  return (
    <div className="app">
      <header>
        <div className="title">
          <h1>{plan.job_id}</h1>
          <p>
            {plan.vehicle.name} · <code>{plan.algorithm}</code>
          </p>
        </div>
        <Verdict plan={plan} />
      </header>

      <main>
        <Canvas
          camera={{ position: [10, 7, 9], fov: 42, near: 0.05, far: 400 }}
          style={{ background: SURFACE }}
          onPointerMissed={() => setSelected(null)}
        >
          <Scene
            plan={plan}
            visibleCount={visible}
            selected={selected}
            onSelect={setSelected}
            transparent={transparent}
          />
        </Canvas>

        <aside>
          <Metrics plan={plan} />
          <Legend stops={stops} />
          <h2>Selection</h2>
          <Detail placement={selectedPlacement} vehicle={plan.vehicle} />
          {plan.unplaced.length > 0 && (
            <>
              <h2>Left behind</h2>
              <p className="hint">
                {plan.unplaced.length} items did not fit:{' '}
                {[...new Set(plan.unplaced.map((u) => u.reason))].join(', ')}.
              </p>
            </>
          )}
        </aside>
      </main>

      <footer>
        <button
          onClick={() => {
            // Replay has to rewind first, or "play" at the end does nothing.
            if (!playing && visible >= total) setVisible(0)
            setPlaying((p) => !p)
          }}
          disabled={total === 0}
        >
          {playing ? 'Pause' : visible >= total ? 'Replay' : 'Play'}
        </button>
        <input
          type="range"
          min={0}
          max={total}
          value={visible}
          onChange={(event) => {
            setPlaying(false)
            setVisible(Number(event.target.value))
          }}
          aria-label="loading step"
        />
        <span className="counter">
          {visible} / {total} loaded
        </span>
        <label className="toggle">
          <input
            type="checkbox"
            checked={transparent}
            onChange={(event) => setTransparent(event.target.checked)}
          />
          see through
        </label>
        <button className="ghost" onClick={() => fileInput.current?.click()}>
          Open plan…
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="application/json"
          onChange={openFile}
          hidden
        />
      </footer>
    </div>
  )
}
