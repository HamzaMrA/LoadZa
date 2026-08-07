/** Calls to the FastAPI service. Same origin in production, proxied in dev. */

import type { Plan, Vehicle } from './types'

export interface ItemType {
  sku: string
  name: string
  dims_mm: { length: number; width: number; height: number }
  weight_g: number
  fragile: boolean
  max_stack_weight_g: number | null
  this_side_up: boolean
}

export interface Catalog {
  vehicles: Vehicle[]
  item_types: ItemType[]
}

export interface JobSummary {
  job_id: string
  vehicle_code: string
  items: number
  created_at: string
  note: string | null
}

export interface PlanSummary {
  plan_id: string
  job_id?: string | null
  algorithm: string
  created_at?: string | null
  volume_utilization: number | null
  weight_utilization: number | null
  placed: number | null
  unplaced: number | null
  cog_lateral_mm: number | null
  cog_longitudinal_mm: number | null
  solve_ms: number | null
  violations: Record<string, number>
}

export interface JobLine {
  sku: string
  qty: number
  stop: number
}

export interface SolveOptions {
  scorer: string
  search: string
  anneal_seconds: number | null
  enforce_lifo: boolean
  enforce_stacking: boolean
  rebalance: boolean
  balance_lateral: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { 'content-type': 'application/json' } : undefined,
  })
  if (!response.ok) {
    // FastAPI puts the reason in `detail`; surfacing it beats "500".
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail)
    } catch {
      /* not json */
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const getHealth = () => request<{ status: string }>('/health')
export const getCatalog = () => request<Catalog>('/catalog')
export const getJobs = () => request<JobSummary[]>('/jobs')
export const getPlan = (planId: string) =>
  request<Plan>(`/plans/${encodeURIComponent(planId)}`)
export const getPlansFor = (jobId: string) =>
  request<PlanSummary[]>(`/jobs/${encodeURIComponent(jobId)}/plans`)

export function createJob(
  jobId: string,
  vehicleCode: string,
  lines: JobLine[],
  note?: string,
) {
  return request<JobSummary>('/jobs', {
    method: 'POST',
    body: JSON.stringify({
      job_id: jobId,
      vehicle: { code: vehicleCode },
      items: lines.map((line) => ({ sku: line.sku, qty: line.qty, stop: line.stop })),
      note,
    }),
  })
}

export function solveJob(jobId: string, options: SolveOptions) {
  return request<PlanSummary>(`/jobs/${encodeURIComponent(jobId)}/solve`, {
    method: 'POST',
    body: JSON.stringify({
      scorer: options.scorer,
      search: options.search,
      enforce_lifo: options.enforce_lifo,
      enforce_stacking: options.enforce_stacking,
      rebalance: options.rebalance,
      balance_lateral: options.balance_lateral,
      anneal_seconds: options.anneal_seconds,
    }),
  })
}
