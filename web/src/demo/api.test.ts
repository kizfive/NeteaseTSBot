import { beforeEach, describe, expect, it, vi } from 'vitest'
import { demoRequest, resetDemo } from './api'

const get = (path: string): any => demoRequest(path)
const send = (path: string, body: unknown = {}, method = 'POST'): any => demoRequest(path, { method, body: JSON.stringify(body) })

beforeEach(() => { vi.useRealTimers(); resetDemo() })

describe('offline demo behavior', () => {
  it('searches sample tracks and updates the queue without a network request', () => {
    const fetch = vi.fn(() => { throw new Error('network forbidden') })
    vi.stubGlobal('fetch', fetch)
    try {
      const songs = get('/search?keywords=Weekend').raw.result.songs
      expect(songs).toHaveLength(1)
      const added = send('/queue/netease', { track_id: String(songs[0].id), play_now: true })
      expect(get('/voice/status').now_playing_title).toBe(songs[0].name)
      expect(get('/voice/status').track_id).toBe(added.id)
      expect(get('/queue').find((item: any) => item.id === added.id).duration).toBe(172)
      expect(get('/voice/status').duration).toBe(172)
      expect(get('/queue')).toHaveLength(4)
      expect(fetch).not.toHaveBeenCalled()
    } finally { vi.unstubAllGlobals() }
  })

  it('keeps playback position paused and resumes the simulated clock', () => {
    vi.useFakeTimers()
    send('/voice/play')
    vi.advanceTimersByTime(3000)
    expect(get('/voice/status').current_time).toBe(27)
    send('/voice/pause')
    vi.advanceTimersByTime(3000)
    expect(get('/voice/status').current_time).toBe(27)
    send('/voice/seek', { time: 50 })
    send('/voice/play')
    vi.advanceTimersByTime(1000)
    expect(get('/voice/status').current_time).toBe(51)
  })

  it('handles reordering, removing the current item and clearing the queue', () => {
    send('/queue/reorder', { track_ids: [3, 2, 1] })
    expect(get('/queue').map((item: any) => item.id)).toEqual([3, 2, 1])
    expect(() => send('/queue/reorder', { track_ids: [1, 1, 2] })).toThrow('无效')
    send('/queue/1', {}, 'DELETE')
    expect(get('/voice/status').track_id).toBe(3)
    send('/queue', {}, 'DELETE')
    expect(get('/queue')).toEqual([])
    expect(get('/voice/status').state).toBe('idle')
  })

  it('returns independent response data and resets changed state', () => {
    get('/queue')[0].title = 'mutated'
    expect(get('/queue')[0].title).not.toBe('mutated')
    send('/admin/settings', { values: { 'voice.ts3_host': 'changed.example' }, apply: false }, 'PUT')
    expect(get('/admin/settings').apply_pending).toBe(true)
    resetDemo()
    expect(get('/admin/settings').fields.find((field: any) => field.key === 'voice.ts3_host').value).toBe('ts.example.com')
  })

  it('rejects real credentials, uploads and unknown routes instead of falling through to fetch', () => {
    expect(() => send('/admin/cookie', { cookie: 'do-not-send' })).toThrow('演示模式')
    expect(() => send('/auth/login', { password: 'do-not-send' })).toThrow('演示模式')
    expect(() => send('/admin/settings', { values: { 'voice.ts3_server_password': 'secret' } }, 'PUT')).toThrow('凭据')
    expect(() => send('/admin/settings', { values: { constructor: 'invalid' } }, 'PUT')).toThrow('凭据')
    expect(() => send('/admin/assets/web-app-icon', {}, 'PUT')).toThrow('演示模式')
    expect(() => get('/unknown')).toThrow('演示模式')
  })
})
