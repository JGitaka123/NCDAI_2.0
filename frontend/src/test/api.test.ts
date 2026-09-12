import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, setSession } from '../api'
import type { Session } from '../types'

describe('Authenticated API requests', () => {
  beforeEach(() => { setSession(null); vi.unstubAllGlobals() })
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
