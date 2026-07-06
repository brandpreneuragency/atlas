import type { ReactNode } from 'react'

import { isValidCron } from '../../lib/cron'

// --- client-side validators mirroring backend validate_graph rules -----------

const FILE_OPS = new Set(['move', 'copy', 'write', 'delete', 'mkdir'])

export function relPathOk(rel: unknown): boolean {
  if (typeof rel !== 'string' || rel.length === 0) return false
  if (rel.includes('\\') || rel.includes('\0')) return false
  if (rel.startsWith('/') || rel.startsWith('~')) return false
  if (rel.length >= 2 && rel[1] === ':') return false
  return !rel.split('/').some((part) => part === '..' || part.startsWith('~'))
}

type Validator = (config: Record<string, unknown>) => string | null

export const validators: Record<string, Validator> = {
  'trigger.cron': (c) =>
    isValidCron(String(c.expr ?? '')) ? null : 'invalid cron expression',
  'trigger.file_drop': (c) =>
    relPathOk(c.watch_path) ? null : 'watch path must stay inside ATLAS',
  'trigger.webhook': () => null,
  'trigger.manual': () => null,
  'hermes.task': (c) =>
    typeof c.prompt === 'string' && c.prompt.trim() ? null : 'prompt is required',
  'file.op': (c) => {
    if (!FILE_OPS.has(String(c.op))) return 'invalid op'
    if (!relPathOk(c.path)) return 'path must stay inside ATLAS'
    if (c.dest != null && c.dest !== '' && !relPathOk(c.dest))
      return 'dest must stay inside ATLAS'
    return null
  },
  'logic.condition': (c) =>
    typeof c.expression === 'string' && c.expression.trim()
      ? null
      : 'expression is required',
  'notify.telegram': (c) =>
    typeof c.message === 'string' && c.message.trim() ? null : 'message is required',
  'notify.email': (c) =>
    typeof c.subject === 'string' && c.subject.trim() &&
    typeof c.message === 'string' && c.message.trim()
      ? null
      : 'subject and message are required',
  'shell.command': (c) =>
    typeof c.command === 'string' && c.command.trim() ? null : 'command is required',
  'gate.approval': (c) =>
    typeof c.message === 'string' && c.message.trim() ? null : 'message is required',
}

// --- small typed field components (no form library) ---------------------------

const inputClass =
  'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm'

export function TextField({
  label,
  value,
  onChange,
  mono = false,
  extra,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  mono?: boolean
  extra?: ReactNode
}) {
  return (
    <label className="block text-sm text-slate-300">
      {label}
      <span className="flex items-center gap-2">
        <input
          className={`${inputClass} ${mono ? 'font-mono' : ''}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        {extra}
      </span>
    </label>
  )
}

export function TextArea({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="block text-sm text-slate-300">
      {label}
      <textarea
        className={`${inputClass} h-28 font-mono`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}

export function NumberField({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <label className="block text-sm text-slate-300">
      {label}
      <input
        type="number"
        className={inputClass}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  )
}

export function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
}) {
  return (
    <label className="block text-sm text-slate-300">
      {label}
      <select className={inputClass} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  )
}

export function CheckboxGroup({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (selected: string[]) => void
}) {
  return (
    <fieldset className="text-sm text-slate-300">
      <legend>{label}</legend>
      <div className="mt-1 flex gap-4">
        {options.map((opt) => (
          <label key={opt} className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={selected.includes(opt)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...selected, opt]
                    : selected.filter((s) => s !== opt),
                )
              }
            />
            {opt}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function InlineError({ message }: { message: string | null }) {
  if (!message) return null
  return <p className="text-xs text-red-300">{message}</p>
}
