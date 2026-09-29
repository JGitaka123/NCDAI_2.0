import { useEffect, useState } from 'react'
import { Smartphone } from 'lucide-react'

type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> }

// Offers "Install app" where the browser supports it; iOS users get the Share-menu hint.
export default function InstallApp() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null), [installed, setInstalled] = useState(false)
  const standalone = typeof window !== 'undefined' && window.matchMedia?.('(display-mode: standalone)').matches
  const ios = typeof navigator !== 'undefined' && /iphone|ipad|ipod/i.test(navigator.userAgent)
  useEffect(() => {
    const capture = (event: Event) => { event.preventDefault(); setPrompt(event as InstallPrompt) }
    const done = () => { setInstalled(true); setPrompt(null) }
    window.addEventListener('beforeinstallprompt', capture); window.addEventListener('appinstalled', done)
    return () => { window.removeEventListener('beforeinstallprompt', capture); window.removeEventListener('appinstalled', done) }
  }, [])
  if (standalone || installed) return null
  return <div className="install-card">
    <Smartphone size={18} aria-hidden="true" />
    <div><strong>NCDAI on your phone</strong>{prompt ? <p>Install the workspace as an app.</p> : ios ? <p>In Safari, tap Share, then Add to Home Screen.</p> : <p>Use your browser menu to install or add to home screen.</p>}
      <p><a href="/mobile/" target="_blank" rel="noopener">Offline quick consult</a></p></div>
    {prompt && <button type="button" className="button button-secondary button-small" onClick={async () => { await prompt.prompt(); const choice = await prompt.userChoice; if (choice.outcome === 'accepted') setInstalled(true); setPrompt(null) }}>Install</button>}
  </div>
}
