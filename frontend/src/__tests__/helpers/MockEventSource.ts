import { vi } from 'vitest'

type Listener = (ev: MessageEvent) => void

/**
 * Minimal EventSource mock for tests. Captures url/listeners and lets tests
 * dispatch named SSE frames (mimicking `event: <name>\ndata: <str>\n\n`).
 */
export class MockEventSource {
  static instances: MockEventSource[] = []
  static readonly READYSTATE_OPEN = 1

  readonly url: string
  readyState = 0
  private listeners: Record<string, Listener[]> = {}

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
    queueMicrotask(() => {
      this.readyState = MockEventSource.READYSTATE_OPEN
      ;(this.listeners['open'] ?? []).forEach((fn) => fn(new MessageEvent('open')))
    })
  }

  addEventListener(type: string, listener: Listener) {
    ;(this.listeners[type] ??= []).push(listener)
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((l) => l !== listener)
  }

  close() {
    this.readyState = 2
  }

  emit(type: string, data: string) {
    ;(this.listeners[type] ?? []).forEach((fn) => fn(new MessageEvent(type, { data })))
  }

  emitError() {
    ;(this.listeners['error'] ?? []).forEach((fn) => fn(new MessageEvent('error')))
  }
}

export function installMockEventSource() {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
  return MockEventSource
}