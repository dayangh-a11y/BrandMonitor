import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  HealthResponse,
  MeetingSummary,
  PredictionItem,
  PredictionResponse,
  RaceDetailResponse,
} from '../api/types'
import { HorseDetailPanel } from '../components/HorseDetailPanel'
import { HorseSearchBox } from '../components/HorseSearchBox'
import { RankingTable } from '../components/RankingTable'
import { RaceSummaryCard } from '../components/RaceSummaryCard'
import { EmptyState, SkeletonBlock, friendlyApiError } from '../components/Ui'
import { MiniBars } from '../components/MiniBars'
import { riskFromWarnings } from '../utils/metrics'
import { formatScore, horseDisplayName } from '../utils/format'
import type { NavId } from '../nav'

interface Props {
  onNavigate: (tab: NavId) => void
  onOpenHorse: (horseId: number, name?: string) => void
}

export function DashboardPage({ onNavigate, onOpenHorse }: Props) {
  const [loading, setLoading] = useState(true)
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [quickRaceId, setQuickRaceId] = useState('')
  const [quickBusy, setQuickBusy] = useState(false)
  const [quickPred, setQuickPred] = useState<PredictionResponse | null>(null)
  const [quickRace, setQuickRace] = useState<RaceDetailResponse | null>(null)
  const [quickError, setQuickError] = useState<string | null>(null)
  const [selected, setSelected] = useState<PredictionItem | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [upcoming, healthRes] = await Promise.all([api.upcomingMeetings(), api.health()])
        if (cancelled) return
        setMeetings(upcoming.meetings ?? [])
        setMessage(upcoming.message ?? null)
        setHealth(healthRes)
        const first = (upcoming.meetings ?? [])
          .flatMap((m) => (m.races ?? []).map((r) => r.race_id))
          .find(Boolean)
        if (first) setQuickRaceId(String(first))
      } catch (err) {
        if (!cancelled) setError(friendlyApiError(err, 'بارگذاری داشبورد ناموفق بود.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const flatRaces = useMemo(
    () =>
      meetings.flatMap((m) =>
        (m.races ?? []).map((r) => ({
          meeting: m,
          race: r,
        })),
      ),
    [meetings],
  )

  async function runQuickAnalysis() {
    if (!quickRaceId) {
      setQuickError('یک کورس انتخاب کنید.')
      return
    }
    setQuickBusy(true)
    setQuickError(null)
    setQuickPred(null)
    setQuickRace(null)
    setSelected(null)
    try {
      const [pred, race] = await Promise.all([
        api.racePrediction(quickRaceId),
        api.getRace(quickRaceId).catch(() => null),
      ])
      setQuickPred(pred)
      setQuickRace(race)
      setSelected(pred.prediction?.[0] ?? null)
    } catch (err) {
      setQuickError(friendlyApiError(err, 'تحلیل مسابقه در دسترس نیست.'))
    } finally {
      setQuickBusy(false)
    }
  }

  const top = quickPred?.prediction?.slice(0, 3) ?? []
  const chartItems = top
    .filter((t) => t.score != null)
    .map((t) => ({ label: horseDisplayName(t.horse_name), value: Number(t.score) }))

  return (
    <section className="page-card dashboard-page">
      <div className="page-head">
        <div>
          <h2 className="page-title">داشبورد</h2>
          <p className="page-subtitle">وضعیت API، مسابقات پیش‌رو، تحلیل سریع و جستجوی اسب</p>
        </div>
        <button type="button" className="btn btn-gold" onClick={() => onNavigate('predictions')}>
          تحلیل کامل مسابقه
        </button>
      </div>

      {error ? <p className="error-box">{error}</p> : null}

      {loading ? (
        <SkeletonBlock rows={4} />
      ) : (
        <>
          <div className="kpi-row">
            <div className="kpi">
              <span className="kpi__label">API</span>
              <strong className={health?.status === 'ok' ? 'ok' : 'warn'}>
                {health?.status === 'ok' ? '🟢 Connected' : '⚠️ Offline'}
              </strong>
            </div>
            <div className="kpi">
              <span className="kpi__label">مسابقات پیش‌رو</span>
              <strong>{flatRaces.length}</strong>
            </div>
            <div className="kpi">
              <span className="kpi__label">جلسات</span>
              <strong>{meetings.length}</strong>
            </div>
            <div className="kpi">
              <span className="kpi__label">موتور پیش‌بینی</span>
              <strong className={health?.dataset_loaded ? 'ok' : 'warn'}>
                {health?.dataset_loaded ? '🟢 Ready' : '⚠️ Preparing'}
              </strong>
            </div>
          </div>

          <div className="dash-grid">
            <div className="panel span-7">
              <h3>تحلیل سریع مسابقه</h3>
              <div className="form-grid">
                <label>
                  کورس
                  <select
                    value={quickRaceId}
                    onChange={(e) => setQuickRaceId(e.target.value)}
                    disabled={quickBusy || !flatRaces.length}
                  >
                    <option value="">— انتخاب —</option>
                    {flatRaces.map(({ meeting, race }) => (
                      <option key={`${meeting.meeting_id}-${race.race_id}`} value={race.race_id}>
                        {(meeting.display_date ?? '—') +
                          ' · ' +
                          (meeting.track ?? meeting.city ?? '—') +
                          ' · ' +
                          (race.label ?? `کورس ${race.race_number ?? '?'}`)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                disabled={quickBusy || !quickRaceId}
                onClick={() => void runQuickAnalysis()}
              >
                {quickBusy ? 'در حال تحلیل…' : 'تحلیل مسابقه'}
              </button>
              {quickError ? <p className="error-box">{quickError}</p> : null}
              {!flatRaces.length ? (
                <EmptyState
                  title="مسابقه‌ای ثبت نشده"
                  body={message ?? 'در این بازه مسابقه‌ای برای پیش‌بینی نیست.'}
                />
              ) : null}

              {quickPred ? (
                <div className="quick-result">
                  <div className="meta-row">
                    <span>
                      اطمینان داده:{' '}
                      {quickPred.data_completeness ??
                        (top.some((t) => (t.warnings ?? []).length) ? 'محدود' : 'کافی')}
                    </span>
                    <span>
                      ریسک:{' '}
                      {riskFromWarnings(top[0]?.warnings) === 'low'
                        ? 'پایین'
                        : riskFromWarnings(top[0]?.warnings) === 'medium'
                          ? 'متوسط'
                          : 'بالا'}
                    </span>
                    <span>پایه: {quickPred.baseline ?? 'A'}</span>
                  </div>
                  <ol className="top-picks">
                    {top.map((item) => (
                      <li key={item.rank} className={item.rank === 1 ? 'is-gold' : ''}>
                        <span className={`rank-badge rank-badge--${item.rank}`}>#{item.rank}</span>
                        <div>
                          <strong>{horseDisplayName(item.horse_name)}</strong>
                          <div className="muted">امتیاز {formatScore(item.score)}</div>
                        </div>
                      </li>
                    ))}
                  </ol>
                  {chartItems.length ? <MiniBars items={chartItems} accent="gold" /> : null}
                </div>
              ) : null}
            </div>

            <div className="panel span-5">
              <h3>جستجوی اسب</h3>
              <HorseSearchBox
                onSelect={(horse) => onOpenHorse(horse.horse_id, horse.horse_name)}
              />
              <div className="status-mini" style={{ marginTop: '1rem' }}>
                <div className="status-row">
                  <span>API</span>
                  <span>{health?.status === 'ok' ? '🟢 Connected' : '⚠️'}</span>
                </div>
                <div className="status-row">
                  <span>Health</span>
                  <span>{health?.status === 'ok' ? '200' : '—'}</span>
                </div>
                <div className="status-row">
                  <span>Prediction Engine</span>
                  <span>{health?.dataset_loaded ? '🟢 Ready' : '⚠️'}</span>
                </div>
                <div className="status-row">
                  <span>Database / Dataset</span>
                  <span>{health ? '🟢 Connected' : '⚠️'}</span>
                </div>
              </div>
            </div>

            <div className="panel span-7">
              <h3>مسابقات پیش‌رو</h3>
              {!flatRaces.length ? (
                <EmptyState title="خالی" body={message ?? 'مسابقه‌ای نیست.'} />
              ) : (
                <div className="race-list">
                  {flatRaces.slice(0, 8).map(({ meeting, race }) => (
                    <article key={`${meeting.meeting_id}-${race.race_id}`} className="race-card-lite">
                      <div>
                        <strong>{race.label ?? `کورس ${race.race_number ?? '—'}`}</strong>
                        <div className="muted">
                          {(meeting.display_date ?? '—') +
                            ' · ' +
                            (meeting.city ?? meeting.track ?? '—')}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => onNavigate('predictions')}
                      >
                        تحلیل
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <div className="panel span-5">
              <h3>جزئیات اسب منتخب</h3>
              {selected && selected.horse_id != null ? (
                <div>
                  <HorseDetailPanel predictionItem={selected} />
                  <button
                    type="button"
                    className="btn btn-primary"
                    style={{ marginTop: '0.75rem' }}
                    onClick={() => onOpenHorse(selected.horse_id!, selected.horse_name ?? undefined)}
                  >
                    تحلیل کامل اسب
                  </button>
                </div>
              ) : (
                <EmptyState title="هنوز انتخاب نشده" body="پس از تحلیل، روی یک اسب کلیک کنید." />
              )}
              {quickRace ? (
                <div style={{ marginTop: '1rem' }}>
                  <RaceSummaryCard
                    raceDay={quickRace.race_date}
                    track={quickRace.track}
                    heat={String(quickRace.race_id)}
                    distance={quickRace.distance}
                    horseCount={quickRace.field_size}
                    raceClass={quickRace.race_class}
                    breed={quickRace.breed}
                  />
                </div>
              ) : null}
            </div>

            {quickPred ? (
              <div className="panel span-12">
                <h3>رتبه‌بندی</h3>
                <RankingTable
                  prediction={quickPred}
                  selectedHorseId={selected?.horse_id}
                  onSelectHorse={setSelected}
                />
              </div>
            ) : null}
          </div>
        </>
      )}
    </section>
  )
}
