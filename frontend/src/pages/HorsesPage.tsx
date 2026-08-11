import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { HorseAnalysisResponse, HorseSearchItem } from '../api/types'
import { HorseDetailPanel } from '../components/HorseDetailPanel'
import { HorseSearchBox } from '../components/HorseSearchBox'
import { EmptyState, friendlyApiError } from '../components/Ui'

interface Props {
  initialHorseId?: number | null
}

export function HorsesPage({ initialHorseId = null }: Props) {
  const [selectedSearch, setSelectedSearch] = useState<HorseSearchItem | null>(null)
  const [analysis, setAnalysis] = useState<HorseAnalysisResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (initialHorseId == null) return
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const a = await api.horseAnalysis(initialHorseId!)
        if (cancelled) return
        setAnalysis(a)
        setSelectedSearch({
          horse_id: initialHorseId!,
          horse_name: a.horse_name ?? String(initialHorseId),
        })
      } catch (err) {
        if (!cancelled) setError(friendlyApiError(err, 'اسب یافت نشد.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [initialHorseId])

  async function selectHorse(horse: HorseSearchItem) {
    setLoading(true)
    setError(null)
    setSelectedSearch(horse)
    try {
      setAnalysis(await api.horseAnalysis(horse.horse_id))
    } catch (err) {
      setAnalysis(null)
      setError(friendlyApiError(err, 'تحلیل اسب ناموفق بود.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page-card">
      <h2 className="page-title">Horses</h2>
      <p className="page-subtitle">جستجوی فارسی/لاتین روی API موجود — بدون داده ساختگی</p>

      <HorseSearchBox onSelect={(h) => void selectHorse(h)} autoFocus />

      {error ? <p className="error-box">{error}</p> : null}

      {!analysis && !loading && !error ? (
        <EmptyState title="اسبی انتخاب نشده" body="نام اسب را جستجو کنید تا جزئیات نمایش داده شود." />
      ) : null}

      <div style={{ marginTop: '1rem' }}>
        <HorseDetailPanel loading={loading} searchMeta={selectedSearch} analysis={analysis} />
      </div>
    </section>
  )
}
