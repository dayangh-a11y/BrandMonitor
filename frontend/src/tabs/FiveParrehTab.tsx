import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  FiveParrehCombinationsResponse,
  FiveParrehEventSummary,
  PredictionItem,
} from '../api/types'
import { EmptyState, SkeletonBlock, friendlyApiError } from '../components/Ui'
import { formatScore, horseDisplayName } from '../utils/format'

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
  const [loadingList, setLoadingList] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoadingList(true)
      try {
        const payload = await api.listFiveParrehEvents()
        if (cancelled) return
        setEvents(payload.events ?? [])
        setListMessage(payload.message ?? null)
      } catch (err) {
        if (cancelled) return
        setEvents([])
        setListMessage(friendlyApiError(err, 'بارگذاری رویدادها ناموفق بود.'))
      } finally {
        if (!cancelled) setLoadingList(false)
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
        try {
          const prediction = await api.racePrediction(race.race_id)
          preds[race.race_id] = prediction.prediction ?? []
        } catch {
          preds[race.race_id] = []
        }
        initialSelections[race.race_id] = new Set()
      }
      setPredictionsByRace(preds)
      setSelections(initialSelections)
    } catch (err) {
      setError(friendlyApiError(err, 'بارگذاری رویداد ناموفق بود.'))
    } finally {
      setLoading(false)
    }
  }

  function toggleHorse(raceIdKey: string, key: string) {
    setSelections((prev) => {
      const next = { ...prev }
      const set = new Set(next[raceIdKey] ?? [])
      if (set.has(key)) set.delete(key)
      else set.add(key)
      next[raceIdKey] = set
      return next
    })
  }

  const selectionSummary = useMemo(() => {
    const races = eventDetail?.races ?? []
    return races.map((race, index) => {
      const selectedKeys = Array.from(selections[race.race_id] ?? [])
      const candidates = predictionsByRace[race.race_id] ?? []
      const names = selectedKeys.map((key) => {
        const found = candidates.find((c) => horseKey(c) === key)
        return horseDisplayName(found?.horse_name, key)
      })
      return {
        label: race.label ?? `کورس ${race.race_number ?? index + 1}`,
        count: selectedKeys.length,
        names,
      }
    })
  }, [eventDetail, selections, predictionsByRace])

  const suggestedCombo = useMemo(() => {
    if (!selectionSummary.length || selectionSummary.some((s) => s.count !== 1)) return null
    return selectionSummary.map((s) => ({ label: s.label, name: s.names[0] }))
  }, [selectionSummary])

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
    } catch (err) {
      setError(friendlyApiError(err, 'محاسبه ترکیب‌ها ناموفق بود.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page-card">
      <h2 className="page-title">پنج‌پره</h2>
      <p className="page-subtitle">انتخاب پنج اسب برتر از پنج کورس — فقط رویدادهای اعلام‌شده</p>

      {loadingList ? <SkeletonBlock rows={2} /> : null}
      {!loadingList && !events.length ? (
        <EmptyState
          title="پنج‌پره‌ای ثبت نشده"
          body={listMessage ?? 'هیچ پنج‌پره آینده‌ای در داده فعلی موجود نیست.'}
        />
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

      {loading && eventId ? <SkeletonBlock rows={3} /> : null}

      {eventDetail ? (
        <div className="panel" style={{ marginTop: '1rem' }}>
          <h3>{eventDetail.title ?? 'پنج‌پره'}</h3>
          <div className="meta-row">
            <span>📅 {eventDetail.display_date ?? '—'}</span>
            <span>📍 {eventDetail.location ?? eventDetail.track ?? '—'}</span>
          </div>

          {(eventDetail.races ?? []).map((race, index) => {
            const candidates = predictionsByRace[race.race_id] ?? []
            const selected = selections[race.race_id] ?? new Set<string>()
            return (
              <div key={race.race_id} className="fp-race-block">
                <h4>
                  {race.label ?? `کورس ${race.race_number ?? index + 1}`}
                  {race.race_number != null ? (
                    <span className="badge" style={{ marginInlineStart: '0.5rem' }}>
                      شماره {race.race_number}
                    </span>
                  ) : null}
                </h4>
                <p className="muted">
                  📍 {eventDetail.location ?? eventDetail.track ?? '—'}
                  {race.scheduled_start ? ` · ${race.scheduled_start}` : ''}
                </p>

                {candidates.length ? (
                  <>
                    <p className="muted">رتبه‌بندی پیش‌بینی‌شده:</p>
                    <ol className="rank-list">
                      {candidates.slice(0, 5).map((item) => (
                        <li key={horseKey(item)} className="rank-item">
                          <span className={`rank-num ${item.rank <= 3 ? `top${item.rank}` : ''}`}>
                            {item.rank}
                          </span>
                          <div className="rank-body">
                            <strong>{horseDisplayName(item.horse_name)}</strong>
                          </div>
                          <span className="badge">امتیاز: {formatScore(item.score)}</span>
                        </li>
                      ))}
                    </ol>
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
                  </>
                ) : (
                  <p className="hint">اسبی برای این کورس در دسترس نیست.</p>
                )}
              </div>
            )
          })}

          <button
            type="button"
            className="btn btn-gold"
            style={{ marginTop: '1rem' }}
            onClick={() => void generateCombinations()}
            disabled={loading}
          >
            {loading ? 'در حال محاسبه…' : 'محاسبه ترکیب‌ها'}
          </button>
        </div>
      ) : null}

      {error ? <p className="error-box">{error}</p> : null}

      {result ? (
        <div className="panel" style={{ marginTop: '1rem' }}>
          <h3>ترکیب پیشنهادی پنج‌پره</h3>
          <p>تعداد انتخاب‌ها:</p>
          <ul>
            {selectionSummary.map((row, index) => (
              <li key={row.label}>
                {row.label}: {row.count || result.selections_per_race?.[index] || 0}
              </li>
            ))}
          </ul>
          <p>
            تعداد ترکیب: <strong>{result.total_combinations ?? '—'}</strong>
          </p>

          {suggestedCombo ? (
            <div className="combo-picks">
              {suggestedCombo.map((row) => (
                <div key={row.label} className="combo-pick">
                  <span>{row.label}</span>
                  <strong>{row.name}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">
              برای نمایش یک ترکیب پیشنهادی مشخص، از هر کورس دقیقاً یک اسب انتخاب کنید.
            </p>
          )}
        </div>
      ) : null}
    </section>
  )
}
