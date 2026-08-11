const WARNING_MESSAGES: Record<string, string> = {
  low_feature_coverage: '⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.',
  score_unavailable_insufficient_features:
    '⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.',
}

export function formatScore(value: unknown): string {
  if (value === null || value === undefined) {
    return 'در دسترس نیست'
  }
  const num = Number(value)
  if (Number.isNaN(num)) {
    return 'در دسترس نیست'
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
    const metric = item.metric ?? 'در دسترس نیست'
    const value =
      item.value === null || item.value === undefined ? 'در دسترس نیست' : String(item.value)
    return `${metric}: ${value}`
  })
}
