import { useMemo, useState } from 'react'

import { createJob, solveJob } from './api'
import type { Catalog, ItemType, JobLine, SolveOptions } from './api'
import { displayName, useT } from './i18n'
import type { Key } from './i18n'
import { stopColour } from './palette'
import type { Vehicle } from './types'

const DEFAULT_OPTIONS: SolveOptions = {
  scorer: 'layer',
  search: 'first_fit',
  anneal_seconds: null,
  enforce_lifo: true,
  enforce_stacking: true,
  rebalance: true,
  balance_lateral: false,
}

function volumeOf(t: ItemType): number {
  return t.dims_mm.length * t.dims_mm.width * t.dims_mm.height
}

function suggestId(vehicleCode: string): string {
  const stamp = new Date().toISOString().slice(5, 16).replace(/[-:T]/g, '')
  return `${vehicleCode}-${stamp}`
}

export default function JobForm({
  catalog,
  onSolved,
}: {
  catalog: Catalog
  onSolved: (planId: string) => void
}) {
  const { t, lang } = useT()
  const [vehicleCode, setVehicleCode] = useState(catalog.vehicles[0]?.code ?? '')
  const [jobId, setJobId] = useState(() => suggestId(catalog.vehicles[0]?.code ?? 'JOB'))
  const [lines, setLines] = useState<JobLine[]>([
    { sku: catalog.item_types[0]?.sku ?? '', qty: 20, stop: 1 },
  ])
  const [options, setOptions] = useState<SolveOptions>(DEFAULT_OPTIONS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const vehicle: Vehicle | undefined = useMemo(
    () => catalog.vehicles.find((v) => v.code === vehicleCode),
    [catalog.vehicles, vehicleCode],
  )
  const types = useMemo(
    () => new Map(catalog.item_types.map((t) => [t.sku, t])),
    [catalog.item_types],
  )

  const totals = useMemo(() => {
    let volume = 0
    let weight = 0
    let count = 0
    for (const line of lines) {
      const type = types.get(line.sku)
      if (!type) continue
      volume += volumeOf(type) * line.qty
      weight += type.weight_g * line.qty
      count += line.qty
    }
    return { volume, weight, count }
  }, [lines, types])

  const capacity = vehicle
    ? vehicle.inner_mm.length * vehicle.inner_mm.width * vehicle.inner_mm.height
    : 1
  const volumeRatio = totals.volume / capacity
  const weightRatio = vehicle ? totals.weight / vehicle.max_payload_g : 0

  function update(index: number, patch: Partial<JobLine>) {
    setLines((current) =>
      current.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    )
  }

  function pickVehicle(code: string) {
    setVehicleCode(code)
    setJobId((current) => (current.startsWith(vehicleCode) ? suggestId(code) : current))
  }

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const usable = lines.filter((line) => line.sku && line.qty > 0)
      if (usable.length === 0) throw new Error(t('form.needLine'))
      await createJob(jobId.trim(), vehicleCode, usable)
      const plan = await solveJob(jobId.trim(), options)
      onSolved(plan.plan_id)
    } catch (problem) {
      setError((problem as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="form">
      <section>
        <h2>{t('form.vehicle')}</h2>
        <div className="row">
          <select value={vehicleCode} onChange={(e) => pickVehicle(e.target.value)}>
            {catalog.vehicles.map((v) => (
              <option key={v.code} value={v.code}>
                {displayName(lang, v.code, v.name)}
              </option>
            ))}
          </select>
          <input
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            aria-label={t('form.jobId')}
            placeholder={t('form.jobId')}
          />
        </div>
        {vehicle && (
          <p className="hint">
            {t('form.vehicleSpec', {
              l: vehicle.inner_mm.length,
              w: vehicle.inner_mm.width,
              h: vehicle.inner_mm.height,
              v: (capacity / 1e9).toFixed(1),
              t: (vehicle.max_payload_g / 1e6).toFixed(1),
            })}
          </p>
        )}
      </section>

      <section>
        <h2>{t('form.cargo')}</h2>
        <table className="lines">
          <thead>
            <tr>
              <th>{t('form.colItem')}</th>
              <th>{t('form.colQty')}</th>
              <th>{t('form.colStop')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((line, index) => {
              const type = types.get(line.sku)
              return (
                <tr key={index}>
                  <td>
                    <select
                      value={line.sku}
                      onChange={(e) => update(index, { sku: e.target.value })}
                    >
                      {catalog.item_types.map((t) => (
                        <option key={t.sku} value={t.sku}>
                          {displayName(lang, t.sku, t.name)} ({t.dims_mm.length}×
                          {t.dims_mm.width}×{t.dims_mm.height})
                        </option>
                      ))}
                    </select>
                    {type?.fragile && <span className="tag">{t('form.fragile')}</span>}
                    {type?.this_side_up && (
                      <span className="tag">{t('form.thisSideUp')}</span>
                    )}
                  </td>
                  <td>
                    <input
                      type="number"
                      min={1}
                      max={2000}
                      value={line.qty}
                      onChange={(e) =>
                        update(index, { qty: Math.max(1, Number(e.target.value)) })
                      }
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      min={1}
                      max={9}
                      value={line.stop}
                      onChange={(e) =>
                        update(index, { stop: Math.max(1, Number(e.target.value)) })
                      }
                      style={{ borderLeft: `4px solid ${stopColour(line.stop)}` }}
                    />
                  </td>
                  <td>
                    <button
                      className="ghost"
                      onClick={() =>
                        setLines((current) => current.filter((_, i) => i !== index))
                      }
                      disabled={lines.length === 1}
                      aria-label={t('form.removeLine')}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <button
          className="ghost"
          onClick={() =>
            setLines((current) => [
              ...current,
              { sku: catalog.item_types[0].sku, qty: 10, stop: 1 },
            ])
          }
        >
          {t('form.addLine')}
        </button>

        <div className="gauges">
          <Gauge
            label={t('form.gaugeVolume')}
            ratio={volumeRatio}
            note={t('form.nItems', { n: totals.count })}
          />
          <Gauge
            label={t('form.gaugeWeight')}
            ratio={weightRatio}
            note={`${(totals.weight / 1e6).toFixed(2)} t`}
          />
        </div>
        {(volumeRatio > 1 || weightRatio > 1) && (
          <p className="hint">{t('form.overCapacity')}</p>
        )}
      </section>

      <section>
        <h2>{t('form.solver')}</h2>
        <div className="row">
          <label>
            {t('form.corner')}
            <select
              value={options.scorer}
              onChange={(e) => setOptions({ ...options, scorer: e.target.value })}
            >
              <option value="layer">{t('form.cornerLayer')}</option>
              <option value="dbl">{t('form.cornerDbl')}</option>
              <option value="contact">{t('form.cornerContact')}</option>
            </select>
          </label>
          <label>
            {t('form.search')}
            <select
              value={options.search}
              onChange={(e) => setOptions({ ...options, search: e.target.value })}
            >
              <option value="first_fit">{t('form.searchFirst')}</option>
              <option value="best_fit">{t('form.searchBest')}</option>
            </select>
          </label>
          <label>
            {t('form.anneal')}
            <select
              value={options.anneal_seconds ?? 0}
              onChange={(e) =>
                setOptions({
                  ...options,
                  anneal_seconds: Number(e.target.value) || null,
                })
              }
            >
              <option value={0}>{t('form.annealOff')}</option>
              {[5, 15, 30].map((seconds) => (
                <option key={seconds} value={seconds}>
                  {t('form.seconds', { n: seconds })}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="checks">
          {(
            [
              ['form.k8', 'enforce_lifo'],
              ['form.k5', 'enforce_stacking'],
              ['form.k7', 'rebalance'],
              ['form.lateral', 'balance_lateral'],
            ] as [Key, keyof SolveOptions][]
          ).map(([key, field]) => (
            <Toggle
              key={field}
              label={t(key)}
              value={options[field] as boolean}
              onChange={(v) => setOptions({ ...options, [field]: v })}
            />
          ))}
        </div>
        <p className="hint">
          {t('form.constraintHint', { tab: t('tab.jobs') })}
        </p>
      </section>

      {error && <p className="error">{error}</p>}

      <button className="primary" onClick={submit} disabled={busy}>
        {busy
          ? options.anneal_seconds
            ? t('form.searching', { n: options.anneal_seconds })
            : t('form.solving')
          : t('form.submit')}
      </button>
    </div>
  )
}

function Gauge({ label, ratio, note }: { label: string; ratio: number; note: string }) {
  const over = ratio > 1
  return (
    <div className="gauge">
      <div className="gauge-head">
        <span>{label}</span>
        <strong className={over ? 'over' : undefined}>{(ratio * 100).toFixed(0)}%</strong>
      </div>
      <div className="gauge-track">
        <i
          style={{
            width: `${Math.min(ratio, 1) * 100}%`,
            background: over ? '#d03b3b' : '#2a78d6',
          }}
        />
      </div>
      <small>{note}</small>
    </div>
  )
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string
  value: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}
