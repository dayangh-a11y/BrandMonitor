import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

function mockFetch(handler: (url: string) => Response | Promise<Response>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
    const url =
      typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    return Promise.resolve(handler(url))
  })
}

describe('App dashboard', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('loads product shell with Persian brand and navigation', async () => {
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }))
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(JSON.stringify({ meetings: [], message: 'empty', count: 0 }))
      }
      if (url.includes('/race-program/five-parreh')) {
        return new Response(JSON.stringify({ events: [], message: 'none' }))
      }
      return new Response('{}')
    })

    render(<App />)

    const nav = screen.getByRole('navigation', { name: /ناوبری اصلی/i })
    expect(screen.getByText(/والدین اسب مسابقه باارزش/i)).toBeInTheDocument()
    expect(screen.getByText('تحلیل و پیش‌بینی مسابقات اسب')).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /^داشبورد$/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /^پیش‌بینی کورس$/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /^پنج‌پره$/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /^اسب مقابل اسب$/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /^تحلیل اسب$/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /وضعیت سیستم/i })).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText(/API متصل/i)).toBeInTheDocument()
    })
  })

  it('shows API offline state without crashing', async () => {
    mockFetch(() => {
      throw new TypeError('network down')
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/API قطع/i)
    })
  })

  it('renders race prediction flow with mocked API', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }))
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(
          JSON.stringify({
            count: 1,
            meetings: [
              {
                meeting_id: 'm1',
                display_date: 'جمعه',
                track: 'مشهد',
                location: 'مشهد',
                races: [{ race_id: '3393', race_number: 1, label: 'کورس ۱' }],
              },
            ],
          }),
        )
      }
      if (url.includes('/race-program/meetings/m1')) {
        return new Response(
          JSON.stringify({
            meeting_id: 'm1',
            display_date: 'جمعه',
            track: 'مشهد',
            races: [{ race_id: '3393', race_number: 1, label: 'کورس ۱' }],
          }),
        )
      }
      if (url.includes('/races/3393/prediction')) {
        return new Response(
          JSON.stringify({
            race_id: 3393,
            prediction: [{ rank: 1, horse_id: 1, horse_name: 'Test Horse', score: 12.3 }],
          }),
        )
      }
      if (url.includes('/race-program/five-parreh')) {
        return new Response(JSON.stringify({ events: [] }))
      }
      return new Response('{}')
    })

    render(<App />)
    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /^پیش‌بینی کورس$/i }))
    await waitFor(() => expect(screen.getByText(/API متصل/i)).toBeInTheDocument())

    await user.selectOptions(screen.getByLabelText(/جلسه/i), 'm1')
    await user.selectOptions(screen.getByLabelText(/^کورس$/i), '3393')
    await user.click(screen.getByRole('button', { name: /شروع پیش‌بینی/i }))

    await waitFor(() => {
      expect(screen.getByText('Test Horse')).toBeInTheDocument()
      expect(screen.getByText(/امتیاز: 12.3/i)).toBeInTheDocument()
    })
  })

  it('validates horse vs horse same-horse selection', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }))
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(
          JSON.stringify({
            meetings: [{ meeting_id: 'm1', display_date: 'جمعه', track: 'مشهد', location: 'مشهد' }],
          }),
        )
      }
      if (url.includes('/race-program/meetings/m1')) {
        return new Response(
          JSON.stringify({
            meeting_id: 'm1',
            races: [{ race_id: '3393', race_number: 1, label: 'کورس ۱' }],
          }),
        )
      }
      if (url.includes('/races/3393/prediction')) {
        return new Response(
          JSON.stringify({
            race_id: 3393,
            prediction: [
              { rank: 1, horse_id: 10, horse_name: 'A' },
              { rank: 2, horse_id: 20, horse_name: 'B' },
            ],
          }),
        )
      }
      if (url.includes('/race-program/five-parreh')) {
        return new Response(JSON.stringify({ events: [] }))
      }
      return new Response('{}')
    })

    render(<App />)
    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /^اسب مقابل اسب$/i }))

    await user.selectOptions(screen.getByLabelText(/جلسه/i), 'm1')
    await user.selectOptions(screen.getByLabelText(/^کورس$/i), '3393')
    await user.selectOptions(screen.getByLabelText(/اسب A/i), '10')
    await user.selectOptions(screen.getByLabelText(/اسب B/i), '10')
    await user.click(screen.getByRole('button', { name: /^مقایسه$/i }))

    expect(await screen.findByText(/دو اسب باید متفاوت باشند/i)).toBeInTheDocument()
  })

  it('does not fabricate five-parreh events when API returns empty', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }))
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(JSON.stringify({ meetings: [] }))
      }
      if (url.includes('/race-program/five-parreh')) {
        return new Response(
          JSON.stringify({ events: [], message: 'هیچ پنج‌پره آینده‌ای در داده فعلی موجود نیست.' }),
        )
      }
      return new Response('{}')
    })

    render(<App />)
    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /^پنج‌پره$/i }))

    expect(await screen.findByText(/هیچ پنج‌پره آینده‌ای در داده فعلی موجود نیست/i)).toBeInTheDocument()
  })

  it('supports horse search and analysis', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }))
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(JSON.stringify({ meetings: [] }))
      }
      if (url.includes('/race-program/five-parreh')) {
        return new Response(JSON.stringify({ events: [] }))
      }
      if (url.includes('/horses/search')) {
        return new Response(
          JSON.stringify({
            query: 'دنزی',
            count: 1,
            horses: [{ horse_id: 3239, horse_name: 'شیرین صحرا' }],
          }),
        )
      }
      if (url.includes('/horses/3239')) {
        return new Response(
          JSON.stringify({
            horse_id: 3239,
            horse_name: 'شیرین صحرا',
            observation_count: 3,
            evidence: [{ metric: 'breed', value: 'Thoroughbred' }],
          }),
        )
      }
      return new Response('{}')
    })

    render(<App />)
    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /^تحلیل اسب$/i }))

    await user.type(screen.getByLabelText(/نام اسب/i), 'دنزی')
    await user.click(screen.getByRole('button', { name: /^جستجو$/i }))

    await user.click(await screen.findByRole('button', { name: /شیرین صحرا/i }))

    expect(await screen.findByText(/تعداد مشاهده: 3/i)).toBeInTheDocument()
  })

  it('keeps raw API response under system status only', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }))
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(JSON.stringify({ meetings: [], count: 0 }))
      }
      return new Response('{}')
    })

    render(<App />)
    expect(screen.queryByText(/پاسخ خام API/i)).not.toBeInTheDocument()

    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /وضعیت سیستم/i }))
    expect(await screen.findByText(/پاسخ خام API \(پیشرفته\)/i)).toBeInTheDocument()
  })
})
