import { useState } from 'react'

import { api } from '../../api/client'
import { describeCron, isValidCron } from '../../lib/cron'
import {
  CheckboxGroup,
  InlineError,
  NumberField,
  SelectField,
  TextArea,
  TextField,
  validators,
} from './fields'
import { NODE_META } from './nodeTypes'
import type { AtlasNode } from './useGraph'

/** Map a backend 422 detail ("node 'n2': ...") to the node ids it names. */
export function extractInvalidNodeIds(detail: string, nodeIds: string[]): string[] {
  return nodeIds.filter((id) => detail.includes(`node '${id}'`))
}

type TreeEntry = { name: string; is_dir: boolean }

function BrowseModal({
  onPick,
  onClose,
}: {
  onPick: (path: string) => void
  onClose: () => void
}) {
  const [path, setPath] = useState('')
  const [entries, setEntries] = useState<TreeEntry[]>([])

  const load = (p: string) => {
    setPath(p)
    api
      .get<{ entries: TreeEntry[] }>(`/api/files/tree?path=${encodeURIComponent(p)}`)
      .then((res) => setEntries(res.entries))
      .catch(() => setEntries([]))
  }

  useState(() => {
    load('')
    return undefined
  })

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
      <div
        role="dialog"
        aria-label="Browse files"
        className="max-h-[70vh] w-full max-w-md overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900 p-4"
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="font-mono text-xs text-slate-400">/{path}</span>
          <button type="button" className="text-sm text-slate-400" onClick={onClose}>
            ✕
          </button>
        </div>
        {path && (
          <button
            type="button"
            className="block w-full rounded px-2 py-1 text-left text-sm text-slate-300 hover:bg-slate-800"
            onClick={() => load(path.split('/').slice(0, -1).join('/'))}
          >
            ⬆ ..
          </button>
        )}
        {entries.map((entry) => {
          const full = path ? `${path}/${entry.name}` : entry.name
          return (
            <button
              key={entry.name}
              type="button"
              className="block w-full rounded px-2 py-1 text-left text-sm text-slate-300 hover:bg-slate-800"
              onClick={() => (entry.is_dir ? load(full) : (onPick(full), onClose()))}
            >
              {entry.is_dir ? '📁' : '📄'} {entry.name}
            </button>
          )
        })}
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            className="rounded-lg bg-cyan-500 px-3 py-1 text-sm font-medium text-slate-950"
            onClick={() => {
              onPick(path)
              onClose()
            }}
          >
            Use this folder
          </button>
        </div>
      </div>
    </div>
  )
}

function PathField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  const [browsing, setBrowsing] = useState(false)
  return (
    <>
      <TextField
        label={label}
        value={value}
        onChange={onChange}
        mono
        extra={
          <button
            type="button"
            className="mt-1 rounded-lg border border-slate-700 px-2 py-2 text-xs text-slate-300"
            onClick={() => setBrowsing(true)}
          >
            Browse
          </button>
        }
      />
      {browsing && <BrowseModal onPick={onChange} onClose={() => setBrowsing(false)} />}
    </>
  )
}

function TemplateHelper({ upstreamIds }: { upstreamIds: string[] }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950 p-2 text-xs text-slate-400">
      <p className="mb-1 text-slate-500">Template variables:</p>
      {upstreamIds.map((id) => (
        <code key={id} className="mr-2">
          {`{{${id}.*}}`}
        </code>
      ))}
    </div>
  )
}

type ConfigPanelProps = {
  node: AtlasNode
  upstreamIds: string[]
  shellAllowlist: string[]
  onChange: (nodeId: string, config: Record<string, unknown>) => void
  onClose: () => void
}

export function ConfigPanel({
  node,
  upstreamIds,
  shellAllowlist,
  onChange,
  onClose,
}: ConfigPanelProps) {
  const { nodeType, config } = node.data
  const meta = NODE_META[nodeType]
  const set = (key: string, value: unknown) =>
    onChange(node.id, { ...config, [key]: value })
  const str = (key: string, fallback = '') =>
    typeof config[key] === 'string' ? (config[key] as string) : fallback
  const num = (key: string, fallback: number) =>
    typeof config[key] === 'number' ? (config[key] as number) : fallback
  // trigger.cron renders its own inline cron error next to the field
  const error =
    nodeType === 'trigger.cron' ? null : validators[nodeType]?.(config) ?? null

  return (
    <aside
      data-testid="config-panel"
      className="w-80 shrink-0 space-y-3 overflow-y-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">
          {meta?.icon} {meta?.label ?? nodeType}{' '}
          <span className="font-mono text-xs text-slate-500">({node.id})</span>
        </h3>
        <button type="button" aria-label="Close panel" className="text-slate-400" onClick={onClose}>
          ✕
        </button>
      </div>

      {nodeType === 'trigger.cron' && (
        <>
          <TextField label="Cron expression" value={str('expr')} onChange={(v) => set('expr', v)} mono />
          {isValidCron(str('expr')) ? (
            <p className="text-xs text-cyan-200">{describeCron(str('expr'))}</p>
          ) : (
            <InlineError message="invalid cron expression" />
          )}
        </>
      )}

      {nodeType === 'trigger.file_drop' && (
        <>
          <PathField label="Watch path" value={str('watch_path')} onChange={(v) => set('watch_path', v)} />
          <TextField label="Glob" value={str('glob', '*')} onChange={(v) => set('glob', v)} mono />
          <NumberField label="Stability window (s)" value={num('stability_s', 5)} onChange={(v) => set('stability_s', v)} />
        </>
      )}

      {nodeType === 'trigger.webhook' && (
        <TextField label="Secret" value={str('secret')} onChange={(v) => set('secret', v)} mono />
      )}

      {nodeType === 'trigger.manual' && (
        <p className="text-xs text-slate-400">No configuration — run from the Run panel.</p>
      )}

      {nodeType === 'hermes.task' && (
        <>
          <TextArea label="Prompt" value={str('prompt')} onChange={(v) => set('prompt', v)} />
          <TemplateHelper upstreamIds={upstreamIds} />
          <NumberField label="Timeout (s)" value={num('timeout_s', 900)} onChange={(v) => set('timeout_s', v)} />
          <NumberField label="Retries" value={num('retries', 0)} onChange={(v) => set('retries', v)} />
          <TextField label="Session key (optional)" value={str('session_key')} onChange={(v) => set('session_key', v || null)} />
        </>
      )}

      {nodeType === 'file.op' && (
        <>
          <SelectField label="Operation" value={str('op', 'write')} options={['write', 'move', 'copy', 'delete', 'mkdir']} onChange={(v) => set('op', v)} />
          <PathField label="Path" value={str('path')} onChange={(v) => set('path', v)} />
          {(str('op') === 'move' || str('op') === 'copy') && (
            <PathField label="Destination" value={str('dest')} onChange={(v) => set('dest', v)} />
          )}
          {str('op', 'write') === 'write' && (
            <>
              <TextArea label="Content" value={str('content')} onChange={(v) => set('content', v)} />
              <TemplateHelper upstreamIds={upstreamIds} />
            </>
          )}
        </>
      )}

      {nodeType === 'logic.condition' && (
        <>
          <TextField label="Expression" value={str('expression')} onChange={(v) => set('expression', v)} mono />
          <p className="text-xs text-slate-500">
            Comparisons only, e.g. <code>{"'PONG' in n2.output_text"}</code>
          </p>
        </>
      )}

      {(nodeType === 'notify.telegram' || nodeType === 'notify.email') && (
        <>
          {nodeType === 'notify.email' && (
            <TextField label="Subject" value={str('subject')} onChange={(v) => set('subject', v)} />
          )}
          <TextArea label="Message" value={str('message')} onChange={(v) => set('message', v)} />
          <TemplateHelper upstreamIds={upstreamIds} />
        </>
      )}

      {nodeType === 'shell.command' && (
        <>
          <TextField label="Command" value={str('command')} onChange={(v) => set('command', v)} mono />
          <div className="text-xs text-slate-500">
            <p>Allowed prefixes:</p>
            {shellAllowlist.length ? (
              shellAllowlist.map((prefix) => (
                <code key={prefix} className="mr-2">
                  {prefix}
                </code>
              ))
            ) : (
              <p>(allowlist empty — configure in Settings)</p>
            )}
          </div>
          <PathField label="Working dir (optional)" value={str('cwd')} onChange={(v) => set('cwd', v)} />
          <NumberField label="Timeout (s)" value={num('timeout_s', 60)} onChange={(v) => set('timeout_s', v)} />
        </>
      )}

      {nodeType === 'gate.approval' && (
        <>
          <TextField label="Message" value={str('message')} onChange={(v) => set('message', v)} />
          <NumberField label="Timeout (h)" value={num('timeout_h', 24)} onChange={(v) => set('timeout_h', v)} />
          <CheckboxGroup
            label="Notify"
            options={['telegram', 'email']}
            selected={Array.isArray(config.notify) ? (config.notify as string[]) : []}
            onChange={(sel) => set('notify', sel)}
          />
        </>
      )}

      <InlineError message={error} />
    </aside>
  )
}
