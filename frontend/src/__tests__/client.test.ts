import { describe, expect, it, vi } from 'vitest'

import { ApiError, api } from '../api/client'

describe('api client', () => {
  it('sends csrf and credentials on post', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await api.post('/api/killswitch', { paused: true })

    expect(fetchMock).toHaveBeenCalledWith('/api/killswitch', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-Atlas-CSRF': '1' },
      body: JSON.stringify({ paused: true }),
    })
  })

  it('throws normalized ApiError on non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Invalid password' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(api.post('/api/auth/login', { password: 'bad' })).rejects.toEqual(
      new ApiError(401, 'Invalid password'),
    )
  })
})
