export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
    this.name = 'ApiError'
  }
}

type JsonBody = Record<string, unknown>

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : response.statusText
  } catch {
    return response.statusText
  }
}

// 401 from any API call (except the login attempt itself) → back to Login.
let onUnauthorized: () => void = () => {
  if (window.location.pathname !== '/login') {
    window.location.assign('/login')
  }
}

export function setOnUnauthorized(handler: () => void): void {
  onUnauthorized = handler
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...init })
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/auth/login') {
      onUnauthorized()
    }
    throw new ApiError(response.status, await parseError(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'GET' })
  },
  post<T = void>(path: string, body: JsonBody): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-Atlas-CSRF': '1' },
      body: JSON.stringify(body),
    })
  },
  put<T = void>(path: string, body: JsonBody): Promise<T> {
    return request<T>(path, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-Atlas-CSRF': '1' },
      body: JSON.stringify(body),
    })
  },
  delete<T = void>(path: string): Promise<T> {
    return request<T>(path, {
      method: 'DELETE',
      credentials: 'include',
      headers: { 'X-Atlas-CSRF': '1' },
    })
  },
  postForm<T = void>(path: string, form: FormData): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Atlas-CSRF': '1' },
      body: form,
    })
  },
}
