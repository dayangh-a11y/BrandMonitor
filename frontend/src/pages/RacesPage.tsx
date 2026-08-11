import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { MeetingSummary, RaceListItem } from '../api/types'
import { EmptyState, SkeletonBlock, friendlyApiError } from '../components/Ui'
import type { NavId } from '../nav'

interface Props {
  onNavigate: (tab: NavId) => void
}

export function RacesPage({ onNavigate }: Props) {
  const [loading, setLoading] = useState(true)
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [freezeRaces, setFreezeRaces] = useState<RaceListItem[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [upcoming, listed] = await Promise.all([
          api.upcomingMeetings(),
          api.listRaces(40, 0).catch(() => null),
        ])
        if (cancelled) return
        setMeetings(upcoming.meetings ?? [])
        setMessage(upcoming.message ?? null)
        setFreezeRaces(listed?.races ?? [])
      } catch (err) {
        if (!cancelled) setError(friendlyApiError(err, 'بارگذاری مسابقات ناموفق بود.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <h2 className="page-title">Races</h2>
          <p className="page-subtitle">جلسات پیش‌رو و فهرست کورس‌های موجود در داده</p>
        </div>
        <button type="button" className="btn btn-gold" onClick={() => onNavigate('predictions')}>
          رفتن به پیش‌بینی
        </button>
      </div>

      {error ? <p className="error-box">{error}</p> : null}
      {loading ? <SkeletonBlock rows={3} /> : null}

      {!loading ? (
        <div className="dash-grid">
          <div className="panel span-12">
            <h3>مسابقات پیش‌رو (برنامه)</h3>
            {!meetings.length ? (
              <EmptyState title="مسابقه‌ای نیست" body={message ?? 'بازه‌ای خالی است.'} />
            ) : (
              <div className="race-list">
                {meetings.map((m) => (
                  <article key={m.meeting_id} className="race-card-lite">
                    <div>
                      <strong>{m.display_date ?? m.meeting_id}</strong>
                      <div className="muted">
                        {(m.city ?? m.track ?? '—') +
                          ' · ' +
                          String(m.races?.length ?? m.race_count ?? 0) +
                          ' کورس'}
                      </div>
                    </div>
                    <button type="button" className="btn btn-primary" onClick={() => onNavigate('predictions')}>
                      تحلیل
                    </button>
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="panel span-12">
            <h3>کورس‌های دیتاست (API /races)</h3>
            {!freezeRaces.length ? (
              <EmptyState title="فهرست خالی" body="هیچ کورسی از endpoint /races برنگشت." />
            ) : (
              <div className="table-wrap">
                <table className="rank-table">
                  <thead>
                    <tr>
                      <th>Race ID</th>
                      <th>تاریخ</th>
                      <th>پیست</th>
                      <th>مسافت</th>
                      <th>نژاد</th>
                      <th>فیلد</th>
                    </tr>
                  </thead>
                  <tbody>
                    {freezeRaces.map((r) => (
                      <tr key={r.race_id}>
                        <td>{r.race_id}</td>
                        <td>{r.race_date ?? '—'}</td>
                        <td>{r.track ?? '—'}</td>
                        <td>{r.distance ?? '—'}</td>
                        <td>{r.breed ?? '—'}</td>
                        <td>{r.field_size ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  )
}
