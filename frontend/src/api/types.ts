export interface HealthResponse {
  status: string
  version: string
  dataset_version: string
  ml_status?: string
  dataset_loaded?: boolean
  baseline_default?: string
}

export interface ProgramRace {
  race_id: string
  race_number?: number
  label?: string
  scheduled_start?: string | null
  status?: string
  eligible_for_prediction?: boolean
}

export interface MeetingSummary {
  meeting_id: string
  display_date?: string
  track?: string
  city?: string
  location?: string
  race_count?: number
  races?: ProgramRace[]
}

export interface UpcomingMeetingsResponse {
  days?: number
  count?: number
  meetings?: MeetingSummary[]
  message?: string | null
}

export interface MeetingDetailResponse extends MeetingSummary {
  races: ProgramRace[]
}

export interface EvidenceItem {
  metric: string
  value: unknown
}

export interface PredictionItem {
  rank: number | null
  horse_id?: number | null
  horse_name?: string | null
  score?: number | null
  probability?: null
  evidence?: EvidenceItem[]
  warnings?: string[]
}

export interface PredictionResponse {
  race_id: number
  dataset_version?: string
  ml_status?: string | null
  baseline?: string | null
  ranking_available?: boolean
  scored_horses?: number | null
  field_size?: number | null
  warnings?: string[]
  prediction: PredictionItem[]
}

export interface CompareHorseSide {
  horse_id: number
  horse_name?: string | null
  rank?: number | null
  score?: number | null
  probability?: null
  evidence?: EvidenceItem[]
  warnings?: string[]
}

export interface HorseCompareResponse {
  race_id: number
  dataset_version?: string
  comparison_type?: string
  note?: string | null
  horse_a: CompareHorseSide
  horse_b: CompareHorseSide
  selected?: string | null
  selected_horse?: CompareHorseSide | null
  evidence?: Record<string, unknown>[]
  probability?: null
}

export interface HorseSearchItem {
  horse_id: number
  horse_name: string
  breed?: string | null
  sex?: string | null
  birth_year?: number | null
}

export interface HorseSearchResponse {
  query: string
  count: number
  horses: HorseSearchItem[]
  dataset_version?: string | null
}

export interface HorseAnalysisResponse {
  horse_id: number
  horse_name?: string | null
  dataset_version?: string
  ml_status?: string | null
  observation_count?: number
  latest_race_id?: number | null
  latest_race_date?: string | null
  latest_features?: EvidenceItem[]
  warnings?: string[]
  evidence?: EvidenceItem[]
  appearances?: Record<string, unknown>[]
  note?: string | null
}

export interface FiveParrehEventSummary {
  event_id: string
  display_date?: string
  track?: string
  city?: string
  location?: string
  title?: string
  races?: ProgramRace[]
  race_ids?: string[]
}

export interface FiveParrehEventsResponse {
  count?: number
  events?: FiveParrehEventSummary[]
  message?: string | null
}

export interface FiveParrehCombinationsRequest {
  races: { race_id: string; horses: string[] }[]
  include_combinations?: boolean
  max_combinations_in_response?: number
}

export interface FiveParrehCombinationsResponse {
  total_combinations?: number
  selections_per_race?: number[]
  combinations?: unknown[] | null
  combinations_omitted?: boolean
  combinations_omission_reason?: string
  [key: string]: unknown
}

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}
