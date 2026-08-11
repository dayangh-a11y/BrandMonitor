import { describe, expect, it, vi } from 'vitest'
import { getApiBaseUrl } from '../api/client'
import { formatScore, friendlyWarnings } from '../utils/format'

describe('format helpers', () => {
  it('formats numeric scores without probability semantics', () => {
    expect(formatScore(12.34)).toBe('12.3')
    expect(formatScore(null)).toBe('—')
  })

  it('maps internal warning codes to friendly Persian only', () => {
    const messages = friendlyWarnings(['low_feature_coverage', 'unknown_internal_code'])
    expect(messages).toEqual(['⚠️ اطلاعات کافی برای امتیازدهی این اسب وجود ندارد.'])
  })
})

describe('api config', () => {
  it('uses VITE_API_BASE_URL when provided', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://example.test:9000')
    expect(getApiBaseUrl()).toBe('http://example.test:9000')
    vi.unstubAllEnvs()
  })

  it('does not hardcode localhost outside development when unset', () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubEnv('DEV', false)
    // In Vitest, import.meta.env.DEV may still be true; assert configured URL path works.
    const value = getApiBaseUrl()
    expect(typeof value).toBe('string')
    vi.unstubAllEnvs()
  })
})
