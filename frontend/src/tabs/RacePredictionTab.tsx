import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { MeetingDetailResponse, MeetingSummary, PredictionResponse } from '../api/types'
import { EmptyState, SkeletonBlock, friendlyApiError } from '../components/Ui'
import {
  formatScore,
  friendlyWarnings,
  horseDisplayName,
} from '../utils/format'

export function RacePredictionTab() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [listMessage, setListMessage] = useState<string | null>(null)
  const [meetingId, setMeetingId] = useState('')
  const [meetingDetail, setMeetingDetail] = useState<MeetingDetailResponse | null>(null)
  const [raceId, setRaceId] = useState('')
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoadingList(true)
      try {
        const payload = await api.upcomingMeetings()
        if (cancelled) return
        setMeetings(payload.meetings ?? [])
        setListMessage(payload.message ?? null)
      } catch (err) {
        if (cancelled) return
        setMeetings([])
        setListMessage(friendlyApiError(err, 'بارگذاری جلسات ناموفق بود.'))
      } finally {
        if (!cancelled) setLoadingList(false)
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
    setError(null)
    if (!nextId) return

    setLoading(true)
    try {
      const detail = await api.meetingDetail(nextId)
      setMeetingDetail(detail)
    } catch (err) {
      setMeetingDetail(null)
      setError(friendlyApiError(err, 'بارگذاری جلسه ناموفق بود.'))
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
    } catch (err) {
      setError(friendlyApiError(err, 'تحلیل کورس ناموفق بود.'))
    } finally {
      setLoading(false)
    }
  }

  const races = meetingDetail?.races ?? selectedMeeting?.races ?? []
  const selectedRace = races.find((r) => r.race_id === raceId)

  return (
    <section className="page-card">
      <h2 className="page-title">پیش‌بینی کورس</h2>
      <p className="page-subtitle">جلسه و کورس آینده را انتخاب کنید — بدون نیاز به شناسه داخلی</p>

      {loadingList ? <SkeletonBlock rows={2} /> : null}

      {!loadingList && !meetings.length ? (
        <EmptyState
          title="مسابقه‌ای در دسترس نیست"
          body={listMessage ?? 'در حال حاضر مسابقه‌ای برای این بازه ثبت نشده است.'}
        />
      ) : null}

      <div className="form-grid">
        <label>
          جلسه / تاریخ
          <select
            value={meetingId}
            onChange={(e) => void onMeetingChange(e.target.value)}
            disabled={loading || loadingList}
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
          محل
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
          کورس
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

      <button
        type="button"
        className="btn btn-gold"
        onClick={() => void analyzeRace()}
        disabled={loading || !raceId}
      >
        {loading ? 'در حال تحلیل…' : 'شروع پیش‌بینی'}
      </button>

      {error ? <p className="error-box">{error}</p> : null}

      {prediction ? (
        <div className="panel" style={{ marginTop: '1rem' }}>
          <h3>نتیجه پیش‌بینی</h3>
          <div className="meta-row">
            <span>📅 {meetingDetail?.display_date ?? selectedMeeting?.display_date ?? '—'}</span>
            <span>
              📍{' '}
              {meetingDetail?.location ??
                meetingDetail?.track ??
                selectedMeeting?.location ??
                selectedMeeting?.track ??
                '—'}
            </span>
            <span>
              🏁 {selectedRace?.label ?? (selectedRace?.race_number ? `کورس ${selectedRace.race_number}` : '—')}
            </span>
          </div>

          <ol className="rank-list">
            {(prediction.prediction ?? []).map((item) => {
              const scoreText = formatScore(item.score)
              const warnings = friendlyWarnings(item.warnings)
              const showWarning = scoreText === '—' || warnings.length > 0
              const rankClass =
                item.rank === 1 ? 'top1' : item.rank === 2 ? 'top2' : item.rank === 3 ? 'top3' : ''
              return (
                <li key={`${item.rank}-${item.horse_id ?? item.horse_name}`} className="rank-item">
                  <span className={`rank-num ${rankClass}`}>{item.rank}</span>
                  <div className="rank-body">
                    <strong>{horseDisplayName(item.horse_name)}</strong>
                    {showWarning ? (
                      <span className="warning-text">
                        {warnings[0] ?? '⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.'}
                      </span>
                    ) : null}
                    {(item.evidence ?? []).slice(0, 3).map((ev) => (
                      <span key={`${ev.metric}`} className="evidence-line">
                        {ev.metric}: {ev.value == null ? '—' : String(ev.value)}
                      </span>
                    ))}
                  </div>
                  <div>
                    <span className="badge">امتیاز: {scoreText}</span>
                  </div>
                </li>
              )
            })}
          </ol>
        </div>
      ) : null}
    </section>
  )
}
