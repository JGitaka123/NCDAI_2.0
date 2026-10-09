import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, setSession } from '../api'
import type { Session } from '../types'

describe('Authenticated API requests', () => {
  beforeEach(() => { setSession(null); vi.unstubAllGlobals() })
  afterEach(() => { vi.useRealTimers() })
  it.each([200, 400])('keeps the deadline active while a %s response body is stalled', async status => {
    vi.useFakeTimers()
    const fetch = vi.fn().mockImplementation(async (_url, options) => ({
      ok: status === 200, status,
      json: () => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true })),
    }))
    vi.stubGlobal('fetch', fetch)
    const pending = expect(api('/encounters', { method: 'POST', body: {} })).rejects.toMatchObject({ status: 0, message: expect.stringContaining('outcome is unconfirmed') })
    await vi.advanceTimersByTimeAsync(45000)
    await pending
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('forwards cancellation after response headers arrive', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (_url, options) => ({
      ok: true, status: 200,
      json: () => new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true })
        controller.abort()
      }),
    })))
    await expect(api('/patients', { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
  })
  it('uses cookie credentials and attaches CSRF only to mutations', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'saved' }), { status: 200 })); vi.stubGlobal('fetch', fetch)
    setSession({ csrf_token: 'synthetic-csrf-token' } as Session)
    await api('/encounters', { method: 'POST', body: { patient_id: 'synthetic' } })
    expect(fetch).toHaveBeenCalledWith('/api/encounters', expect.objectContaining({ credentials: 'include', headers: expect.objectContaining({ 'X-CSRF-Token': 'synthetic-csrf-token' }) }))
    fetch.mockResolvedValueOnce(new Response('[]', { status: 200 })); await api('/patients')
    expect(fetch.mock.calls[1][1].headers).not.toHaveProperty('X-CSRF-Token')
  })
  it('removes the anti-CSRF token on session clearance', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 })); vi.stubGlobal('fetch', fetch)
    setSession({ csrf_token: 'old' } as Session); setSession(null); await api('/auth/login', { method: 'POST', body: { email: 'a@example.test' } })
    expect(fetch.mock.calls[0][1].headers).not.toHaveProperty('X-CSRF-Token')
  })
  it('treats a 409 as a stale-record conflict without retrying a clinical mutation', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"detail":"conflict"}', { status: 409 })); vi.stubGlobal('fetch', fetch)
    await expect(api('/encounters/id', { method: 'PATCH', body: {} })).rejects.toMatchObject({ status: 409, message: expect.stringContaining('Reload') })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('explains connectivity failure without claiming an offline save', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api('/encounters', { method: 'POST', body: {} })).rejects.toMatchObject({ status: 0, message: expect.stringContaining('No offline save') })
  })
  it('expires an active session on an unauthorized protected request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Session expired"}', { status: 401 })))
    const listener = vi.fn(); window.addEventListener('ncdai-session-expired', listener)
    await expect(api('/patients')).rejects.toMatchObject({ status: 401 }); expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener('ncdai-session-expired', listener)
  })
})
