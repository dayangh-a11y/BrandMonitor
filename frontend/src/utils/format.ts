const WARNING_MESSAGES: Record<string, string> = {
  low_feature_coverage: '⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.',
  score_unavailable_insufficient_features:
    '⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.',
  ranking_unavailable_insufficient_features:
    '⚠️ برای این کورس دادهٔ کافی جهت رتبه‌بندی واقعی وجود ندارد — ترتیب شماره کارت به‌عنوان پیش‌بینی نمایش داده نمی‌شود.',
  source_rating_missing_for_field: '⚠️ ریتینگ رسمی اسب‌های این میدان در داده موجود نیست.',
}

export function formatScore(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  const num = Number(value)
  if (Number.isNaN(num)) {
    return '—'
  }
  return num.toFixed(1)
}

export function friendlyWarnings(warnings: string[] | undefined | null): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of warnings ?? []) {
    const key = String(raw).trim()
    const msg = WARNING_MESSAGES[key]
    if (!msg || seen.has(msg)) {
      continue
    }
    seen.add(msg)
    out.push(msg)
  }
  return out
}

export function medalForRank(rank: number): string {
  if (rank === 1) return '🥇'
  if (rank === 2) return '🥈'
  if (rank === 3) return '🥉'
  return `${rank}.`
}

export function horseDisplayName(name: string | null | undefined, fallback?: string): string {
  const trimmed = (name ?? '').trim()
  if (trimmed) return trimmed
  return fallback ?? 'اسب بدون نام'
}

export function formatEvidence(items: { metric?: string; value?: unknown }[] | undefined): string[] {
  if (!items?.length) return []
  return items.map((item) => {
    const metric = item.metric ?? '—'
    const value =
      item.value === null || item.value === undefined ? '—' : String(item.value)
    return `${metric}: ${value}`
  })
}
