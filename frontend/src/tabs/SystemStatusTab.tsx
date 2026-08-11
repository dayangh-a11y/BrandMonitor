import { useEffect, useState } from 'react'
import { api, getApiBaseUrl } from '../api/client'
import type { HealthResponse } from '../api/types'
import { ApiStatus } from '../components/ApiStatus'
import { RawJsonPanel } from '../components/RawJsonPanel'
import { EmptyState, friendlyApiError } from '../components/Ui'

export function SystemStatusTab() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [raw, setRaw] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await api.health()
        if (cancelled) return
        setHealth(res)
        setRaw(res)
      } catch (err) {
        if (cancelled) return
        setError(friendlyApiError(err, 'دریافت وضعیت سیستم ناموفق بود.'))
        setRaw(err && typeof err === 'object' && 'body' in err ? (err as { body: unknown }).body : null)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="page-card">
      <h2 className="page-title">System</h2>
      <p className="page-subtitle">وضعیت اتصال سرویس‌ها برای پشتیبانی فنی</p>

      <div style={{ margin: '0.75rem 0' }}>
        <ApiStatus compact={false} />
      </div>

      {error ? <p className="error-box">{error}</p> : null}

      <div className="status-list" style={{ marginTop: '1rem' }}>
        <div className="status-row">
          <span>API</span>
          <span className={`badge ${health?.status === 'ok' ? 'badge--ok' : 'badge--warn'}`}>
            {health?.status === 'ok' ? '🟢 Connected' : '⚠️ Offline'}
          </span>
        </div>
        <div className="status-row">
          <span>Health</span>
          <span className={`badge ${health?.status === 'ok' ? 'badge--ok' : 'badge--warn'}`}>
            {health?.status === 'ok' ? '200' : '—'}
          </span>
        </div>
        <div className="status-row">
          <span>Prediction Engine</span>
          <span className={`badge ${health?.dataset_loaded ? 'badge--ok' : 'badge--warn'}`}>
            {health?.dataset_loaded ? '🟢 Ready' : '⚠️ Preparing'}
          </span>
        </div>
        <div className="status-row">
          <span>Database / Dataset</span>
          <span className={`badge ${health ? 'badge--ok' : 'badge--warn'}`}>
            {health ? '🟢 Connected' : '⚠️'}
          </span>
        </div>
      </div>

      <div className="panel" style={{ marginTop: '1rem' }}>
        <h3>خلاصه فنی</h3>
        {health ? (
          <ul className="muted">
            <li>نسخه API: {health.version}</li>
            <li>نسخه دیتاست: {health.dataset_version}</li>
            <li>وضعیت ML: {health.ml_status ?? '—'}</li>
            <li>پایه پیش‌فرض: {health.baseline_default ?? '—'}</li>
            <li>آدرس پایه پیکربندی‌شده: {getApiBaseUrl()}</li>
          </ul>
        ) : (
          <EmptyState title="وضعیت در دسترس نیست" body="پس از اتصال موفق API، جزئیات اینجا نمایش داده می‌شود." />
        )}
      </div>

      <RawJsonPanel data={raw} title="پاسخ خام API (پیشرفته)" />
    </section>
  )
}
