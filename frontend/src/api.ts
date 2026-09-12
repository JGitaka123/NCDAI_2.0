import type { Session } from './types'

let csrfToken = ''
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status; this.name = 'ApiError' }
}

export function setSession(session: Session | null) { csrfToken = session?.csrf_token ?? '' }

function errorText(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.filter(x => x !== 'body').join(' → ') || 'Request'}: ${item.msg || 'Invalid value'}`).join('; ')
  return 'The request could not be completed. Try again.'
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const controller = new AbortController()
  const forwardAbort = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) forwardAbort()
  else options.signal?.addEventListener('abort', forwardAbort, { once: true })
  const timeout = window.setTimeout(() => controller.abort(new DOMException('Request deadline exceeded', 'TimeoutError')), 45000)
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: 'include',
      headers: { Accept: 'application/json', ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' && csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    })
  } catch (error) {
    if (options.signal?.aborted) throw new DOMException('Request cancelled', 'AbortError')
    const timedOut = controller.signal.aborted && controller.signal.reason?.name === 'TimeoutError'
    throw new ApiError(0, `${timedOut ? 'The clinical service did not respond in time.' : 'The clinical service is unreachable.'} No offline save is available.${method === 'GET' ? ' Check the connection and try again.' : ' The request outcome is unconfirmed. Reload saved records before repeating this action.'}`)
  } finally {
    window.clearTimeout(timeout)
    options.signal?.removeEventListener('abort', forwardAbort)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/session') window.dispatchEvent(new CustomEvent('ncdai-session-expired'))
    throw new ApiError(response.status, response.status === 409 ? 'This record changed in another session. Reload the latest saved record before continuing. Your unsaved changes have not been applied.' : errorText(body.detail))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function message(error: unknown): string { return error instanceof Error ? error.message : 'An unexpected error occurred. Please try again.' }
