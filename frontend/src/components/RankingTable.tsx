import type { PredictionItem, PredictionResponse } from '../api/types'
import {
  confidenceLabel,
  pickEvidence,
  relativeScoreShare,
  riskFromWarnings,
} from '../utils/metrics'
import { formatScore, friendlyWarnings, horseDisplayName } from '../utils/format'

interface RankingTableProps {
  prediction: PredictionResponse
  selectedHorseId?: number | null
  onSelectHorse: (item: PredictionItem) => void
}

export function RankingTable({ prediction, selectedHorseId, onSelectHorse }: RankingTableProps) {
  const rows = prediction.prediction ?? []
  if (!rows.length) {
    return (
      <div className="empty-box">
        <strong>رتبه‌بندی در دسترس نیست</strong>
        <p className="muted">پاسخ پیش‌بینی خالی بود.</p>
      </div>
    )
  }

  return (
    <div className="table-wrap">
      <table className="rank-table">
        <thead>
          <tr>
            <th>رتبه</th>
            <th>اسب</th>
            <th>سن</th>
            <th>نژاد</th>
            <th>مربی</th>
            <th>جوکی</th>
            <th>فرم اخیر</th>
            <th>سرعت</th>
            <th>کلاس</th>
            <th>احتمال نسبی*</th>
            <th>اطمینان</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => {
            const rankClass =
              item.rank === 1 ? 'is-gold' : item.rank === 2 ? 'is-silver' : item.rank === 3 ? 'is-bronze' : ''
            const share = relativeScoreShare(item, rows)
            const risk = riskFromWarnings(item.warnings)
            const selected = item.horse_id != null && item.horse_id === selectedHorseId
            return (
              <tr
                key={`${item.rank}-${item.horse_id ?? item.horse_name}`}
                className={`rank-row ${rankClass} ${selected ? 'is-selected' : ''}`}
                onClick={() => onSelectHorse(item)}
              >
                <td>
                  <span className={`rank-badge rank-badge--${item.rank <= 3 ? item.rank : 'n'}`}>
                    #{item.rank}
                  </span>
                </td>
                <td>
                  <div className="horse-cell">
                    <strong>{horseDisplayName(item.horse_name)}</strong>
                    {friendlyWarnings(item.warnings)[0] ? (
                      <span className={`risk-dot risk-dot--${risk}`} title={friendlyWarnings(item.warnings)[0]} />
                    ) : null}
                  </div>
                </td>
                <td>{pickEvidence(item.evidence, 'age')}</td>
                <td>{pickEvidence(item.evidence, 'breed')}</td>
                <td>{pickEvidence(item.evidence, 'trainer')}</td>
                <td>{pickEvidence(item.evidence, 'jockey')}</td>
                <td>{pickEvidence(item.evidence, 'form')}</td>
                <td>{pickEvidence(item.evidence, 'speed')}</td>
                <td>{pickEvidence(item.evidence, 'class')}</td>
                <td>
                  {share != null ? `${share.toFixed(0)}%` : '—'}
                  <div className="cell-sub">امتیاز {formatScore(item.score)}</div>
                </td>
                <td>{confidenceLabel(item, prediction.data_completeness)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="table-footnote">
        * احتمال نسبی فقط بر اساس سهم امتیاز مدل در این کورس است؛ API احتمال قطعی برنمی‌گرداند.
      </p>
    </div>
  )
}
