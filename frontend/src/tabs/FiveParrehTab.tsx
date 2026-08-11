import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { ApiError } from '../api/types'
import type {
  FiveParrehCombinationsResponse,
  FiveParrehEventSummary,
  PredictionItem,
} from '../api/types'
import { RawJsonPanel } from '../components/RawJsonPanel'
import { horseDisplayName } from '../utils/format'

type SelectionMap = Record<string, Set<string>>

function horseKey(item: PredictionItem): string {
  if (item.horse_id != null) return String(item.horse_id)
  return horseDisplayName(item.horse_name)
}

export function FiveParrehTab() {
  const [events, setEvents] = useState<FiveParrehEventSummary[]>([])
  const [listMessage, setListMessage] = useState<string | null>(null)
  const [eventId, setEventId] = useState('')
  const [eventDetail, setEventDetail] = useState<FiveParrehEventSummary | null>(null)
  const [predictionsByRace, setPredictionsByRace] = useState<Record<string, PredictionItem[]>>({})
  const [selections, setSelections] = useState<SelectionMap>({})
  const [result, setResult] = useState<FiveParrehCombinationsResponse | null>(null)
  const [rawPayload, setRawPayload] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const payload = await api.listFiveParrehEvents()
        if (cancelled) return
        setEvents(payload.events ?? [])
        setListMessage(payload.message ?? null)
      } catch (err) {
        if (cancelled) return
        setEvents([])
        setListMessage(err instanceof ApiError ? err.message : 'بارگذاری رویدادها ناموفق بود')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  async function onEventChange(nextId: string) {
    setEventId(nextId)
    setEventDetail(null)
    setPredictionsByRace({})
    setSelections({})
    setResult(null)
    setRawPayload(null)
    setError(null)
    if (!nextId) return

    setLoading(true)
    try {
      const detail = await api.getFiveParrehEvent(nextId)
      setEventDetail(detail)
      const races = detail.races ?? []
      const preds: Record<string, PredictionItem[]> = {}
      const initialSelections: SelectionMap = {}
      for (const race of races) {
        const prediction = await api.racePrediction(race.race_id)
        preds[race.race_id] = prediction.prediction ?? []
        initialSelections[race.race_id] = new Set()
      }
      setPredictionsByRace(preds)
      setSelections(initialSelections)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'بارگذاری رویداد ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  function toggleHorse(raceIdKey: string, key: string) {
    setSelections((prev) => {
      const next = { ...prev }
      const set = new Set(next[raceIdKey] ?? [])
      if (set.has(key)) {
        set.delete(key)
      } else {
        set.add(key)
      }
      next[raceIdKey] = set
      return next
    })
  }

  const selectionCounts = useMemo(() => {
    const races = eventDetail?.races ?? []
    return races.map((race, index) => ({
      label: race.label ?? `کورس ${race.race_number ?? index + 1}`,
      count: selections[race.race_id]?.size ?? 0,
    }))
  }, [eventDetail, selections])

  async function generateCombinations() {
    if (!eventDetail?.races?.length) {
      setError('رویداد پنج‌پره انتخاب نشده است.')
      return
    }
    if (eventDetail.races.length !== 5) {
      setError('رویداد باید دقیقاً ۵ کورس داشته باشد.')
      return
    }

    for (const race of eventDetail.races) {
      if ((selections[race.race_id]?.size ?? 0) < 1) {
        setError('هر کورس باید حداقل یک اسب انتخاب‌شده داشته باشد.')
        return
      }
    }

    setLoading(true)
    setError(null)
    try {
      const body = {
        races: eventDetail.races.map((race) => ({
          race_id: race.race_id,
          horses: Array.from(selections[race.race_id] ?? []),
        })),
        include_combinations: false,
      }
      const response = await api.generateFiveParrehCombinations(body)
      setResult(response)
      setRawPayload(response)
    } catch (err) {
      setRawPayload(err instanceof ApiError ? err.body : null)
      setError(err instanceof ApiError ? err.message : 'محاسبه ترکیب‌ها ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  const noEvents = !events.length

  return (
    <section className="tab-panel">
      <h2>🎟 پنج‌پره</h2>
      <p className="hint">فقط رویدادهای پنج‌پرهٔ آیندهٔ ثبت‌شده در برنامه مسابقات.</p>

      {noEvents ? (
        <p className="info-box">
          {listMessage ?? 'هیچ پنج‌پره آینده‌ای در داده فعلی موجود نیست.'}
        </p>
      ) : (
        <label className="full-width">
          رویداد
          <select value={eventId} onChange={(e) => void onEventChange(e.target.value)} disabled={loading}>
            <option value="">— انتخاب —</option>
            {events.map((ev) => (
              <option key={ev.event_id} value={ev.event_id}>
                {ev.display_date ?? '—'} · {ev.location ?? ev.track ?? '—'}
              </option>
            ))}
          </select>
        </label>
      )}

      {eventDetail ? (
        <div className="result-card">
          <h3>🎟 پنج‌پره</h3>
          <p>📅 {eventDetail.display_date ?? '—'}</p>
          <p>📍 {eventDetail.location ?? eventDetail.track ?? '—'}</p>

          {(eventDetail.races ?? []).map((race, index) => {
            const candidates = predictionsByRace[race.race_id] ?? []
            const selected = selections[race.race_id] ?? new Set<string>()
            return (
              <div key={race.race_id} className="fp-race-block">
                <h4>🏇 {race.label ?? `کورس ${race.race_number ?? index + 1}`}</h4>
                {candidates.length ? (
                  <ul className="horse-select-list">
                    {candidates.map((item) => {
                      const key = horseKey(item)
                      const name = horseDisplayName(item.horse_name)
                      const checked = selected.has(key)
                      return (
                        <li key={key}>
                          <label className="checkbox-row">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleHorse(race.race_id, key)}
                              disabled={loading}
                            />
                            <span>{name}</span>
                          </label>
                        </li>
                      )
                    })}
                  </ul>
                ) : (
                  <p className="hint">اسبی برای این کورس در دسترس نیست.</p>
                )}
              </div>
            )
          })}

          <button
            type="button"
            className="primary-btn"
            onClick={() => void generateCombinations()}
            disabled={loading}
          >
            {loading ? 'در حال محاسبه…' : 'محاسبه ترکیب‌ها'}
          </button>
        </div>
      ) : null}

      {error ? <p className="error-box">{error}</p> : null}

      {result ? (
        <div className="result-card">
          <h3>نتیجه ترکیب‌ها</h3>
          <p>تعداد انتخاب‌ها:</p>
          <ul>
            {selectionCounts.map((row, index) => (
              <li key={row.label}>
                {row.label}: {row.count || result.selections_per_race?.[index] || 0}
              </li>
            ))}
          </ul>
          <p>
            تعداد ترکیب: <strong>{result.total_combinations ?? '—'}</strong>
          </p>
        </div>
      ) : null}

      <RawJsonPanel data={rawPayload} />
    </section>
  )
}
