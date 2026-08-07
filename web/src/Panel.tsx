import { useT } from './i18n'
import { stopColour } from './palette'
import { checked, isValid, violationList } from './types'
import type { Placement, Plan } from './types'

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${value}`
}

export function Verdict({ plan }: { plan: Plan }) {
  const { t } = useT()
  const metrics = plan.metrics
  if (!checked(metrics)) {
    return (
      <span className="badge badge-unknown" title={t('verdict.uncheckedHint')}>
        {t('verdict.unchecked')}
      </span>
    )
  }
  if (isValid(metrics)) {
    return <span className="badge badge-good">{t('verdict.clean')}</span>
  }
  return (
    <span className="badge badge-bad" title={violationList(metrics).join(', ')}>
      {violationList(metrics).join('  ')}
    </span>
  )
}

export function Metrics({ plan }: { plan: Plan }) {
  const { t } = useT()
  const m = plan.metrics
  const inner = plan.vehicle.inner_mm
  const volume = (inner.length * inner.width * inner.height) / 1e9
  if (!m) return null
  return (
    <dl className="metrics">
      <div>
        <dt>{t('metric.volume')}</dt>
        <dd>{pct(m.volume_utilization)}</dd>
        <small>{t('metric.ofVolume', { v: volume.toFixed(1) })}</small>
      </div>
      <div>
        <dt>{t('metric.payload')}</dt>
        <dd>{pct(m.weight_utilization)}</dd>
        <small>
          {t('metric.ofPayload', { t: (plan.vehicle.max_payload_g / 1e6).toFixed(1) })}
        </small>
      </div>
      <div>
        <dt>{t('metric.placed')}</dt>
        <dd>
          {m.placed}
          <span className="dim"> / {m.placed + m.unplaced}</span>
        </dd>
        <small>{t('metric.leftBehind', { n: m.unplaced })}</small>
      </div>
      <div>
        <dt>{t('metric.balance')}</dt>
        <dd>{signed(m.cog_longitudinal_mm)} mm</dd>
        <small>{t('metric.sideways', { n: signed(m.cog_lateral_mm) })}</small>
      </div>
    </dl>
  )
}

export function Legend({ stops }: { stops: number[] }) {
  const { t } = useT()
  if (stops.length < 2) return null
  return (
    <div className="legend">
      {stops.map((stop) => (
        <span key={stop}>
          <i style={{ background: stopColour(stop) }} />
          {t('common.stop', { n: stop })}
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
  const { t } = useT()
  if (!placement) {
    return <p className="hint">{t('detail.prompt')}</p>
  }
  const doorDistance = vehicle.inner_mm.length - placement.pos_mm.x - placement.dims_mm.length
  return (
    <table className="detail">
      <tbody>
        <tr>
          <th>{t('detail.sku')}</th>
          <td>{placement.sku}</td>
        </tr>
        <tr>
          <th>{t('detail.order')}</th>
          <td>#{placement.seq}</td>
        </tr>
        <tr>
          <th>{t('detail.stop')}</th>
          <td>
            <i className="swatch" style={{ background: stopColour(placement.stop) }} />
            {placement.stop}
          </td>
        </tr>
        <tr>
          <th>{t('detail.size')}</th>
          <td>
            {placement.dims_mm.length} × {placement.dims_mm.width} ×{' '}
            {placement.dims_mm.height} mm
          </td>
        </tr>
        <tr>
          <th>{t('detail.position')}</th>
          <td>
            x {placement.pos_mm.x}, y {placement.pos_mm.y}, z {placement.pos_mm.z}
          </td>
        </tr>
        <tr>
          <th>{t('detail.orientation')}</th>
          <td>{placement.orientation}</td>
        </tr>
        <tr>
          <th>{t('detail.fromDoors')}</th>
          <td>{doorDistance} mm</td>
        </tr>
      </tbody>
    </table>
  )
}
