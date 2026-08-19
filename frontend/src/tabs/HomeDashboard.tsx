import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { HealthResponse, MeetingSummary } from '../api/types'
import { EmptyState, SkeletonBlock, friendlyApiError } from '../components/Ui'

interface HomeDashboardProps {
  onNavigate: (tab: 'predict' | 'fiveparreh' | 'horsevs' | 'horse') => void
}

export function HomeDashboard({ onNavigate }: HomeDashboardProps) {
  const [loading, setLoading] = useState(true)
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [upcoming, healthRes] = await Promise.all([
          api.upcomingMeetings(),
          api.health(),
        ])
        if (cancelled) return
        setMeetings(upcoming.meetings ?? [])
        setMessage(upcoming.message ?? null)
        setHealth(healthRes)
      } catch (err) {
        if (cancelled) return
        setError(friendlyApiError(err, 'بارگذاری داشبورد ناموفق بود.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const raceCount = meetings.reduce((sum, m) => sum + (m.races?.length ?? m.race_count ?? 0), 0)

  return (
    <section className="page-card">
      <h2 className="page-title">داشبورد</h2>
      <p className="page-subtitle">تحلیل و پیش‌بینی مسابقات اسب — نمای کلی وضعیت و مسابقات پیش‌رو</p>

      <div className="cta-row">
        <button type="button" className="btn btn-gold" onClick={() => onNavigate('predict')}>
          شروع پیش‌بینی
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => onNavigate('fiveparreh')}>
          پنج‌پره
        </button>
      </div>

      {error ? <p className="error-box">{error}</p> : null}

      {loading ? (
        <div style={{ marginTop: '1rem' }}>
          <SkeletonBlock rows={3} />
        </div>
      ) : (
        <>
          <div className="section-grid" style={{ marginTop: '1.25rem' }}>
            <div className="stat-card span-3">
              <div className="stat-label">مسابقات پیش‌رو</div>
              <div className="stat-value">{raceCount}</div>
            </div>
            <div className="stat-card span-3">
              <div className="stat-label">جلسات فعال</div>
              <div className="stat-value">{meetings.length}</div>
            </div>
            <div className="stat-card span-3">
              <div className="stat-label">وضعیت موتور</div>
              <div className="stat-value" style={{ fontSize: '1.1rem' }}>
                {health?.status === 'ok' ? 'آماده' : 'نامشخص'}
              </div>
            </div>
            <div className="stat-card span-3">
              <div className="stat-label">نسخه مدل/داده</div>
              <div className="stat-value" style={{ fontSize: '1rem' }}>
                {health?.dataset_version ?? '—'}
              </div>
            </div>
          </div>

          <div className="section-grid" style={{ marginTop: '1rem' }}>
            <div className="panel span-8">
              <h3>مسابقات پیش‌رو</h3>
              {!meetings.length ? (
                <EmptyState
                  title="مسابقه‌ای ثبت نشده"
                  body={message ?? 'در حال حاضر مسابقه‌ای برای این بازه ثبت نشده است.'}
                />
              ) : (
                <div className="section-grid">
                  {meetings.flatMap((meeting) =>
                    (meeting.races ?? []).map((race) => (
                      <article key={`${meeting.meeting_id}-${race.race_id}`} className="race-card span-6">
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
                          <h3 style={{ margin: 0 }}>{race.label ?? `کورس ${race.race_number ?? '—'}`}</h3>
                          <span className="badge badge--ok">آماده پیش‌بینی</span>
                        </div>
                        <div className="meta-row">
                          <span>📅 {meeting.display_date ?? '—'}</span>
                          <span>📍 {meeting.location ?? meeting.track ?? '—'}</span>
                          {race.race_number != null ? <span>🏁 شماره {race.race_number}</span> : null}
                        </div>
                        <button
                          type="button"
                          className="btn btn-primary"
                          style={{ marginTop: 'auto', alignSelf: 'flex-start' }}
                          onClick={() => onNavigate('predict')}
                        >
                          شروع پیش‌بینی
                        </button>
                      </article>
                    )),
                  )}
                </div>
              )}
            </div>

            <div className="panel span-4">
              <h3>وضعیت موتور پیش‌بینی</h3>
              <div className="status-list">
                <div className="status-row">
                  <span>API</span>
                  <span className="badge badge--ok">● متصل</span>
                </div>
                <div className="status-row">
                  <span>موتور پیش‌بینی</span>
                  <span className={`badge ${health?.dataset_loaded ? 'badge--ok' : 'badge--warn'}`}>
                    {health?.dataset_loaded ? '● آماده' : '● در حال آماده‌سازی'}
                  </span>
                </div>
                <div className="status-row">
                  <span>داده</span>
                  <span className="badge badge--ok">● متصل</span>
                </div>
              </div>
              <p className="muted" style={{ marginTop: '0.85rem' }}>
                امتیازها احتمال قطعی برد نیستند. تصمیم نهایی با کاربر است.
              </p>
            </div>

            <div className="panel span-6">
              <h3>آخرین پیش‌بینی‌ها</h3>
              <EmptyState
                title="هنوز پیش‌بینی ذخیره نشده"
                body="پس از اجرای پیش‌بینی کورس، نتایج اخیر از همان جریان در این بخش قابل پیگیری است."
              />
            </div>

            <div className="panel span-6">
              <h3>اسب‌های قابل توجه</h3>
              <EmptyState
                title="پس از پیش‌بینی نمایش داده می‌شود"
                body="رتبه‌های برتر هر کورس پس از تحلیل، از پاسخ واقعی API استخراج می‌شوند — بدون آمار ساختگی."
              />
            </div>
          </div>
        </>
      )}
    </section>
  )
}
