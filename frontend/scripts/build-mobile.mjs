// Packages the offline NCDAI Consult app (frontend/mobile) into public/mobile so
// Vite serves it at /mobile/. page.html is a body fragment (also publishable as
// a standalone page); this wraps it in a full document with PWA metadata.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(root, 'mobile'), target = join(root, 'public', 'mobile')
mkdirSync(target, { recursive: true })
for (const file of ['engine.js', 'evidence.js', 'app.js']) copyFileSync(join(source, file), join(target, file))
copyFileSync(join(root, 'public', 'brand', 'ncdai-logo.png'), join(target, 'ncdai-logo.png'))
const page = readFileSync(join(source, 'page.html'), 'utf8')
writeFileSync(join(target, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#FF5757">
<meta name="description" content="Offline consultant-level NCD decision support for clinicians: safety triage, targets and guideline-linked plans.">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="NCDAI Consult">
<link rel="manifest" href="/mobile/manifest.webmanifest">
<link rel="icon" type="image/png" href="/icons/icon-192.png">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
</head>
<body>
${page}
<script src="/mobile/register-sw.js"></script>
</body>
</html>
`)
writeFileSync(join(target, 'register-sw.js'), "if ('serviceWorker' in navigator) window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function () {}) })\n")
writeFileSync(join(target, 'manifest.webmanifest'), JSON.stringify({
  name: 'NCDAI Consult', short_name: 'NCDAI Consult', id: '/mobile/', start_url: '/mobile/', scope: '/mobile/', display: 'standalone',
  description: 'Offline consultant-level NCD decision support for clinicians.', background_color: '#fbf7f6', theme_color: '#FF5757', categories: ['medical', 'health'],
  icons: [{ src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }, { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    { src: '/icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }],
}, null, 2) + '\n')
console.log('Packaged NCDAI Consult into public/mobile')
