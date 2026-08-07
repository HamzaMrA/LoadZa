import { useMemo, useState } from 'react'

import { createJob, solveJob } from './api'
import type { Catalog, ItemType, JobLine, SolveOptions } from './api'
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
      if (usable.length === 0) throw new Error('add at least one item line')
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
        <h2>Vehicle</h2>
        <div className="row">
          <select value={vehicleCode} onChange={(e) => pickVehicle(e.target.value)}>
            {catalog.vehicles.map((v) => (
              <option key={v.code} value={v.code}>
                {v.name}
              </option>
            ))}
          </select>
          <input
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            aria-label="job id"
            placeholder="job id"
          />
        </div>
        {vehicle && (
          <p className="hint">
            {vehicle.inner_mm.length} × {vehicle.inner_mm.width} ×{' '}
            {vehicle.inner_mm.height} mm · {(capacity / 1e9).toFixed(1)} m³ ·{' '}
            {(vehicle.max_payload_g / 1e6).toFixed(1)} t payload
          </p>
        )}
      </section>

      <section>
        <h2>Cargo</h2>
        <table className="lines">
          <thead>
            <tr>
              <th>item</th>
              <th>qty</th>
              <th>stop</th>
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
                          {t.name} ({t.dims_mm.length}×{t.dims_mm.width}×
                          {t.dims_mm.height})
                        </option>
                      ))}
                    </select>
                    {type?.fragile && <span className="tag">fragile</span>}
                    {type?.this_side_up && <span className="tag">this side up</span>}
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
                      aria-label="remove line"
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
          + add line
        </button>

        <div className="gauges">
          <Gauge label="volume" ratio={volumeRatio} note={`${totals.count} items`} />
          <Gauge
            label="weight"
            ratio={weightRatio}
            note={`${(totals.weight / 1e6).toFixed(2)} t`}
          />
        </div>
        {(volumeRatio > 1 || weightRatio > 1) && (
          <p className="hint">
            More cargo than the vehicle holds. That is allowed — the solver packs
            what fits and reports the rest as left behind.
          </p>
        )}
      </section>

      <section>
        <h2>Solver</h2>
        <div className="row">
          <label>
            corner
            <select
              value={options.scorer}
              onChange={(e) => setOptions({ ...options, scorer: e.target.value })}
            >
              <option value="layer">layer (default)</option>
              <option value="dbl">deep-left-bottom</option>
              <option value="contact">max contact</option>
            </select>
          </label>
          <label>
            search
            <select
              value={options.search}
              onChange={(e) => setOptions({ ...options, search: e.target.value })}
            >
              <option value="first_fit">first fit</option>
              <option value="best_fit">best fit (slower)</option>
            </select>
          </label>
          <label>
            anneal
            <select
              value={options.anneal_seconds ?? 0}
              onChange={(e) =>
                setOptions({
                  ...options,
                  anneal_seconds: Number(e.target.value) || null,
                })
              }
            >
              <option value={0}>off</option>
              <option value={5}>5 s</option>
              <option value={15}>15 s</option>
              <option value={30}>30 s</option>
            </select>
          </label>
        </div>
        <div className="checks">
          <Toggle
            label="delivery reach (K8)"
            value={options.enforce_lifo}
            onChange={(v) => setOptions({ ...options, enforce_lifo: v })}
          />
          <Toggle
            label="stacking limits (K5)"
            value={options.enforce_stacking}
            onChange={(v) => setOptions({ ...options, enforce_stacking: v })}
          />
          <Toggle
            label="centre the load (K7)"
            value={options.rebalance}
            onChange={(v) => setOptions({ ...options, rebalance: v })}
          />
          <Toggle
            label="sideways balance (experimental)"
            value={options.balance_lateral}
            onChange={(v) => setOptions({ ...options, balance_lateral: v })}
          />
        </div>
        <p className="hint">
          Turn a constraint off and solve again to see what it costs — the plans
          stay side by side under <strong>Jobs</strong>.
        </p>
      </section>

      {error && <p className="error">{error}</p>}

      <button className="primary" onClick={submit} disabled={busy}>
        {busy
          ? options.anneal_seconds
            ? `searching for ${options.anneal_seconds} s…`
            : 'solving…'
          : 'Solve and view'}
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
