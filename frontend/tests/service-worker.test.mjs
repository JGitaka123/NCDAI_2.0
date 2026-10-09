import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const source = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
function worker({ offline = false } = {}) {
  const handlers = {}, deleted = [], stored = [], lookedUp = []
  const cache = {
    addAll: async () => {},
    put: async request => stored.push(request.url),
    match: async request => { lookedUp.push(request); return undefined },
  }
  vm.runInNewContext(source, {
    self: { location: { origin: 'https://ncdai.example.test' }, addEventListener: (name, handler) => { handlers[name] = handler }, clients: { claim: async () => {} }, skipWaiting: async () => {} },
    caches: { keys: async () => ['ncdai-shell-v2', 'ncdai-shell-v3', 'unrelated-app'], delete: async name => deleted.push(name), open: async name => { assert.equal(name, 'ncdai-shell-v3'); return cache }, match: () => { throw new Error('Must not search other releases') } },
    fetch: async () => { if (offline) throw new Error('offline'); return { ok: true, type: 'basic', clone: () => ({}) } },
    URL, Response,
  })
  function dispatch(name, request) {
    const waits = []; let response
    handlers[name]({ request, waitUntil: promise => waits.push(promise), respondWith: promise => { response = promise } })
    return { get response() { return response }, complete: async () => { await response; await Promise.all(waits) } }
  }
  return { dispatch, deleted, stored, lookedUp }
}
test('activation deletes only obsolete NCDAI caches', async () => {
  const w = worker(); await w.dispatch('activate').complete()
  assert.deepEqual(w.deleted, ['ncdai-shell-v2'])
})
test('API, cross-origin, query and unrelated requests are not intercepted', () => {
  const w = worker()
  for (const path of ['/api/patients', '/other-app', '/?record=synthetic', 'https://other.example.test/']) {
    assert.equal(w.dispatch('fetch', { method: 'GET', url: new URL(path, 'https://ncdai.example.test').href }).response, undefined)
  }
})
test('online app caching is included in the event lifetime', async () => {
  const w = worker(), url = 'https://ncdai.example.test/mobile/engine.js'
  await w.dispatch('fetch', { method: 'GET', url }).complete()
  assert.deepEqual(w.stored, [url])
})
test('offline consultant navigation searches only the active release', async () => {
  const w = worker({ offline: true }), request = { method: 'GET', mode: 'navigate', url: 'https://ncdai.example.test/consultant' }
  await w.dispatch('fetch', request).complete()
  assert.deepEqual(w.lookedUp, [request, '/'])
})
