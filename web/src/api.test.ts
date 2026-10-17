import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules() })

describe('API transport isolation', () => {
  it('routes demo requests locally and rejects credentials without ever fetching', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'true')
    vi.resetModules()
    const fetch = vi.fn(() => { throw new Error('network forbidden') })
    vi.stubGlobal('fetch', fetch)
    const { apiGet, apiPost } = await import('./api')
    expect(await apiGet('/auth/status')).toMatchObject({ authenticated: true, username: 'demo' })
    expect(await apiGet('/config/public')).toHaveProperty('app_name')
    await expect(apiPost('/admin/cookie', { cookie: 'placeholder' })).rejects.toThrow('演示模式')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('keeps real installations on the authenticated HTTP transport', async () => {
    vi.stubEnv('VITE_DEMO_MODE', 'false')
    vi.resetModules()
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ voice_connected: false })))
    vi.stubGlobal('fetch', fetch)
    const { apiGet } = await import('./api')
    expect(await apiGet('/voice/status')).toEqual({ voice_connected: false })
    expect(fetch).toHaveBeenCalledWith('/api/voice/status', expect.objectContaining({ credentials: 'include' }))
  })
})
