import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type {
  MeetingDetailResponse,
  MeetingSummary,
  PredictionItem,
  PredictionResponse,
  RaceDetailResponse,
} from '../api/types'
import { HorseDetailPanel } from '../components/HorseDetailPanel'
import { RankingTable } from '../components/RankingTable'
import { RaceSummaryCard } from '../components/RaceSummaryCard'
import { EmptyState, SkeletonBlock, friendlyApiError } from '../components/Ui'
import { MiniBars } from '../components/MiniBars'
import { riskFromWarnings, confidenceLabel } from '../utils/metrics'
import { formatScore, horseDisplayName } from '../utils/format'

interface Props {
  onOpenHorse: (horseId: number, name?: string) => void
}

export function PredictionsPage({ onOpenHorse }: Props) {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [listMessage, setListMessage] = useState<string | null>(null)
  const [meetingId, setMeetingId] = useState('')
  const [meetingDetail, setMeetingDetail] = useState<MeetingDetailResponse | null>(null)
  const [raceId, setRaceId] = useState('')
  const [breedFilter, setBreedFilter] = useState('')
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null)
  const [raceDetail, setRaceDetail] = useState<RaceDetailResponse | null>(null)
  const [selected, setSelected] = useState<PredictionItem | null>(null)
  const [horseDetailBusy, setHorseDetailBusy] = useState(false)
  const [horseAnalysis, setHorseAnalysis] = useState<Awaited<
    ReturnType<typeof api.horseAnalysis>
  > | null>(null)
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
        if (!cancelled) setListMessage(friendlyApiError(err, 'بارگذاری جلسات ناموفق بود.'))
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
  const races = meetingDetail?.races ?? selectedMeeting?.races ?? []
  const selectedRace = races.find((r) => r.race_id === raceId)
  const cities = Array.from(
    new Set(meetings.map((m) => m.city ?? m.track ?? m.location).filter(Boolean) as string[]),
  )

  async function onMeetingChange(nextId: string) {
    setMeetingId(nextId)
    setRaceId('')
    setMeetingDetail(null)
    setPrediction(null)
    setRaceDetail(null)
    setSelected(null)
    setHorseAnalysis(null)
    setError(null)
    if (!nextId) return
    setLoading(true)
    try {
      setMeetingDetail(await api.meetingDetail(nextId))
    } catch (err) {
      setError(friendlyApiError(err, 'بارگذاری جلسه ناموفق بود.'))
    } finally {
      setLoading(false)
    }
  }

  async function analyzeRace() {
    if (!raceId) {
      setError('لطفاً یک کورس (Heat) انتخاب کنید.')
      return
    }
    setLoading(true)
    setError(null)
    setPrediction(null)
    setRaceDetail(null)
    setSelected(null)
    setHorseAnalysis(null)
    try {
      const [pred, race] = await Promise.all([
        api.racePrediction(raceId),
        api.getRace(raceId).catch(() => null),
      ])
      setPrediction(pred)
      setRaceDetail(race)
      const first = pred.prediction?.[0] ?? null
      setSelected(first)
      if (first?.horse_id != null) void loadHorse(first.horse_id)
    } catch (err) {
      setError(friendlyApiError(err, 'پیش‌بینی در دسترس نیست.'))
    } finally {
      setLoading(false)
    }
  }

  async function loadHorse(horseId: number) {
    setHorseDetailBusy(true)
    try {
      setHorseAnalysis(await api.horseAnalysis(horseId))
    } catch {
      setHorseAnalysis(null)
    } finally {
      setHorseDetailBusy(false)
    }
  }

  async function onSelectHorse(item: PredictionItem) {
    setSelected(item)
    if (item.horse_id != null) await loadHorse(item.horse_id)
  }

  const filteredPrediction =
    prediction && breedFilter
      ? {
          ...prediction,
          prediction: (prediction.prediction ?? []).filter((p) => {
            const breed = (p.evidence ?? []).find((e) =>
              String(e.metric).toLowerCase().includes('breed'),
            )?.value
            return String(breed ?? raceDetail?.breed ?? '')
              .toLowerCase()
              .includes(breedFilter.toLowerCase())
          }),
        }
      : prediction

  const top = filteredPrediction?.prediction?.slice(0, 5) ?? []
  const compareBars = top
    .filter((t) => t.score != null)
    .map((t) => ({ label: horseDisplayName(t.horse_name), value: Number(t.score) }))

  return (
    <section className="page-card">
      <h2 className="page-title">تحلیل و پیش‌بینی مسابقه</h2>
      <p className="page-subtitle">انتخاب روز، شهر، کلاس/نژاد و کورس — سپس تحلیل با API واقعی</p>

      {loadingList ? <SkeletonBlock rows={2} /> : null}
      {!loadingList && !meetings.length ? (
        <EmptyState title="مسابقه‌ای انتخاب نشده / موجود نیست" body={listMessage ?? 'مسابقه‌ای نیست.'} />
      ) : null}

      <div className="hero-panel">
        <div className="form-grid">
          <label>
            Race Day / جلسه
            <select
              value={meetingId}
              onChange={(e) => void onMeetingChange(e.target.value)}
              disabled={loading || loadingList}
              aria-label="جلسه / تاریخ"
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
            City / Track
            <input
              type="text"
              readOnly
              value={
                meetingDetail?.city ??
                meetingDetail?.track ??
                selectedMeeting?.city ??
                selectedMeeting?.track ??
                ''
              }
              placeholder={cities[0] ? `مثلاً ${cities[0]}` : 'با انتخاب جلسه'}
              aria-label="شهر / پیست"
            />
          </label>

          <label>
            Breed / Class
            <input
              type="text"
              value={breedFilter || raceDetail?.breed || raceDetail?.race_class || ''}
              onChange={(e) => setBreedFilter(e.target.value)}
              placeholder="فیلتر اختیاری نژاد/کلاس"
              aria-label="نژاد / کلاس"
            />
          </label>

          <label>
            Heat / کورس
            <select
              value={raceId}
              onChange={(e) => setRaceId(e.target.value)}
              disabled={!meetingId || loading}
              aria-label="کورس"
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
          {loading ? 'در حال تحلیل…' : 'تحلیل مسابقه'}
        </button>
      </div>

      {error ? <p className="error-box">{error}</p> : null}

      {filteredPrediction ? (
        <div className="predict-result-grid">
          <div className="panel">
            <h3>نتیجه تحلیل</h3>
            <div className="meta-row">
              <span>
                اطمینان داده:{' '}
                {confidenceLabel(
                  top[0] ?? { rank: 0 },
                  filteredPrediction.data_completeness,
                )}
              </span>
              <span>
                ریسک:{' '}
                {(() => {
                  const r = riskFromWarnings(top[0]?.warnings)
                  return r === 'low' ? 'پایین' : r === 'medium' ? 'متوسط' : 'بالا'
                })()}
              </span>
              <span>اسب‌های پیشنهادی: {Math.min(3, top.length)}</span>
            </div>
            <ol className="top-picks">
              {top.slice(0, 3).map((item) => (
                <li key={item.rank} className={item.rank === 1 ? 'is-gold' : ''}>
                  <span className={`rank-badge rank-badge--${item.rank}`}>#{item.rank}</span>
                  <div>
                    <strong>
                      {horseDisplayName(item.horse_name)}
                      {item.rank === 1 ? ' · پیشنهاد اصلی' : ''}
                    </strong>
                    <div className="muted">امتیاز نسبی: {formatScore(item.score)}</div>
                    {(item.evidence ?? []).slice(0, 2).map((ev) => (
                      <div key={ev.metric} className="evidence-line">
                        {ev.metric}:{' '}
                        {ev.value == null || ev.value === '' ? 'در دسترس نیست' : String(ev.value)}
                      </div>
                    ))}
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <RaceSummaryCard
            raceDay={
              meetingDetail?.display_date ??
              selectedMeeting?.display_date ??
              raceDetail?.race_date
            }
            track={
              meetingDetail?.track ??
              meetingDetail?.city ??
              selectedMeeting?.track ??
              raceDetail?.track
            }
            heat={selectedRace?.label ?? (selectedRace?.race_number != null ? `کورس ${selectedRace.race_number}` : String(raceId))}
            distance={raceDetail?.distance}
            horseCount={raceDetail?.field_size ?? filteredPrediction.prediction?.length}
            raceClass={raceDetail?.race_class}
            breed={raceDetail?.breed}
          />

          <div className="panel span-full">
            <h3>رتبه‌بندی اسب‌ها</h3>
            <RankingTable
              prediction={filteredPrediction}
              selectedHorseId={selected?.horse_id}
              onSelectHorse={(item) => void onSelectHorse(item)}
            />
          </div>

          <div className="panel">
            <h3>جزئیات اسب</h3>
            <HorseDetailPanel
              loading={horseDetailBusy}
              analysis={horseAnalysis}
              predictionItem={selected}
            />
            {selected?.horse_id != null ? (
              <button
                type="button"
                className="btn btn-ghost"
                style={{ marginTop: '0.75rem' }}
                onClick={() => onOpenHorse(selected.horse_id!, selected.horse_name ?? undefined)}
              >
                باز کردن صفحه اسب
              </button>
            ) : null}
          </div>

          <div className="panel">
            <h3>مقایسه امتیاز (داده واقعی)</h3>
            {compareBars.length ? (
              <MiniBars items={compareBars} accent="gold" />
            ) : (
              <EmptyState title="نمودار نیست" body="امتیاز عددی برای رسم نمودار موجود نیست." />
            )}
          </div>
        </div>
      ) : !loading ? (
        <EmptyState
          title="مسابقه‌ای انتخاب نشده"
          body="Race Day، پیست و Heat را انتخاب کنید، سپس «تحلیل مسابقه» را بزنید."
        />
      ) : null}
    </section>
  )
}
