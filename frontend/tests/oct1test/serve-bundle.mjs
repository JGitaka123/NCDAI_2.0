// Serves the deployed frontend bundle and proxies /api to the local backend,
// so the real PWA runs against a real NCDAI API on the Oct1Test database.
import { createServer, request as httpRequest } from 'node:http'
import { readFile } from 'node:fs/promises'
import { join, extname } from 'node:path'
const ROOT = process.argv[2], PORT = Number(process.argv[3] || 8902), API = Number(process.argv[4] || 8010)
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.png': 'image/png', '.webmanifest': 'application/manifest+json; charset=utf-8', '.json': 'application/json' }
createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1')
  if (url.pathname.startsWith('/api/')) {
    const proxy = httpRequest({ host: '127.0.0.1', port: API, path: req.url, method: req.method, headers: req.headers }, upstream => {
      res.writeHead(upstream.statusCode, upstream.headers); upstream.pipe(res)
    })
    proxy.on('error', e => { res.writeHead(502); res.end(String(e)) })
    return req.pipe(proxy)
  }
  let p = decodeURIComponent(url.pathname)
  if (p === '/mobile' || p === '/mobile/') p = '/mobile/index.html'
  try { const body = await readFile(join(ROOT, p)); res.writeHead(200, { 'content-type': TYPES[extname(join(ROOT, p))] || 'application/octet-stream' }); return res.end(body) } catch {}
  try { const body = await readFile(join(ROOT, 'index.html')); res.writeHead(200, { 'content-type': TYPES['.html'] }); return res.end(body) }
  catch { res.writeHead(404); res.end('not found') }
}).listen(PORT, '127.0.0.1', () => console.log('pwa host on ' + PORT + ' -> api ' + API))
