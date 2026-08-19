import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { ApiError } from '../api/types'

type Status = 'checking' | 'online' | 'offline'

interface ApiStatusProps {
  compact?: boolean
  onChange?: (online: boolean, detail?: string) => void
}

export function ApiStatus({ compact = true, onChange }: ApiStatusProps) {
  const [status, setStatus] = useState<Status>('checking')
  const [detail, setDetail] = useState('')

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const health = await api.health()
        if (cancelled) return
        if (health.status === 'ok') {
          setStatus('online')
          setDetail(`نسخه ${health.version}`)
          onChange?.(true, health.dataset_version)
        } else {
          setStatus('offline')
          setDetail('پاسخ سلامت نامعتبر')
          onChange?.(false)
        }
      } catch (err) {
        if (cancelled) return
        setStatus('offline')
        setDetail(err instanceof ApiError ? err.message : 'اتصال برقرار نشد')
        onChange?.(false)
      }
    }

    void check()
    const timer = window.setInterval(() => void check(), 30_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [onChange])

  const label =
    status === 'checking' ? 'در حال بررسی…' : status === 'online' ? 'API متصل' : 'API قطع'

  if (compact) {
    return (
      <div className={`api-pill api-pill--${status}`} role="status" aria-live="polite">
        <span className="dot" aria-hidden />
        <span>{label}</span>
      </div>
    )
  }

  return (
    <div className={`api-pill api-pill--${status}`} role="status">
      <span className="dot" aria-hidden />
      <span>
        {label}
        {detail ? ` · ${detail}` : ''}
      </span>
    </div>
  )
}
