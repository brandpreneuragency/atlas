import { useCallback, useEffect, useState } from 'react'

import { api } from '../api/client'
import type { CronJob } from '../components/cards/CronJobRow'
import { CronJobRow } from '../components/cards/CronJobRow'
import { ConfirmDialog } from '../components/files/ConfirmDialog'
import { describeCron, isValidCron } from '../lib/cron'

function JobModal({
  job,
  onClose,
  onSaved,
}: {
  job: CronJob | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(job?.name ?? '')
  const [prompt, setPrompt] = useState(job?.prompt ?? '')
  const [expr, setExpr] = useState(job?.schedule?.expr ?? '*/30 * * * *')
  const [skills, setSkills] = useState((job?.skills ?? []).join(', '))
  const [error, setError] = useState<string | null>(null)
  const valid = isValidCron(expr)

  const save = async () => {
    setError(null)
    const payload = {
      name,
      prompt,
      schedule: { kind: 'cron', expr },
      skills: skills
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    }
    try {
      if (job) await api.put(`/api/hermes/cron/${job.id}`, payload)
      else await api.post('/api/hermes/cron', payload)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save failed')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
      <div
        role="dialog"
        aria-label={job ? 'Edit cron job' : 'New cron job'}
        className="w-full max-w-lg space-y-3 rounded-2xl border border-slate-700 bg-slate-900 p-5"
      >
        <h2 className="text-lg font-semibold">
          {job ? 'Edit cron job' : 'New cron job'}
        </h2>
        <label className="block text-sm text-slate-300">
          Name
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="block text-sm text-slate-300">
          Prompt
          <textarea
            className="mt-1 h-28 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </label>
        <label className="block text-sm text-slate-300">
          Cron expression
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
          />
        </label>
        {valid ? (
          <p className="text-xs text-cyan-200">{describeCron(expr)}</p>
        ) : (
          <p className="text-xs text-red-300">invalid cron expression</p>
        )}
        <label className="block text-sm text-slate-300">
          Skills (comma-separated)
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            value={skills}
            onChange={(e) => setSkills(e.target.value)}
          />
        </label>
        {error && <p className="text-xs text-red-300">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!valid || !name}
            className="rounded-lg bg-cyan-500 px-3 py-1.5 text-sm font-medium text-slate-950 disabled:opacity-40"
            onClick={() => void save()}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}

export function Automation() {
  const [jobs, setJobs] = useState<CronJob[]>([])
  const [editing, setEditing] = useState<CronJob | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<CronJob | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .get<CronJob[]>('/api/hermes/cron')
      .then(setJobs)
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'load failed'),
      )
  }, [])

  useEffect(load, [load])

  const action = async (id: string, verb: 'pause' | 'resume' | 'trigger') => {
    // optimistic flip for pause/resume
    if (verb !== 'trigger') {
      setJobs((prev) =>
        prev.map((j) =>
          j.id === id
            ? { ...j, enabled: verb === 'resume', state: verb === 'resume' ? 'scheduled' : 'paused' }
            : j,
        ),
      )
    }
    try {
      await api.post(`/api/hermes/cron/${id}/${verb}`, {})
    } catch (err) {
      setError(err instanceof Error ? err.message : `${verb} failed`)
    } finally {
      load()
    }
  }

  return (
    <div className="space-y-8" data-testid="automation-page">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Automation</h1>
        <button
          type="button"
          className="rounded-lg bg-cyan-500 px-3 py-1.5 text-sm font-medium text-slate-950"
          onClick={() => setCreating(true)}
        >
          New cron job
        </button>
      </div>
      {error && <p className="text-sm text-red-300">{error}</p>}

      <section>
        <h2 className="mb-3 text-lg font-medium text-slate-200">Workflows</h2>
        <div className="rounded-2xl border border-dashed border-slate-800 p-8 text-center text-slate-500">
          No workflows yet — coming in Phase 6
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium text-slate-200">
          Hermes cron jobs
        </h2>
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Schedule</th>
                <th className="px-4 py-2">State</th>
                <th className="px-4 py-2">Next run</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-slate-400">
                    No Hermes cron jobs.
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <CronJobRow
                    key={job.id}
                    job={job}
                    onAction={(id, verb) => void action(id, verb)}
                    onEdit={setEditing}
                    onDelete={setDeleting}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {(editing || creating) && (
        <JobModal
          job={editing}
          onClose={() => {
            setEditing(null)
            setCreating(false)
          }}
          onSaved={() => {
            setEditing(null)
            setCreating(false)
            load()
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title={`Delete cron job '${deleting.name}'?`}
          paths={[deleting.name]}
          confirmLabel="Confirm delete"
          onConfirm={() => {
            void (async () => {
              try {
                await api.delete(`/api/hermes/cron/${deleting.id}`)
              } finally {
                setDeleting(null)
                load()
              }
            })()
          }}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  )
}
