import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'
import './brand.css'
import './consultant.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
)

// Installable app shell; clinical API calls always go to the network.
if (import.meta.env.PROD && 'serviceWorker' in navigator) window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js').catch(() => {}) })
