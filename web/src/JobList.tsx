import { useEffect, useState } from 'react'

import { getJobs, getPlansFor } from './api'
import type { JobSummary, PlanSummary } from './api'

function pct(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

function verdict(violations: Record<string, number>): string {
  const keys = Object.keys(violations ?? {})
  if (keys.length === 0) return 'unchecked'
  const failed = keys.filter((k) => violations[k] > 0)
  return failed.length === 0 ? 'clean' : failed.map((k) => `${k}×${violations[k]}`).join(' ')
}

export default function JobList({ onOpen }: { onOpen: (planId: string) => void }) {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [plans, setPlans] = useState<Record<string, PlanSummary[]>>({})
  const [open, setOpen] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getJobs()
      .then(setJobs)
      .catch((problem: Error) => setError(problem.message))
  }, [])

  function expand(jobId: string) {
    setOpen(open === jobId ? null : jobId)
    if (!plans[jobId]) {
      getPlansFor(jobId)
        .then((rows) => setPlans((current) => ({ ...current, [jobId]: rows })))
        .catch((problem: Error) => setError(problem.message))
    }
  }

  if (error) return <p className="error">{error}</p>
  if (jobs.length === 0) {
    return <p className="hint">No jobs yet. Build one under “New job”.</p>
  }

  return (
    <div className="jobs">
      {jobs.map((job) => (
        <div key={job.job_id} className="job">
          <button className="job-head" onClick={() => expand(job.job_id)}>
            <span className="job-id">{job.job_id}</span>
            <span className="dim">
              {job.vehicle_code} · {job.items} items
            </span>
            <span className="dim">{open === job.job_id ? '▾' : '▸'}</span>
          </button>

          {open === job.job_id && (
            <table className="plans">
              <thead>
                <tr>
                  <th>algorithm</th>
                  <th>volume</th>
                  <th>payload</th>
                  <th>placed</th>
                  <th>checks</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(plans[job.job_id] ?? []).map((plan) => (
                  <tr key={plan.plan_id}>
                    <td>
                      <code>{plan.algorithm}</code>
                    </td>
                    <td className="num">{pct(plan.volume_utilization)}</td>
                    <td className="num">{pct(plan.weight_utilization)}</td>
                    <td className="num">
                      {plan.placed}
                      <span className="dim">/{(plan.placed ?? 0) + (plan.unplaced ?? 0)}</span>
                    </td>
                    <td>{verdict(plan.violations)}</td>
                    <td>
                      <button className="ghost" onClick={() => onOpen(plan.plan_id)}>
                        view
                      </button>
                    </td>
                  </tr>
                ))}
                {(plans[job.job_id] ?? []).length === 0 && (
                  <tr>
                    <td colSpan={6} className="hint">
                      no plans for this job yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  )
}
