import type {
  FiveParrehCombinationsRequest,
  FiveParrehCombinationsResponse,
  FiveParrehEventsResponse,
  FiveParrehEventSummary,
  HealthResponse,
  HorseAnalysisResponse,
  HorseCompareResponse,
  HorseSearchResponse,
  MeetingDetailResponse,
  PredictionResponse,
  UpcomingMeetingsResponse,
} from './types'
import { ApiError } from './types'

export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL?.trim()
  if (raw) return raw.replace(/\/$/, '')
  // Local development convenience only — production builds must set VITE_API_BASE_URL.
  if (import.meta.env.DEV) return 'http://127.0.0.1:8000'
  return ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBaseUrl()
  if (!base) {
    throw new ApiError('آدرس API پیکربندی نشده است (VITE_API_BASE_URL).', 0, null)
  }
  const url = `${base}${path}`
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new ApiError('API در دسترس نیست', 0, null)
  }

  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${response.status}`
    throw new ApiError(detail, response.status, body)
  }

  return body as T
}

export const api = {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/health')
  },

  upcomingMeetings(days = 7): Promise<UpcomingMeetingsResponse> {
    return request<UpcomingMeetingsResponse>(`/race-program/upcoming?days=${days}`)
  },

  meetingDetail(meetingId: string): Promise<MeetingDetailResponse> {
    return request<MeetingDetailResponse>(
      `/race-program/meetings/${encodeURIComponent(meetingId)}`,
    )
  },

  racePrediction(raceId: string, baseline = 'A'): Promise<PredictionResponse> {
    return request<PredictionResponse>(
      `/races/${encodeURIComponent(raceId)}/prediction?baseline=${encodeURIComponent(baseline)}`,
    )
  },

  compareHorses(
    raceId: string,
    horseA: number,
    horseB: number,
    baseline = 'A',
  ): Promise<HorseCompareResponse> {
    const params = new URLSearchParams({
      horse_a: String(horseA),
      horse_b: String(horseB),
      baseline,
    })
    return request<HorseCompareResponse>(
      `/races/${encodeURIComponent(raceId)}/compare?${params.toString()}`,
    )
  },

  searchHorses(name: string, limit = 20): Promise<HorseSearchResponse> {
    const params = new URLSearchParams({ name, limit: String(limit) })
    return request<HorseSearchResponse>(`/horses/search?${params.toString()}`)
  },

  horseAnalysis(horseId: number): Promise<HorseAnalysisResponse> {
    return request<HorseAnalysisResponse>(`/horses/${horseId}`)
  },

  listFiveParrehEvents(): Promise<FiveParrehEventsResponse> {
    return request<FiveParrehEventsResponse>('/race-program/five-parreh')
  },

  getFiveParrehEvent(eventId: string): Promise<FiveParrehEventSummary> {
    return request<FiveParrehEventSummary>(
      `/race-program/five-parreh/${encodeURIComponent(eventId)}`,
    )
  },

  generateFiveParrehCombinations(
    body: FiveParrehCombinationsRequest,
  ): Promise<FiveParrehCombinationsResponse> {
    return request<FiveParrehCombinationsResponse>('/five-parreh/combinations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        include_combinations: false,
        ...body,
      }),
    })
  },
}
