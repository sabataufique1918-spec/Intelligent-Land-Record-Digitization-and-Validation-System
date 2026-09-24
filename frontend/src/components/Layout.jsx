import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../api.js'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '▦', end: true },
  { to: '/upload', label: 'Upload Document', icon: '⇪' },
  { to: '/records', label: 'Uploaded Records', icon: '☰' },
  { to: '/validation', label: 'Validation Status', icon: '✓' },
  { to: '/conflicts', label: 'Conflicts', icon: '⚠' },
  { to: '/map', label: 'Cadastral Map', icon: '⌖' },
  { to: '/parcels', label: 'Parcel History', icon: '⧗' },
  { to: '/search', label: 'Record Search', icon: '⌕' },
]

export default function Layout() {
  const [health, setHealth] = useState({ state: 'checking' })
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth({ state: 'ok', database: h.database }))
      .catch(() => setHealth({ state: 'down' }))
  }, [])

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">LR</div>
          <div>
            <div className="brand-title">Land Record DVS</div>
            <div className="brand-sub">SIH26018 · v0.6</div>
          </div>
        </div>
        <nav>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          v0.6: upload, OCR, confidence scoring, optional Claude AI extraction, rule checks, conflict
          detection, cadastral map checks, parcel ownership history and officer review. Handwriting
          recognition is planned.
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="menu-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="Toggle menu">
            ☰
          </button>
          <div className="topbar-title">Intelligent Land Record Digitization &amp; Validation System</div>
          <div className={`health health-${health.state}`}>
            <span className="dot" />
            {health.state === 'checking' && 'Checking API…'}
            {health.state === 'ok' && `API online · ${health.database}`}
            {health.state === 'down' && 'API offline'}
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
