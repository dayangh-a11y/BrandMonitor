interface MiniBarsProps {
  items: { label: string; value: number }[]
  accent?: 'green' | 'gold' | 'blue'
}

export function MiniBars({ items, accent = 'blue' }: MiniBarsProps) {
  if (!items.length) return null
  const max = Math.max(...items.map((i) => Math.abs(i.value)), 1)
  return (
    <div className={`mini-bars mini-bars--${accent}`}>
      {items.map((item) => (
        <div key={item.label} className="mini-bars__row">
          <span className="mini-bars__label">{item.label}</span>
          <div className="mini-bars__track">
            <div
              className="mini-bars__fill"
              style={{ width: `${Math.max(4, (Math.abs(item.value) / max) * 100)}%` }}
            />
          </div>
          <span className="mini-bars__value">{item.value}</span>
        </div>
      ))}
    </div>
  )
}
