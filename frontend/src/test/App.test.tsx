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

  it('loads product shell with Horse Racing AI brand and navigation', async () => {
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(
          JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }),
        )
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(JSON.stringify({ meetings: [], message: 'empty', count: 0 }))
      }
      if (url.includes('/race-program/five-parreh')) {
        return new Response(JSON.stringify({ events: [], message: 'none' }))
      }
      if (url.includes('/races?')) {
        return new Response(JSON.stringify({ total: 0, offset: 0, limit: 30, races: [] }))
      }
      return new Response('{}')
    })

    render(<App />)

    const nav = screen.getByRole('navigation', { name: /ناوبری اصلی/i })
    expect(screen.getAllByText(/Horse Racing AI/i).length).toBeGreaterThan(0)
    expect(within(nav).getByRole('button', { name: /Dashboard/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /Races/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /Horses/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /Predictions/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /Analytics/i })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: /System/i })).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getAllByText(/API Connected/i).length).toBeGreaterThan(0)
    })
  })

  it('shows API offline state without crashing', async () => {
    mockFetch(() => {
      throw new TypeError('network down')
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByRole('status')[0]).toHaveTextContent(/API Offline/i)
    })
  })

  it('renders race prediction flow with mocked API', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(
          JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }),
        )
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
      if (url.includes('/races/3393') && !url.includes('prediction')) {
        return new Response(
          JSON.stringify({
            race_id: 3393,
            field_size: 1,
            track: 'مشهد',
            horses: [{ horse_id: 1, horse_name: 'Test Horse' }],
          }),
        )
      }
      if (url.includes('/horses/1')) {
        return new Response(JSON.stringify({ horse_id: 1, horse_name: 'Test Horse', observation_count: 2 }))
      }
      return new Response('{}')
    })

    render(<App />)
    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /Predictions/i }))
    await waitFor(() => expect(screen.getAllByText(/API Connected/i).length).toBeGreaterThan(0))

    await user.selectOptions(screen.getByLabelText(/جلسه/i), 'm1')
    await user.selectOptions(screen.getByLabelText(/کورس/i), '3393')
    await user.click(screen.getByRole('button', { name: /تحلیل مسابقه/i }))

    await waitFor(() => {
      expect(screen.getAllByText('Test Horse').length).toBeGreaterThan(0)
      expect(screen.getAllByText(/امتیاز نسبی: 12.3/i).length).toBeGreaterThan(0)
    })
  })

  it('supports horse search and analysis', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(
          JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }),
        )
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(JSON.stringify({ meetings: [] }))
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
    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /Horses/i }))

    const inputs = screen.getAllByLabelText(/جستجوی نام اسب/i)
    await user.type(inputs[inputs.length - 1], 'دنزی')
    await user.click(await screen.findByRole('option', { name: /شیرین صحرا/i }))

    expect(await screen.findByText(/مشاهدات/i)).toBeInTheDocument()
    expect(await screen.findByText('3')).toBeInTheDocument()
  })

  it('keeps raw API response under system status only', async () => {
    const user = userEvent.setup()
    mockFetch((url) => {
      if (url.includes('/health')) {
        return new Response(
          JSON.stringify({ status: 'ok', version: '1', dataset_version: 'test', dataset_loaded: true }),
        )
      }
      if (url.includes('/race-program/upcoming')) {
        return new Response(JSON.stringify({ meetings: [], count: 0 }))
      }
      return new Response('{}')
    })

    render(<App />)
    expect(screen.queryByText(/پاسخ خام API/i)).not.toBeInTheDocument()

    await user.click(within(screen.getByRole('navigation', { name: /ناوبری اصلی/i })).getByRole('button', { name: /System/i }))
    expect(await screen.findByText(/پاسخ خام API \(پیشرفته\)/i)).toBeInTheDocument()
  })
})
