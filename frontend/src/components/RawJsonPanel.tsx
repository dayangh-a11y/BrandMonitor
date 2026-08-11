import { useState } from 'react'

interface RawJsonPanelProps {
  data: unknown
  title?: string
}

export function RawJsonPanel({ data, title = 'مشاهده پاسخ خام API' }: RawJsonPanelProps) {
  const [open, setOpen] = useState(false)

  if (data === null || data === undefined) {
    return null
  }

  return (
    <details
      className="raw-json"
      open={open}
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
    >
      <summary>{title}</summary>
      <pre className="raw-json__body">{JSON.stringify(data, null, 2)}</pre>
    </details>
  )
}
