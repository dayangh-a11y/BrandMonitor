import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { ApiError } from '../api/types'

type Status = 'checking' | 'online' | 'offline'

export function ApiStatus() {
  const [status, setStatus] = useState<Status>('checking')
  const [detail, setDetail] = useState<string>('')

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const health = await api.health()
        if (cancelled) return
        if (health.status === 'ok') {
          setStatus('online')
          setDetail(`نسخه ${health.version} · دیتاست ${health.dataset_version}`)
        } else {
          setStatus('offline')
          setDetail('پاسخ سلامت نامعتبر')
        }
      } catch (err) {
        if (cancelled) return
        setStatus('offline')
        if (err instanceof ApiError) {
          setDetail(err.message)
        } else {
          setDetail('اتصال برقرار نشد')
        }
      }
    }

    void check()
    const timer = window.setInterval(() => void check(), 30_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const label =
    status === 'checking'
      ? 'در حال بررسی…'
      : status === 'online'
        ? '🟢 API متصل است'
        : '🔴 API در دسترس نیست'

  return (
    <div className={`api-status api-status--${status}`} role="status" aria-live="polite">
      <span className="api-status__label">{label}</span>
      {detail ? <span className="api-status__detail">{detail}</span> : null}
    </div>
  )
}
