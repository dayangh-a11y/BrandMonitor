import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { HorseSearchItem } from '../api/types'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { friendlyApiError } from './Ui'

interface HorseSearchBoxProps {
  onSelect: (horse: HorseSearchItem) => void
  placeholder?: string
  autoFocus?: boolean
}

export function HorseSearchBox({
  onSelect,
  placeholder = 'جستجوی نام اسب...',
  autoFocus = false,
}: HorseSearchBoxProps) {
  const [query, setQuery] = useState('')
  const debounced = useDebouncedValue(query.trim(), 280)
  const [results, setResults] = useState<HorseSearchItem[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [empty, setEmpty] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function run() {
      if (!debounced) {
        setResults([])
        setEmpty(false)
        setError(null)
        return
      }
      setLoading(true)
      setError(null)
      setEmpty(false)
      try {
        const res = await api.searchHorses(debounced)
        if (cancelled) return
        setResults(res.horses ?? [])
        setEmpty(!(res.horses ?? []).length)
        setOpen(true)
      } catch (err) {
        if (cancelled) return
        setResults([])
        setError(friendlyApiError(err, 'جستجو ناموفق بود.'))
        setOpen(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [debounced])

  return (
    <div className="search-box" ref={rootRef}>
      <label className="search-box__label">
        <span className="sr-only">جستجوی نام اسب</span>
        <input
          type="search"
          value={query}
          autoFocus={autoFocus}
          placeholder={placeholder}
          aria-label="جستجوی نام اسب"
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => {
            if (results.length || empty || error) setOpen(true)
          }}
        />
        {loading ? <span className="search-box__spinner" aria-hidden /> : null}
      </label>

      {open && (results.length || empty || error) ? (
        <div className="search-dropdown" role="listbox">
          {error ? <div className="search-dropdown__msg error">{error}</div> : null}
          {empty && !error ? (
            <div className="search-dropdown__msg">اسبی با این نام پیدا نشد.</div>
          ) : null}
          {results.map((horse) => (
            <button
              key={horse.horse_id}
              type="button"
              className="search-dropdown__item"
              role="option"
              onClick={() => {
                onSelect(horse)
                setQuery(horse.horse_name)
                setOpen(false)
              }}
            >
              <strong>{horse.horse_name}</strong>
              <span className="muted">
                {[horse.breed, horse.sex, horse.birth_year].filter(Boolean).join(' · ') || 'در دسترس نیست'}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
