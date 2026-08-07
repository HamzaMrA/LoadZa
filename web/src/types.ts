/** The plan document produced by core.io.plan_to_dict. */

export interface Dims {
  length: number
  width: number
  height: number
}

export interface Vehicle {
  code: string
  name: string
  inner_mm: Dims
  max_payload_g: number
  access: string
  cog_lateral_tol_mm: number
  cog_long_tol_ratio: number
  min_support_ratio: number
}

export interface Placement {
  seq: number
  item_uid: number
  sku: string
  pos_mm: { x: number; y: number; z: number }
  dims_mm: Dims
  orientation: string
  stop: number
}

export interface Metrics {
  volume_utilization: number
  weight_utilization: number
  placed: number
  unplaced: number
  cog_lateral_mm: number
  cog_longitudinal_mm: number
  solve_ms: number
  violations: Record<string, number>
}

export interface Unplaced {
  item_uid: number
  sku: string
  reason: string
}

export interface Plan {
  plan_id: string
  job_id: string
  algorithm: string
  vehicle: Vehicle
  metrics: Metrics | null
  placements: Placement[]
  unplaced: Unplaced[]
}

/**
 * Whether a validator has looked at this plan.
 *
 * The solver leaves the violation map empty because it is not entitled to
 * grade itself, so an empty map means "unchecked", never "clean". The badge
 * has to say so -- showing a green tick for a plan nobody audited is exactly
 * the failure this project spent a phase avoiding.
 */
export function checked(metrics: Metrics | null): boolean {
  return !!metrics && Object.keys(metrics.violations ?? {}).length > 0
}

export function isValid(metrics: Metrics | null): boolean {
  return (
    checked(metrics) &&
    Object.values(metrics!.violations).every((count) => count === 0)
  )
}

export function violationList(metrics: Metrics | null): string[] {
  if (!metrics) return []
  return Object.entries(metrics.violations ?? {})
    .filter(([, count]) => count > 0)
    .map(([name, count]) => `${name} ×${count}`)
}
