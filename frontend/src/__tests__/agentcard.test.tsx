import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { fixtureAgent, fixtureAgentUnreachable } from '../api/fixtures'
import { AgentCard } from '../components/cards/AgentCard'

describe('AgentCard', () => {
  afterEach(() => {
    cleanup()
  })

  it('shows name, green status dot, model and active runs when ok', () => {
    render(<AgentCard agent={fixtureAgent} />)

    expect(screen.getByText('Hermes')).toBeInTheDocument()
    const dot = screen.getByLabelText('status-ok')
    expect(dot.className).toContain('bg-emerald-400')
    expect(screen.getByTestId('agent-status')).toHaveTextContent('ok')
    expect(screen.getByTestId('agent-model')).toHaveTextContent('gpt-5.5')
    expect(screen.getByTestId('agent-runs')).toHaveTextContent('1')
  })

  it('shows red status dot and placeholder model when unreachable', () => {
    render(<AgentCard agent={fixtureAgentUnreachable} />)

    const dot = screen.getByLabelText('status-unreachable')
    expect(dot.className).toContain('bg-red-500')
    expect(screen.getByTestId('agent-status')).toHaveTextContent('unreachable')
    expect(screen.getByTestId('agent-model')).toHaveTextContent('—')
    expect(screen.getByTestId('agent-runs')).toHaveTextContent('0')
  })
})
