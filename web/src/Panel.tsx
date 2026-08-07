import { stopColour } from './palette'
import { checked, isValid, violationList } from './types'
import type { Placement, Plan } from './types'

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function Verdict({ plan }: { plan: Plan }) {
  const metrics = plan.metrics
  if (!checked(metrics)) {
    return (
      <span className="badge badge-unknown" title="No validator has seen this plan">
        unchecked
      </span>
    )
  }
  if (isValid(metrics)) {
    return <span className="badge badge-good">all checks pass</span>
  }
  return (
    <span className="badge badge-bad" title={violationList(metrics).join(', ')}>
      {violationList(metrics).join('  ')}
    </span>
  )
}

export function Metrics({ plan }: { plan: Plan }) {
  const m = plan.metrics
  const inner = plan.vehicle.inner_mm
  const volume = (inner.length * inner.width * inner.height) / 1e9
  if (!m) return null
  return (
    <dl className="metrics">
      <div>
        <dt>volume</dt>
        <dd>{pct(m.volume_utilization)}</dd>
        <small>of {volume.toFixed(1)} m³</small>
      </div>
      <div>
        <dt>payload</dt>
        <dd>{pct(m.weight_utilization)}</dd>
        <small>of {(plan.vehicle.max_payload_g / 1e6).toFixed(1)} t</small>
      </div>
      <div>
        <dt>placed</dt>
        <dd>
          {m.placed}
          <span className="dim"> / {m.placed + m.unplaced}</span>
        </dd>
        <small>{m.unplaced} left behind</small>
      </div>
      <div>
        <dt>balance</dt>
        <dd>
          {m.cog_longitudinal_mm > 0 ? '+' : ''}
          {m.cog_longitudinal_mm} mm
        </dd>
        <small>
          {m.cog_lateral_mm > 0 ? '+' : ''}
          {m.cog_lateral_mm} mm sideways
        </small>
      </div>
    </dl>
  )
}

export function Legend({ stops }: { stops: number[] }) {
  if (stops.length < 2) return null
  return (
    <div className="legend">
      {stops.map((stop) => (
        <span key={stop}>
          <i style={{ background: stopColour(stop) }} />
          stop {stop}
        </span>
      ))}
    </div>
  )
}

export function Detail({
  placement,
  vehicle,
}: {
  placement: Placement | null
  vehicle: Plan['vehicle']
}) {
  if (!placement) {
    return <p className="hint">Click a box for its details.</p>
  }
  const doorDistance = vehicle.inner_mm.length - placement.pos_mm.x - placement.dims_mm.length
  return (
    <table className="detail">
      <tbody>
        <tr>
          <th>sku</th>
          <td>{placement.sku}</td>
        </tr>
        <tr>
          <th>load order</th>
          <td>#{placement.seq}</td>
        </tr>
        <tr>
          <th>stop</th>
          <td>
            <i className="swatch" style={{ background: stopColour(placement.stop) }} />
            {placement.stop}
          </td>
        </tr>
        <tr>
          <th>size</th>
          <td>
            {placement.dims_mm.length} × {placement.dims_mm.width} ×{' '}
            {placement.dims_mm.height} mm
          </td>
        </tr>
        <tr>
          <th>position</th>
          <td>
            x {placement.pos_mm.x}, y {placement.pos_mm.y}, z {placement.pos_mm.z}
          </td>
        </tr>
        <tr>
          <th>orientation</th>
          <td>{placement.orientation}</td>
        </tr>
        <tr>
          <th>from doors</th>
          <td>{doorDistance} mm</td>
        </tr>
      </tbody>
    </table>
  )
}
