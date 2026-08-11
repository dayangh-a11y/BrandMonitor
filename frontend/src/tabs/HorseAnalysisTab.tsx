import { useState } from 'react'
import { api } from '../api/client'
import { ApiError } from '../api/types'
import type { HorseAnalysisResponse, HorseSearchItem } from '../api/types'
import { RawJsonPanel } from '../components/RawJsonPanel'
import { formatEvidence, friendlyWarnings, horseDisplayName } from '../utils/format'

export function HorseAnalysisTab() {
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<HorseSearchItem[]>([])
  const [analysis, setAnalysis] = useState<HorseAnalysisResponse | null>(null)
  const [rawPayload, setRawPayload] = useState<unknown>(null)
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
    setMatches([])
    setSearchMessage(null)
    try {
      const result = await api.searchHorses(name)
      setMatches(result.horses ?? [])
      setRawPayload(result)
      if (!result.horses?.length) {
        setSearchMessage('اسبی با این نام پیدا نشد.')
      }
    } catch (err) {
      setRawPayload(err instanceof ApiError ? err.body : null)
      setError(err instanceof ApiError ? err.message : 'جستجو ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  async function selectHorse(horse: HorseSearchItem) {
    setLoading(true)
    setError(null)
    try {
      const result = await api.horseAnalysis(horse.horse_id)
      setAnalysis(result)
      setRawPayload(result)
    } catch (err) {
      setRawPayload(err instanceof ApiError ? err.body : null)
      setError(err instanceof ApiError ? err.message : 'تحلیل اسب ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="tab-panel">
      <h2>🐎 تحلیل اسب</h2>
      <p className="hint">نام اسب را وارد کنید — نیازی به شناسه داخلی نیست.</p>

      <div className="search-row">
        <label className="full-width">
          نام اسب
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
        <button type="button" className="primary-btn" onClick={() => void search()} disabled={loading}>
          {loading ? '…' : 'جستجو'}
        </button>
      </div>

      {error ? <p className="error-box">{error}</p> : null}
      {searchMessage ? <p className="info-box">{searchMessage}</p> : null}

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
        <div className="result-card">
          <h3>🐎 {horseDisplayName(analysis.horse_name)}</h3>
          {analysis.observation_count != null ? (
            <p>تعداد مشاهده: {analysis.observation_count}</p>
          ) : null}
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
              <h4>ویژگی‌های آخرین مسابقه</h4>
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
          ) : null}
        </div>
      ) : null}

      <RawJsonPanel data={rawPayload} />
    </section>
  )
}
