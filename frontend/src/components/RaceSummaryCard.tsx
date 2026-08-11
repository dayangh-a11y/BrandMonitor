interface RaceSummaryCardProps {
  raceDay?: string | null
  track?: string | null
  heat?: string | null
  distance?: string | number | null
  horseCount?: number | null
  raceClass?: string | null
  surface?: string | null
  breed?: string | null
}

export function RaceSummaryCard(props: RaceSummaryCardProps) {
  const rows: [string, string][] = [
    ['روز مسابقه', props.raceDay || '—'],
    ['پیست / شهر', props.track || '—'],
    ['کورس (Heat)', props.heat || '—'],
    ['مسافت', props.distance != null && props.distance !== '' ? String(props.distance) : '—'],
    ['تعداد اسب', props.horseCount != null ? String(props.horseCount) : '—'],
    ['کلاس', props.raceClass || '—'],
    ['نژاد', props.breed || '—'],
    ['سطح', props.surface || '—'],
  ]

  return (
    <div className="summary-card">
      <h3>خلاصه مسابقه</h3>
      <dl className="summary-dl">
        {rows.map(([k, v]) => (
          <div key={k} className="summary-dl__row">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
