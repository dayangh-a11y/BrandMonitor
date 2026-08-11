import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { ApiError } from '../api/types'
import type {
  HorseCompareResponse,
  MeetingDetailResponse,
  MeetingSummary,
  PredictionItem,
  PredictionResponse,
} from '../api/types'
import { RawJsonPanel } from '../components/RawJsonPanel'
import {
  formatEvidence,
  formatScore,
  friendlyWarnings,
  horseDisplayName,
} from '../utils/format'

export function HorseVsHorseTab() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [listMessage, setListMessage] = useState<string | null>(null)
  const [meetingId, setMeetingId] = useState('')
  const [meetingDetail, setMeetingDetail] = useState<MeetingDetailResponse | null>(null)
  const [raceId, setRaceId] = useState('')
  const [field, setField] = useState<PredictionItem[]>([])
  const [horseAId, setHorseAId] = useState<number | ''>('')
  const [horseBId, setHorseBId] = useState<number | ''>('')
  const [compare, setCompare] = useState<HorseCompareResponse | null>(null)
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

  async function onMeetingChange(nextId: string) {
    setMeetingId(nextId)
    setRaceId('')
    setMeetingDetail(null)
    setField([])
    setHorseAId('')
    setHorseBId('')
    setCompare(null)
    setRawPayload(null)
    setError(null)
    if (!nextId) return

    setLoading(true)
    try {
      const detail = await api.meetingDetail(nextId)
      setMeetingDetail(detail)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'بارگذاری جلسه ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  async function onRaceChange(nextRaceId: string) {
    setRaceId(nextRaceId)
    setHorseAId('')
    setHorseBId('')
    setCompare(null)
    setRawPayload(null)
    setError(null)
    if (!nextRaceId) {
      setField([])
      return
    }

    setLoading(true)
    try {
      const prediction: PredictionResponse = await api.racePrediction(nextRaceId)
      setField(prediction.prediction ?? [])
    } catch (err) {
      setField([])
      setError(err instanceof ApiError ? err.message : 'بارگذاری اسب‌های کورس ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  async function runCompare() {
    setError(null)
    setCompare(null)

    if (!raceId) {
      setError('لطفاً کورس را انتخاب کنید.')
      return
    }
    if (!horseAId || !horseBId) {
      setError('هر دو اسب را انتخاب کنید.')
      return
    }
    if (horseAId === horseBId) {
      setError('دو اسب باید متفاوت باشند.')
      return
    }

    setLoading(true)
    try {
      const result = await api.compareHorses(raceId, horseAId, horseBId)
      setCompare(result)
      setRawPayload(result)
    } catch (err) {
      setRawPayload(err instanceof ApiError ? err.body : null)
      setError(err instanceof ApiError ? err.message : 'مقایسه ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  const races = meetingDetail?.races ?? []
  const horseA = field.find((h) => h.horse_id === horseAId)
  const horseB = field.find((h) => h.horse_id === horseBId)
  const selectedName =
    compare?.selected_horse?.horse_name ??
    (compare?.selected === 'horse_a'
      ? compare.horse_a.horse_name
      : compare?.selected === 'horse_b'
        ? compare.horse_b.horse_name
        : null)

  return (
    <section className="tab-panel">
      <h2>⚔️ اسب مقابل اسب</h2>
      <p className="hint">هر دو اسب باید در همان کورس آینده باشند.</p>

      {listMessage && !meetings.length ? <p className="info-box">{listMessage}</p> : null}

      <div className="form-grid">
        <label>
          📅 جلسهٔ آینده
          <select value={meetingId} onChange={(e) => void onMeetingChange(e.target.value)} disabled={loading}>
            <option value="">— انتخاب —</option>
            {meetings.map((m) => (
              <option key={m.meeting_id} value={m.meeting_id}>
                {m.display_date ?? '—'} · {m.location ?? m.track ?? '—'}
              </option>
            ))}
          </select>
        </label>

        <label>
          🏇 کورس
          <select
            value={raceId}
            onChange={(e) => void onRaceChange(e.target.value)}
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

        <label>
          اسب A
          <select
            value={horseAId}
            onChange={(e) => setHorseAId(e.target.value ? Number(e.target.value) : '')}
            disabled={!field.length || loading}
          >
            <option value="">— انتخاب —</option>
            {field.map((h) =>
              h.horse_id != null ? (
                <option key={h.horse_id} value={h.horse_id}>
                  {horseDisplayName(h.horse_name)}
                </option>
              ) : null,
            )}
          </select>
        </label>

        <label>
          اسب B
          <select
            value={horseBId}
            onChange={(e) => setHorseBId(e.target.value ? Number(e.target.value) : '')}
            disabled={!field.length || loading}
          >
            <option value="">— انتخاب —</option>
            {field.map((h) =>
              h.horse_id != null ? (
                <option key={h.horse_id} value={h.horse_id}>
                  {horseDisplayName(h.horse_name)}
                </option>
              ) : null,
            )}
          </select>
        </label>
      </div>

      <button
        type="button"
        className="primary-btn"
        onClick={() => void runCompare()}
        disabled={loading || !raceId || !horseAId || !horseBId}
      >
        {loading ? 'در حال مقایسه…' : 'مقایسه'}
      </button>

      {error ? <p className="error-box">{error}</p> : null}

      {compare ? (
        <div className="result-card compare-card">
          <h3>⚔️ مقایسه دو اسب</h3>
          <div className="compare-row">
            <div className="compare-side">
              <h4>{horseDisplayName(horseA?.horse_name ?? compare.horse_a.horse_name)}</h4>
              <p>امتیاز: {formatScore(compare.horse_a.score)}</p>
              {compare.horse_a.rank != null ? <p>رتبه: {compare.horse_a.rank}</p> : null}
              {friendlyWarnings(compare.horse_a.warnings).map((w) => (
                <p key={w} className="warning-text">
                  {w}
                </p>
              ))}
              {formatEvidence(compare.horse_a.evidence).map((line) => (
                <p key={line} className="evidence-line">
                  {line}
                </p>
              ))}
            </div>
            <div className="compare-vs">🆚</div>
            <div className="compare-side">
              <h4>{horseDisplayName(horseB?.horse_name ?? compare.horse_b.horse_name)}</h4>
              <p>امتیاز: {formatScore(compare.horse_b.score)}</p>
              {compare.horse_b.rank != null ? <p>رتبه: {compare.horse_b.rank}</p> : null}
              {friendlyWarnings(compare.horse_b.warnings).map((w) => (
                <p key={w} className="warning-text">
                  {w}
                </p>
              ))}
              {formatEvidence(compare.horse_b.evidence).map((line) => (
                <p key={line} className="evidence-line">
                  {line}
                </p>
              ))}
            </div>
          </div>

          {selectedName ? (
            <p className="compare-winner">
              🏆 انتخاب سیستم: <strong>{horseDisplayName(selectedName)}</strong>
            </p>
          ) : null}

          {compare.note ? <p className="note-text">{compare.note}</p> : null}

          {(compare.evidence ?? []).length > 0 ? (
            <div className="evidence-block">
              <h4>شواهد مقایسه</h4>
              <pre className="evidence-json">{JSON.stringify(compare.evidence, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      ) : null}

      <RawJsonPanel data={rawPayload} />
    </section>
  )
}
