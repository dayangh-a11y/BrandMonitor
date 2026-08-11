import { useMemo, useState } from 'react'
import { ApiStatus } from './components/ApiStatus'
import { FiveParrehTab } from './tabs/FiveParrehTab'
import { HomeDashboard } from './tabs/HomeDashboard'
import { HorseAnalysisTab } from './tabs/HorseAnalysisTab'
import { HorseVsHorseTab } from './tabs/HorseVsHorseTab'
import { RacePredictionTab } from './tabs/RacePredictionTab'
import { SystemStatusTab } from './tabs/SystemStatusTab'
import './styles.css'

type TabId = 'home' | 'predict' | 'fiveparreh' | 'horsevs' | 'horse' | 'system'

const TABS: { id: TabId; label: string }[] = [
  { id: 'home', label: 'داشبورد' },
  { id: 'predict', label: 'پیش‌بینی کورس' },
  { id: 'fiveparreh', label: 'پنج‌پره' },
  { id: 'horsevs', label: 'اسب مقابل اسب' },
  { id: 'horse', label: 'تحلیل اسب' },
  { id: 'system', label: 'API / وضعیت سیستم' },
]

function TabPanel({
  active,
  onNavigate,
}: {
  active: TabId
  onNavigate: (tab: Exclude<TabId, 'home' | 'system'>) => void
}) {
  switch (active) {
    case 'home':
      return <HomeDashboard onNavigate={onNavigate} />
    case 'predict':
      return <RacePredictionTab />
    case 'fiveparreh':
      return <FiveParrehTab />
    case 'horsevs':
      return <HorseVsHorseTab />
    case 'horse':
      return <HorseAnalysisTab />
    case 'system':
      return <SystemStatusTab />
    default:
      return null
  }
}

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
  const [activeTab, setActiveTab] = useState<TabId>('home')
  const today = useMemo(() => persianDate(), [])

  return (
    <div className="app-shell" dir="rtl" lang="fa">
      <header className="app-header">
        <div className="brand-block">
          <h1 className="brand-name">والدین اسب مسابقه باارزش</h1>
          <p className="brand-tagline">تحلیل و پیش‌بینی مسابقات اسب</p>
        </div>
        <div className="header-meta">
          <span className="header-date">{today}</span>
          <ApiStatus />
        </div>
      </header>

      <nav className="app-nav" aria-label="ناوبری اصلی">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="app-main">
        <TabPanel
          active={activeTab}
          onNavigate={(tab) => setActiveTab(tab)}
        />
      </main>

      <footer className="app-footer">
        <p>امتیازها احتمال قطعی برد نیستند و تضمین سود وجود ندارد.</p>
      </footer>
    </div>
  )
}
