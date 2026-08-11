import type { HorseAnalysisResponse, HorseSearchItem, PredictionItem } from '../api/types'
import { pickEvidence } from '../utils/metrics'
import { formatEvidence, formatScore, friendlyWarnings, horseDisplayName } from '../utils/format'
import { EmptyState, SkeletonBlock } from './Ui'
import { MiniBars } from './MiniBars'

interface HorseDetailPanelProps {
  loading?: boolean
  searchMeta?: HorseSearchItem | null
  analysis?: HorseAnalysisResponse | null
  predictionItem?: PredictionItem | null
  error?: string | null
}

export function HorseDetailPanel({
  loading,
  searchMeta,
  analysis,
  predictionItem,
  error,
}: HorseDetailPanelProps) {
  if (loading) return <SkeletonBlock rows={4} />
  if (error) return <p className="error-box">{error}</p>
  if (!analysis && !predictionItem) {
    return (
      <EmptyState
        title="اسبی انتخاب نشده"
        body="از جدول رتبه‌بندی یا جستجو یک اسب را انتخاب کنید."
      />
    )
  }

  const name = horseDisplayName(analysis?.horse_name ?? predictionItem?.horse_name ?? searchMeta?.horse_name)
  const evidence = analysis?.evidence ?? predictionItem?.evidence ?? []
  const features = analysis?.latest_features ?? []
  const warnings = friendlyWarnings(analysis?.warnings ?? predictionItem?.warnings)
  const age =
    searchMeta?.birth_year != null
      ? String(new Date().getFullYear() - searchMeta.birth_year)
      : pickEvidence(evidence, 'age')
  const breed = searchMeta?.breed ?? pickEvidence(evidence, 'breed')
  const trainer = pickEvidence(evidence, 'trainer')
  const jockey = pickEvidence(evidence, 'jockey')
  const winRate = pickEvidence(evidence, 'win_rate')
  const avgFinish = pickEvidence(evidence, 'avg_finish')
  const speedSeries = [...evidence, ...features]
    .map((e) => ({ label: String(e.metric), value: Number(e.value) }))
    .filter((x) => !Number.isNaN(x.value))
    .slice(0, 6)

  const strengths = evidence
    .filter((e) => {
      const n = Number(e.value)
      return !Number.isNaN(n) && n > 0
    })
    .slice(0, 3)
    .map((e) => `${e.metric}: ${e.value}`)
  const weaknesses = warnings

  return (
    <div className="detail-panel">
      <header className="detail-panel__head">
        <div>
          <h3>{name}</h3>
          <p className="muted">
            {[
              breed !== 'در دسترس نیست' ? breed : null,
              age !== 'در دسترس نیست' ? `سن ${age}` : null,
              searchMeta?.sex,
            ]
              .filter(Boolean)
              .join(' · ') || 'در دسترس نیست'}
          </p>
        </div>
        {predictionItem?.rank != null ? (
          <span className={`rank-badge rank-badge--${predictionItem.rank <= 3 ? predictionItem.rank : 'n'}`}>
            #{predictionItem.rank}
          </span>
        ) : null}
      </header>

      <div className="detail-grid">
        <div><span className="meta-k">مربی</span><strong>{trainer}</strong></div>
        <div><span className="meta-k">جوکی</span><strong>{jockey}</strong></div>
        <div><span className="meta-k">نرخ برد</span><strong>{winRate}</strong></div>
        <div><span className="meta-k">میانگین پایان</span><strong>{avgFinish}</strong></div>
        <div><span className="meta-k">امتیاز پیش‌بینی</span><strong>{formatScore(predictionItem?.score)}</strong></div>
        <div>
          <span className="meta-k">مشاهدات</span>
          <strong>{analysis?.observation_count ?? 'در دسترس نیست'}</strong>
        </div>
      </div>

      {analysis?.latest_race_date ? (
        <p className="muted">آخرین مسابقه: {analysis.latest_race_date}</p>
      ) : null}
      {analysis?.note ? <p className="note-text">{analysis.note}</p> : null}

      <div className="detail-split">
        <div>
          <h4>نقاط قوت (از داده)</h4>
          {strengths.length ? (
            <ul className="bullet-list">{strengths.map((s) => <li key={s}>{s}</li>)}</ul>
          ) : (
            <p className="muted">شاخص مثبت عددی در پاسخ فعلی نیست.</p>
          )}
        </div>
        <div>
          <h4>نقاط ضعف / هشدار</h4>
          {weaknesses.length ? (
            <ul className="bullet-list warn">{weaknesses.map((s) => <li key={s}>{s}</li>)}</ul>
          ) : (
            <p className="muted">هشداری گزارش نشده.</p>
          )}
        </div>
      </div>

      {speedSeries.length ? (
        <div>
          <h4>شاخص‌های عددی</h4>
          <MiniBars items={speedSeries} />
        </div>
      ) : null}

      {formatEvidence(evidence).length ? (
        <div>
          <h4>شواهد</h4>
          {formatEvidence(evidence).slice(0, 12).map((line) => (
            <p key={line} className="evidence-line">{line}</p>
          ))}
        </div>
      ) : null}

      {(analysis?.appearances ?? []).length ? (
        <div>
          <h4>نتایج اخیر</h4>
          <ul className="appearance-list">
            {(analysis?.appearances ?? []).slice(0, 8).map((row, idx) => (
              <li key={idx}>
                {[
                  row.race_date ?? row.date,
                  row.track,
                  row.finish_position != null ? `مقام ${String(row.finish_position)}` : null,
                ]
                  .filter(Boolean)
                  .map(String)
                  .join(' · ') || JSON.stringify(row)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
