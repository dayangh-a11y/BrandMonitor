import { useState } from 'react'
import { ApiStatus } from './components/ApiStatus'
import { FiveParrehTab } from './tabs/FiveParrehTab'
import { HorseAnalysisTab } from './tabs/HorseAnalysisTab'
import { HorseVsHorseTab } from './tabs/HorseVsHorseTab'
import { RacePredictionTab } from './tabs/RacePredictionTab'
import './styles.css'

type TabId = 'predict' | 'horsevs' | 'fiveparreh' | 'horse'

const TABS: { id: TabId; label: string }[] = [
  { id: 'predict', label: '🎯 پیش‌بینی کورس' },
  { id: 'horsevs', label: '⚔️ اسب مقابل اسب' },
  { id: 'fiveparreh', label: '🎟 پنج‌پره' },
  { id: 'horse', label: '🐎 تحلیل اسب' },
]

function TabPanel({ active }: { active: TabId }) {
  switch (active) {
    case 'predict':
      return <RacePredictionTab />
    case 'horsevs':
      return <HorseVsHorseTab />
    case 'fiveparreh':
      return <FiveParrehTab />
    case 'horse':
      return <HorseAnalysisTab />
    default:
      return null
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('predict')

  return (
    <div className="app-shell" dir="rtl" lang="fa">
      <header className="app-header">
        <div>
          <h1>🏇 Horse Racing Prediction Lab</h1>
          <p className="subtitle">محیط تست موتور پیش‌بینی مسابقات اسب‌دوانی</p>
        </div>
        <ApiStatus />
      </header>

      <nav className="tab-nav" aria-label="بخش‌های داشبورد">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? 'tab-btn active' : 'tab-btn'}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="app-main">
        <TabPanel active={activeTab} />
      </main>

      <footer className="app-footer">
        <p>امتیازها احتمال قطعی برد نیستند. این داشبورد فقط واسط API است.</p>
      </footer>
    </div>
  )
}
