import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'

import Scene from './Scene'
import JobForm from './JobForm'
import JobList from './JobList'
import { Detail, Legend, Metrics, Verdict } from './Panel'
import { getCatalog, getPlan } from './api'
import type { Catalog } from './api'
import { SURFACE } from './palette'
import type { Plan } from './types'

const SAMPLE = `${import.meta.env.BASE_URL}sample-plan.json`

/** Milliseconds per placement when the loading animation runs. */
const STEP_MS = 90

type Tab = 'new' | 'jobs' | 'view'

export default function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [offline, setOffline] = useState(false)
  const [tab, setTab] = useState<Tab>('view')

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
    setPlaying(false)
    setError(null)
    setTab('view')
  }, [])

  const openPlan = useCallback(
    (planId: string) => {
      getPlan(planId)
        .then((next) => {
          load(next)
          const url = new URL(window.location.href)
          url.searchParams.set('plan', planId)
          window.history.replaceState(null, '', url)
        })
        .catch((problem: Error) => setError(problem.message))
    },
    [load],
  )

  // Decide once, on load, whether there is a service to talk to. With one, the
  // page is a workbench; without one it is still a working demo of a bundled
  // plan, which is what makes a static host enough for a shareable link.
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('plan')
    getCatalog()
      .then((data) => {
        setCatalog(data)
        if (requested) openPlan(requested)
        else setTab('new')
      })
      .catch(() => {
        setOffline(true)
        fetch(SAMPLE)
          .then((response) => response.json())
          .then(load)
          .catch(() => setError('no service reachable and no sample bundled'))
      })
  }, [load, openPlan])

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

  return (
    <div className="app">
      <header>
        <div className="title">
          <h1>{plan ? plan.job_id : 'LoadZa'}</h1>
          <p>
            {plan ? (
              <>
                {plan.vehicle.name} · <code>{plan.algorithm}</code>
              </>
            ) : (
              'container loading — build a job, solve it, look at it'
            )}
          </p>
        </div>

        <nav className="tabs">
          <button
            className={tab === 'new' ? 'on' : ''}
            onClick={() => setTab('new')}
            disabled={offline}
            title={offline ? 'needs the service running' : undefined}
          >
            New job
          </button>
          <button
            className={tab === 'jobs' ? 'on' : ''}
            onClick={() => setTab('jobs')}
            disabled={offline}
            title={offline ? 'needs the service running' : undefined}
          >
            Jobs
          </button>
          <button
            className={tab === 'view' ? 'on' : ''}
            onClick={() => setTab('view')}
            disabled={!plan}
          >
            Plan
          </button>
        </nav>

        {plan && tab === 'view' && <Verdict plan={plan} />}
      </header>

      {error && <p className="error banner">{error}</p>}

      {tab === 'new' && catalog && (
        <div className="scroller">
          <JobForm catalog={catalog} onSolved={openPlan} />
        </div>
      )}

      {tab === 'jobs' && (
        <div className="scroller">
          <JobList onOpen={openPlan} />
        </div>
      )}

      {tab === 'view' && !plan && (
        <div className="scroller">
          <p className="hint">loading…</p>
        </div>
      )}

      {tab === 'view' && plan && (
        <>
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
              {offline && (
                <>
                  <h2>Demo mode</h2>
                  <p className="hint">
                    No service reachable, so this is the bundled example. Start it
                    with <code>uvicorn app.api:app</code> to build your own jobs.
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
        </>
      )}
    </div>
  )
}
