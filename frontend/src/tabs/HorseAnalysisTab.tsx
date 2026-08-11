import { useState } from 'react'
import { api } from '../api/client'
import type { HorseAnalysisResponse, HorseSearchItem } from '../api/types'
import { EmptyState, friendlyApiError } from '../components/Ui'
import { formatEvidence, friendlyWarnings, horseDisplayName } from '../utils/format'

export function HorseAnalysisTab() {
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<HorseSearchItem[]>([])
  const [analysis, setAnalysis] = useState<HorseAnalysisResponse | null>(null)
  const [selectedSearch, setSelectedSearch] = useState<HorseSearchItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchMessage, setSearchMessage] = useState<string | null>(null)

  async function search() {
    const name = query.trim()
    if (!name) {
      setError('نام اسب را وارد کنید.')
      return
    }
    setLoading(true)
    setError(null)
    setAnalysis(null)
    setSelectedSearch(null)
    setMatches([])
    setSearchMessage(null)
    try {
      const result = await api.searchHorses(name)
      setMatches(result.horses ?? [])
      if (!result.horses?.length) {
        setSearchMessage('اسبی با این نام پیدا نشد.')
      }
    } catch (err) {
      setError(friendlyApiError(err, 'جستجو ناموفق بود.'))
    } finally {
      setLoading(false)
    }
  }

  async function selectHorse(horse: HorseSearchItem) {
    setLoading(true)
    setError(null)
    setSelectedSearch(horse)
    try {
      const result = await api.horseAnalysis(horse.horse_id)
      setAnalysis(result)
    } catch (err) {
      setError(friendlyApiError(err, 'تحلیل اسب ناموفق بود.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page-card">
      <h2 className="page-title">تحلیل اسب</h2>
      <p className="page-subtitle">جستجو با نام فارسی یا لاتین — بدون نیاز به شناسه داخلی</p>

      <div className="search-row">
        <label className="full-width">
          نام اسب را وارد کنید
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="مثال: دنزی بوی"
            onKeyDown={(e) => {
              if (e.key === 'Enter') void search()
            }}
          />
        </label>
        <button type="button" className="btn btn-primary" onClick={() => void search()} disabled={loading}>
          {loading ? '…' : 'جستجو'}
        </button>
      </div>

      {error ? <p className="error-box">{error}</p> : null}
      {searchMessage ? <EmptyState title="نتیجه‌ای نیست" body={searchMessage} /> : null}

      {matches.length ? (
        <ul className="match-list">
          {matches.map((horse) => (
            <li key={horse.horse_id}>
              <button type="button" className="link-btn" onClick={() => void selectHorse(horse)} disabled={loading}>
                {horse.horse_name}
                {horse.breed ? ` · ${horse.breed}` : ''}
                {horse.birth_year ? ` · ${horse.birth_year}` : ''}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {analysis ? (
        <div className="panel" style={{ marginTop: '1rem' }}>
          <h3>{horseDisplayName(analysis.horse_name)}</h3>
          {selectedSearch && selectedSearch.horse_name !== analysis.horse_name ? (
            <p className="muted">نام نمایشی جستجو: {selectedSearch.horse_name}</p>
          ) : null}
          {selectedSearch?.breed ? <p>نژاد: {selectedSearch.breed}</p> : null}
          {selectedSearch?.sex ? <p>جنسیت: {selectedSearch.sex}</p> : null}
          {selectedSearch?.birth_year ? <p>سال تولد: {selectedSearch.birth_year}</p> : null}
          {analysis.observation_count != null ? <p>تعداد مشاهده: {analysis.observation_count}</p> : null}
          {analysis.latest_race_date ? <p>آخرین مسابقه: {analysis.latest_race_date}</p> : null}
          {analysis.note ? <p className="note-text">{analysis.note}</p> : null}

          {friendlyWarnings(analysis.warnings).map((w) => (
            <p key={w} className="warning-text">
              {w}
            </p>
          ))}

          {formatEvidence(analysis.evidence).length ? (
            <div>
              <h4>شواهد</h4>
              {formatEvidence(analysis.evidence).map((line) => (
                <p key={line} className="evidence-line">
                  {line}
                </p>
              ))}
            </div>
          ) : null}

          {formatEvidence(analysis.latest_features).length ? (
            <div>
              <h4>شاخص‌های آخرین مشاهده</h4>
              {formatEvidence(analysis.latest_features).map((line) => (
                <p key={line} className="evidence-line">
                  {line}
                </p>
              ))}
            </div>
          ) : null}

          {(analysis.appearances ?? []).length ? (
            <div>
              <h4>سوابق مسابقه</h4>
              <pre className="evidence-json">{JSON.stringify(analysis.appearances, null, 2)}</pre>
            </div>
          ) : (
            <EmptyState title="سابقهٔ اضافی نیست" body="فیلد سابقهٔ بیشتر از API برای این اسب برنگشته است." />
          )}
        </div>
      ) : null}
    </section>
  )
}
