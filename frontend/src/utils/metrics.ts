import type { EvidenceItem, PredictionItem } from '../api/types'

const METRIC_ALIASES: Record<string, string[]> = {
  age: ['age', 'horse_age', 'Age'],
  breed: ['breed', 'surface', 'blood', 'Breed'],
  trainer: ['trainer', 'coach', 'Trainer'],
  jockey: ['jockey', 'rider', 'Jockey'],
  form: ['form', 'recent_form', 'form_score', 'Form'],
  speed: ['speed', 'speed_figure', 'avg_speed', 'Speed'],
  class: ['class', 'race_class', 'class_rating', 'Class'],
  win_rate: ['win_rate', 'win_pct', 'wins', 'WinRate'],
  avg_finish: ['avg_finish', 'average_finish', 'mean_finish'],
}

export function evidenceMap(items: EvidenceItem[] | undefined | null): Map<string, unknown> {
  const map = new Map<string, unknown>()
  for (const item of items ?? []) {
    if (!item?.metric) continue
    map.set(String(item.metric), item.value)
    map.set(String(item.metric).toLowerCase(), item.value)
  }
  return map
}

export function pickEvidence(
  items: EvidenceItem[] | undefined | null,
  key: keyof typeof METRIC_ALIASES,
): string {
  const map = evidenceMap(items)
  for (const alias of METRIC_ALIASES[key]) {
    if (map.has(alias)) {
      const v = map.get(alias)
      if (v === null || v === undefined || v === '') return '—'
      return String(v)
    }
    const lower = alias.toLowerCase()
    if (map.has(lower)) {
      const v = map.get(lower)
      if (v === null || v === undefined || v === '') return '—'
      return String(v)
    }
  }
  return '—'
}

export function relativeScoreShare(
  item: PredictionItem,
  field: PredictionItem[],
): number | null {
  const scores = field
    .map((x) => (x.score == null ? null : Number(x.score)))
    .filter((x): x is number => x != null && !Number.isNaN(x) && x > 0)
  if (!scores.length || item.score == null) return null
  const total = scores.reduce((a, b) => a + b, 0)
  if (total <= 0) return null
  return (Number(item.score) / total) * 100
}

export function riskFromWarnings(warnings: string[] | undefined | null): 'low' | 'medium' | 'high' {
  const n = (warnings ?? []).length
  if (n === 0) return 'low'
  if (n === 1) return 'medium'
  return 'high'
}

export function confidenceLabel(
  item: PredictionItem,
  completeness?: string | null,
): string {
  if ((item.warnings ?? []).length) return 'محدود'
  if (completeness) return String(completeness)
  if (item.score == null) return 'نامشخص'
  return 'کافی'
}

export function numericEvidenceSeries(
  items: EvidenceItem[] | undefined | null,
  preferred: string[],
): { label: string; value: number }[] {
  const out: { label: string; value: number }[] = []
  for (const item of items ?? []) {
    const key = String(item.metric ?? '')
    if (preferred.length && !preferred.some((p) => key.toLowerCase().includes(p.toLowerCase()))) {
      continue
    }
    const num = Number(item.value)
    if (Number.isNaN(num)) continue
    out.push({ label: key, value: num })
  }
  return out
}
