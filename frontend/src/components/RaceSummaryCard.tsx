const NA = 'در دسترس نیست'

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
    ['روز مسابقه', props.raceDay || NA],
    ['پیست / شهر', props.track || NA],
    ['کورس (Heat)', props.heat || NA],
    ['مسافت', props.distance != null && props.distance !== '' ? String(props.distance) : NA],
    ['تعداد اسب', props.horseCount != null ? String(props.horseCount) : NA],
    ['کلاس', props.raceClass || NA],
    ['نژاد', props.breed || NA],
    ['سطح', props.surface || NA],
  ]

  return (
    <div className="summary-card">
      <h3>خلاصه مسابقه</h3>
      <dl className="summary-dl">
        {rows.map(([k, v]) => (
          <div key={k} className="summary-dl__row">
            <dt>{k}</dt>
            <dd className={v === NA ? 'is-na' : undefined}>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
