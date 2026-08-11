export function SkeletonBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div style={{ display: 'grid', gap: '0.65rem' }}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton block" />
      ))}
    </div>
  )
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-box">
      <strong>{title}</strong>
      <p className="muted" style={{ margin: '0.35rem 0 0' }}>
        {body}
      </p>
    </div>
  )
}

export function friendlyApiError(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'status' in err) {
    const status = Number((err as { status: number }).status)
    if (status === 0) return 'ارتباط با سرویس برقرار نشد. لطفاً اتصال را بررسی کنید.'
    if (status === 404) return 'مورد درخواستی در داده‌های فعلی یافت نشد.'
    if (status === 422) return 'ورودی نامعتبر است. لطفاً انتخاب‌ها را بررسی کنید.'
    if (status >= 500) return 'خطای موقت در سرویس. لطفاً دوباره تلاش کنید.'
  }
  return fallback
}
