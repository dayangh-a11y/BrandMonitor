import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { ApiError } from '../api/types'
import type { MeetingDetailResponse, MeetingSummary, PredictionResponse } from '../api/types'
import { RawJsonPanel } from '../components/RawJsonPanel'
import {
  formatScore,
  friendlyWarnings,
  horseDisplayName,
  medalForRank,
} from '../utils/format'

export function RacePredictionTab() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [listMessage, setListMessage] = useState<string | null>(null)
  const [meetingId, setMeetingId] = useState('')
  const [meetingDetail, setMeetingDetail] = useState<MeetingDetailResponse | null>(null)
  const [raceId, setRaceId] = useState('')
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null)
  const [rawPayload, setRawPayload] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const payload = await api.upcomingMeetings()
        if (cancelled) return
        setMeetings(payload.meetings ?? [])
        setListMessage(payload.message ?? null)
      } catch (err) {
        if (cancelled) return
        setMeetings([])
        setListMessage(err instanceof ApiError ? err.message : 'بارگذاری جلسات ناموفق بود')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedMeeting = meetings.find((m) => m.meeting_id === meetingId)

  async function onMeetingChange(nextId: string) {
    setMeetingId(nextId)
    setRaceId('')
    setMeetingDetail(null)
    setPrediction(null)
    setRawPayload(null)
    setError(null)
    if (!nextId) return

    setLoading(true)
    try {
      const detail = await api.meetingDetail(nextId)
      setMeetingDetail(detail)
    } catch (err) {
      setMeetingDetail(null)
      setError(err instanceof ApiError ? err.message : 'بارگذاری جلسه ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  async function analyzeRace() {
    if (!raceId) {
      setError('لطفاً یک کورس انتخاب کنید.')
      return
    }
    setLoading(true)
    setError(null)
    setPrediction(null)
    try {
      const result = await api.racePrediction(raceId)
      setPrediction(result)
      setRawPayload(result)
    } catch (err) {
      setRawPayload(err instanceof ApiError ? err.body : null)
      setError(err instanceof ApiError ? err.message : 'تحلیل کورس ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  const races = meetingDetail?.races ?? selectedMeeting?.races ?? []
  const selectedRace = races.find((r) => r.race_id === raceId)

  return (
    <section className="tab-panel">
      <h2>🎯 پیش‌بینی کورس</h2>
      <p className="hint">مسابقهٔ آینده را انتخاب کنید و تحلیل کورس را بگیرید.</p>

      {listMessage && !meetings.length ? (
        <p className="info-box">{listMessage}</p>
      ) : null}

      <div className="form-grid">
        <label>
          📅 تاریخ / جلسه
          <select
            value={meetingId}
            onChange={(e) => void onMeetingChange(e.target.value)}
            disabled={loading}
          >
            <option value="">— انتخاب —</option>
            {meetings.map((m) => (
              <option key={m.meeting_id} value={m.meeting_id}>
                {m.display_date ?? '—'} · {m.location ?? m.track ?? '—'}
              </option>
            ))}
          </select>
        </label>

        <label>
          📍 محل
          <input
            type="text"
            readOnly
            value={
              meetingDetail?.location ??
              meetingDetail?.track ??
              selectedMeeting?.location ??
              selectedMeeting?.track ??
              ''
            }
            placeholder="با انتخاب جلسه پر می‌شود"
          />
        </label>

        <label>
          🏇 کورس
          <select
            value={raceId}
            onChange={(e) => setRaceId(e.target.value)}
            disabled={!meetingId || loading}
          >
            <option value="">— انتخاب —</option>
            {races.map((race) => (
              <option key={race.race_id} value={race.race_id}>
                {race.label ?? `کورس ${race.race_number ?? '?'}`}
              </option>
            ))}
          </select>
        </label>
      </div>

      <button type="button" className="primary-btn" onClick={() => void analyzeRace()} disabled={loading || !raceId}>
        {loading ? 'در حال تحلیل…' : 'تحلیل کورس'}
      </button>

      {error ? <p className="error-box">{error}</p> : null}

      {prediction ? (
        <div className="result-card">
          <h3>🏇 پیش‌بینی کورس</h3>
          <p>📅 {meetingDetail?.display_date ?? selectedMeeting?.display_date ?? '—'}</p>
          <p>
            📍{' '}
            {meetingDetail?.location ??
              meetingDetail?.track ??
              selectedMeeting?.location ??
              selectedMeeting?.track ??
              '—'}
          </p>
          <p>🏁 {selectedRace?.label ?? (selectedRace?.race_number ? `کورس ${selectedRace.race_number}` : '—')}</p>

          <ol className="rank-list">
            {(prediction.prediction ?? []).map((item) => {
              const scoreText = formatScore(item.score)
              const warnings = friendlyWarnings(item.warnings)
              const showWarning = scoreText === '—' || warnings.length > 0
              return (
                <li key={`${item.rank}-${item.horse_id ?? item.horse_name}`} className="rank-item">
                  <span className="rank-medal">{medalForRank(item.rank)}</span>
                  <div className="rank-body">
                    <strong>{horseDisplayName(item.horse_name)}</strong>
                    <span>امتیاز: {scoreText}</span>
                    {showWarning ? (
                      <span className="warning-text">
                        {warnings[0] ?? '⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.'}
                      </span>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ol>
        </div>
      ) : null}

      <RawJsonPanel data={rawPayload} />
    </section>
  )
}
