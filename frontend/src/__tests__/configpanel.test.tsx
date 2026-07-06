import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ConfigPanel, extractInvalidNodeIds } from '../components/flow/ConfigPanel'
import { validators } from '../components/flow/fields'
import type { AtlasNode } from '../components/flow/useGraph'

function makeNode(nodeType: string, config: Record<string, unknown> = {}): AtlasNode {
  return {
    id: 'n2',
    type: 'atlas',
    position: { x: 0, y: 0 },
    data: { nodeType, config },
  }
}

function renderPanel(node: AtlasNode, onChange = vi.fn()) {
  render(
    <ConfigPanel
      node={node}
      upstreamIds={['trigger', 'n1']}
      shellAllowlist={['git ', 'python ']}
      onChange={onChange}
      onClose={vi.fn()}
    />,
  )
  return onChange
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('validators (mirror backend validate_graph)', () => {
  it('flags bad cron and empty prompt', () => {
    expect(validators['trigger.cron']({ expr: 'not a cron' })).toContain('cron')
    expect(validators['trigger.cron']({ expr: '0 7 * * *' })).toBeNull()
    expect(validators['hermes.task']({ prompt: '' })).toContain('prompt')
    expect(validators['hermes.task']({ prompt: 'hi' })).toBeNull()
  })

  it('flags jail-escaping file paths', () => {
    expect(validators['file.op']({ op: 'write', path: '../../etc/passwd' })).toContain('path')
    expect(validators['file.op']({ op: 'write', path: '04_reports/x.md' })).toBeNull()
    expect(validators['file.op']({ op: 'bogus', path: 'x.md' })).toContain('op')
  })
})

describe('ConfigPanel', () => {
  it('cron form shows live human-readable description', async () => {
    renderPanel(makeNode('trigger.cron', { expr: '*/30 * * * *' }))
    expect(screen.getByLabelText(/cron expression/i)).toHaveValue('*/30 * * * *')
    expect(screen.getByText('every 30 min')).toBeInTheDocument()
  })

  it('cron form shows inline error for invalid expr', () => {
    renderPanel(makeNode('trigger.cron', { expr: 'garbage' }))
    expect(screen.getByText(/invalid cron/i)).toBeInTheDocument()
  })

  it('hermes form has prompt textarea + template variable helper', () => {
    renderPanel(makeNode('hermes.task', { prompt: 'Do it' }))
    expect(screen.getByLabelText(/prompt/i)).toHaveValue('Do it')
    expect(screen.getByText(/\{\{trigger\./)).toBeInTheDocument()
    expect(screen.getByText(/\{\{n1\./)).toBeInTheDocument()
  })

  it('hermes form shows inline error for empty prompt', () => {
    renderPanel(makeNode('hermes.task', { prompt: '' }))
    expect(screen.getByText(/prompt is required/i)).toBeInTheDocument()
  })

  it('file.op form has path input with a browse button', () => {
    renderPanel(makeNode('file.op', { op: 'write', path: 'a.md' }))
    expect(screen.getByLabelText(/path/i)).toHaveValue('a.md')
    expect(screen.getByRole('button', { name: /browse/i })).toBeInTheDocument()
  })

  it('condition form has an expression input', () => {
    renderPanel(makeNode('logic.condition', { expression: "'x' in n1.output_text" }))
    expect(screen.getByLabelText(/expression/i)).toHaveValue("'x' in n1.output_text")
  })

  it('shell form shows the allowlist', () => {
    renderPanel(makeNode('shell.command', { command: 'git status' }))
    expect(screen.getByLabelText(/command/i)).toHaveValue('git status')
    expect(screen.getByText('git')).toBeInTheDocument()
    expect(screen.getByText('python')).toBeInTheDocument()
  })

  it('gate form has message + notify checkboxes', () => {
    renderPanel(makeNode('gate.approval', { message: 'Go?', notify: ['telegram'] }))
    expect(screen.getByLabelText(/message/i)).toHaveValue('Go?')
    expect(screen.getByRole('checkbox', { name: /telegram/i })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /email/i })).not.toBeChecked()
  })

  it('edits call onChange with the updated config', async () => {
    const user = userEvent.setup()
    const onChange = renderPanel(makeNode('hermes.task', { prompt: 'a' }))
    await user.type(screen.getByLabelText(/prompt/i), 'b')
    expect(onChange).toHaveBeenLastCalledWith('n2', expect.objectContaining({ prompt: 'ab' }))
  })
})

describe('extractInvalidNodeIds', () => {
  it('maps a 422 detail to the named node ids', () => {
    const detail =
      "node 'n2': missing config field(s) ['prompt'] for hermes.task; edge 'e1': target references missing node 'zz'"
    expect(extractInvalidNodeIds(detail, ['n1', 'n2', 'n3'])).toEqual(['n2'])
  })
})
