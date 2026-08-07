import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'

import Scene from './Scene'
import JobForm from './JobForm'
import JobList from './JobList'
import { Detail, Legend, Metrics, Verdict } from './Panel'
import { getCatalog, getPlan } from './api'
import type { Catalog } from './api'
import {
  LanguageContext,
  displayName,
  initialLanguage,
  rememberLanguage,
  translate,
} from './i18n'
import type { Key, Lang } from './i18n'
import { SURFACE } from './palette'
import type { Plan } from './types'

const SAMPLE = `${import.meta.env.BASE_URL}sample-plan.json`

/** Milliseconds per placement when the loading animation runs. */
const STEP_MS = 90

type Tab = 'new' | 'jobs' | 'view'

export default function App() {
  const [lang, setLangState] = useState<Lang>(initialLanguage)
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

  const t = useCallback(
    (key: Key, vars?: Record<string, string | number>) => translate(lang, key, vars),
    [lang],
  )
  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    rememberLanguage(next)
    document.documentElement.lang = next
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

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
          .catch(() => setError(translate(lang, 'view.nothing')))
      })
    // Runs once: re-probing the service because the language changed would be
    // absurd, so `lang` is deliberately not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      .catch(() => setError(t('view.badFile', { name: file.name })))
  }

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
    <div className="app">
      <header>
        <div className="title">
          <h1>{plan ? plan.job_id : 'LoadZa'}</h1>
          <p>
            {plan ? (
              <>
                {displayName(lang, plan.vehicle.code, plan.vehicle.name)} ·{' '}
                <code>{plan.algorithm}</code>
              </>
            ) : (
              t('app.subtitle')
            )}
          </p>
        </div>

        <nav className="tabs">
          <button
            className={tab === 'new' ? 'on' : ''}
            onClick={() => setTab('new')}
            disabled={offline}
            title={offline ? t('tab.needsService') : undefined}
          >
            {t('tab.new')}
          </button>
          <button
            className={tab === 'jobs' ? 'on' : ''}
            onClick={() => setTab('jobs')}
            disabled={offline}
            title={offline ? t('tab.needsService') : undefined}
          >
            {t('tab.jobs')}
          </button>
          <button
            className={tab === 'view' ? 'on' : ''}
            onClick={() => setTab('view')}
            disabled={!plan}
          >
            {t('tab.plan')}
          </button>
        </nav>

        {plan && tab === 'view' && <Verdict plan={plan} />}

        <div className="lang" role="group" aria-label="language">
          {(['en', 'tr'] as Lang[]).map((code) => (
            <button
              key={code}
              className={lang === code ? 'on' : ''}
              onClick={() => setLang(code)}
              aria-pressed={lang === code}
            >
              {code.toUpperCase()}
            </button>
          ))}
        </div>
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
          <p className="hint">{t('common.loading')}</p>
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
                doorLabel={t('scene.doors')}
              />
            </Canvas>

            <aside>
              <Metrics plan={plan} />
              <Legend stops={stops} />
              <h2>{t('view.selection')}</h2>
              <Detail placement={selectedPlacement} vehicle={plan.vehicle} />
              {plan.unplaced.length > 0 && (
                <>
                  <h2>{t('view.leftBehind')}</h2>
                  <p className="hint">
                    {t('view.leftBehindDetail', {
                      n: plan.unplaced.length,
                      reasons: [...new Set(plan.unplaced.map((u) => u.reason))].join(', '),
                    })}
                  </p>
                </>
              )}
              {offline && (
                <>
                  <h2>{t('view.demoMode')}</h2>
                  <p className="hint">
                    {t('view.demoModeDetail', { cmd: 'uvicorn app.api:app' })}
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
              {playing
                ? t('view.pause')
                : visible >= total
                  ? t('view.replay')
                  : t('view.play')}
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
              aria-label={t('view.step')}
            />
            <span className="counter">{t('view.loaded', { n: visible, total })}</span>
            <label className="toggle">
              <input
                type="checkbox"
                checked={transparent}
                onChange={(event) => setTransparent(event.target.checked)}
              />
              {t('view.seeThrough')}
            </label>
            <button className="ghost" onClick={() => fileInput.current?.click()}>
              {t('view.openPlan')}
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
    </LanguageContext.Provider>
  )
}
