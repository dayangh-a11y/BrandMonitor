import { useCallback, useMemo, useState } from 'react'
import { ApiStatus } from './components/ApiStatus'
import { HorseSearchBox } from './components/HorseSearchBox'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { DashboardPage } from './pages/DashboardPage'
import { HorsesPage } from './pages/HorsesPage'
import { PredictionsPage } from './pages/PredictionsPage'
import { RacesPage } from './pages/RacesPage'
import { SystemStatusTab } from './tabs/SystemStatusTab'
import { NAV_ITEMS, type NavId } from './nav'
import './styles.css'

function persianDate(now = new Date()): string {
  try {
    return new Intl.DateTimeFormat('fa-IR', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(now)
  } catch {
    return now.toLocaleDateString('fa-IR')
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavId>('dashboard')
  const [focusHorseId, setFocusHorseId] = useState<number | null>(null)
  const today = useMemo(() => persianDate(), [])

  const openHorse = useCallback((horseId: number) => {
    setFocusHorseId(horseId)
    setActiveTab('horses')
  }, [])

  return (
    <div className="app-shell" dir="rtl" lang="fa">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <div className="logo-mark" aria-hidden>
            HR
          </div>
          <div>
            <div className="brand-name">Horse Racing AI</div>
            <div className="brand-tagline">تحلیل حرفه‌ای مسابقات</div>
          </div>
        </div>

        <nav className="sidebar__nav" aria-label="ناوبری اصلی">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeTab === item.id ? 'nav-btn active' : 'nav-btn'}
              onClick={() => setActiveTab(item.id)}
            >
              <span className="nav-btn__en">{item.label}</span>
              <span className="nav-btn__fa">{item.short}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar__foot">
          <ApiStatus />
          <div className="sidebar__date">{today}</div>
        </div>
      </aside>

      <div className="app-body">
        <header className="topbar">
          <div className="topbar__title">
            <strong>Horse Racing AI</strong>
            <span className="muted">MVP Dashboard</span>
          </div>
          <div className="topbar__search">
            <HorseSearchBox onSelect={(h) => openHorse(h.horse_id)} />
          </div>
          <div className="topbar__meta">
            <span className="header-date">{today}</span>
            <ApiStatus />
          </div>
        </header>

        <main className="app-main">
          {activeTab === 'dashboard' ? (
            <DashboardPage onNavigate={setActiveTab} onOpenHorse={openHorse} />
          ) : null}
          {activeTab === 'races' ? <RacesPage onNavigate={setActiveTab} /> : null}
          {activeTab === 'horses' ? <HorsesPage initialHorseId={focusHorseId} /> : null}
          {activeTab === 'predictions' ? <PredictionsPage onOpenHorse={openHorse} /> : null}
          {activeTab === 'analytics' ? <AnalyticsPage /> : null}
          {activeTab === 'system' ? <SystemStatusTab /> : null}
        </main>

        <footer className="app-footer">
          <p>امتیاز مدل احتمال قطعی برد نیست و تضمین سود وجود ندارد.</p>
        </footer>
      </div>

      <nav className="mobile-nav" aria-label="ناوبری موبایل">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={activeTab === item.id ? 'mobile-nav__btn active' : 'mobile-nav__btn'}
            onClick={() => setActiveTab(item.id)}
          >
            {item.short}
          </button>
        ))}
      </nav>
    </div>
  )
}
