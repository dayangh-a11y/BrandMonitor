import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { MeetingSummary, PredictionResponse } from '../api/types'
import { EmptyState, SkeletonBlock, friendlyApiError } from '../components/Ui'
import { MiniBars } from '../components/MiniBars'
import { horseDisplayName } from '../utils/format'
import { FiveParrehTab } from '../tabs/FiveParrehTab'
import { HorseVsHorseTab } from '../tabs/HorseVsHorseTab'

export function AnalyticsPage() {
  const [loading, setLoading] = useState(true)
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<'overview' | 'h2h' | 'five'>('overview')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const upcoming = await api.upcomingMeetings()
        if (cancelled) return
        setMeetings(upcoming.meetings ?? [])
        const firstRace = (upcoming.meetings ?? [])
          .flatMap((m) => m.races ?? [])
          .find((r) => r.eligible_for_prediction !== false)
        if (firstRace?.race_id) {
          try {
            const pred = await api.racePrediction(String(firstRace.race_id))
            if (!cancelled) setPrediction(pred)
          } catch {
            // Prediction may be unavailable for some races — keep overview usable.
          }
        }
      } catch (err) {
        if (!cancelled) setError(friendlyApiError(err, 'بارگذاری Analytics ناموفق بود.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const scoreBars =
    prediction?.prediction
      ?.filter((p) => p.score != null)
      .slice(0, 8)
      .map((p) => ({ label: horseDisplayName(p.horse_name), value: Number(p.score) })) ?? []

  const formBars =
    prediction?.prediction
      ?.flatMap((p) =>
        (p.evidence ?? [])
          .filter((e) => /form|speed|class|win/i.test(String(e.metric)))
          .map((e) => ({
            label: `${horseDisplayName(p.horse_name)} · ${e.metric}`,
            value: Number(e.value),
          }))
          .filter((x) => !Number.isNaN(x.value)),
      )
      .slice(0, 10) ?? []

  return (
    <section className="page-card">
      <div className="page-head">
        <div>
          <h2 className="page-title">Analytics</h2>
          <p className="page-subtitle">نمودارها فقط از پاسخ واقعی API — بدون داده ساختگی</p>
        </div>
        <div className="seg-control">
          <button type="button" className={mode === 'overview' ? 'active' : ''} onClick={() => setMode('overview')}>
            Overview
          </button>
          <button type="button" className={mode === 'h2h' ? 'active' : ''} onClick={() => setMode('h2h')}>
            Horse vs Horse
          </button>
          <button type="button" className={mode === 'five' ? 'active' : ''} onClick={() => setMode('five')}>
            Five-Parreh
          </button>
        </div>
      </div>

      {error ? <p className="error-box">{error}</p> : null}

      {mode === 'overview' ? (
        loading ? (
          <SkeletonBlock rows={3} />
        ) : (
          <div className="dash-grid">
            <div className="panel span-6">
              <h3>مقایسه امتیاز کورس نمونه</h3>
              {scoreBars.length ? (
                <MiniBars items={scoreBars} accent="gold" />
              ) : (
                <EmptyState
                  title="امتیازی نیست"
                  body={
                    meetings.length
                      ? 'پیش‌بینی عددی برای کورس نمونه در دسترس نیست.'
                      : 'مسابقه‌ای برای تحلیل موجود نیست.'
                  }
                />
              )}
            </div>
            <div className="panel span-6">
              <h3>روند/شاخص فرم و سرعت (در صورت وجود)</h3>
              {formBars.length ? (
                <MiniBars items={formBars} accent="green" />
              ) : (
                <EmptyState
                  title="شاخصی در evidence نیست"
                  body="وقتی API متریک form/speed/class برگرداند، اینجا رسم می‌شود."
                />
              )}
            </div>
            <div className="panel span-12">
              <h3>فعالیت اخیر</h3>
              <p className="muted">
                جلسات بارگذاری‌شده: {meetings.length} · اسب‌های رتبه‌بندی‌شده در نمونه:{' '}
                {prediction?.prediction?.length ?? 0}
              </p>
            </div>
          </div>
        )
      ) : null}

      {mode === 'h2h' ? <HorseVsHorseTab /> : null}
      {mode === 'five' ? <FiveParrehTab /> : null}
    </section>
  )
}
