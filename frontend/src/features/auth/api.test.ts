import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../services/apiClient', () => ({
  apiClient: { post: vi.fn() },
}))

import { apiClient } from '../../services/apiClient'
import { refresh } from './api'

describe('refresh token API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset()
  })

  it('shares one in-flight refresh request across concurrent startup callers', async () => {
    let resolveRefresh!: (response: { data: { access_token: string; token_type: 'bearer'; expires_in: number } }) => void
    vi.mocked(apiClient.post).mockReturnValueOnce(new Promise(resolve => {
      resolveRefresh = resolve
    }) as never)

    const first = refresh()
    const second = refresh()
    expect(apiClient.post).toHaveBeenCalledTimes(1)
    expect(apiClient.post).toHaveBeenCalledWith('/auth/refresh', {})

    resolveRefresh({ data: { access_token: 'fresh-access-token', token_type: 'bearer', expires_in: 900 } })
    await expect(first).resolves.toEqual({
      access_token: 'fresh-access-token',
      token_type: 'bearer',
      expires_in: 900,
    })
    await expect(second).resolves.toEqual({
      access_token: 'fresh-access-token',
      token_type: 'bearer',
      expires_in: 900,
    })

    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { access_token: 'next-access-token', token_type: 'bearer', expires_in: 900 },
    } as never)
    await expect(refresh()).resolves.toMatchObject({ access_token: 'next-access-token' })
    expect(apiClient.post).toHaveBeenCalledTimes(2)
  })

  it('clears the in-flight request after rejection so a later retry can run', async () => {
    vi.mocked(apiClient.post)
      .mockRejectedValueOnce(new Error('refresh rejected'))
      .mockResolvedValueOnce({
        data: { access_token: 'retry-access-token', token_type: 'bearer', expires_in: 900 },
      } as never)

    await expect(refresh()).rejects.toThrow('refresh rejected')
    await expect(refresh()).resolves.toMatchObject({ access_token: 'retry-access-token' })
    expect(apiClient.post).toHaveBeenCalledTimes(2)
  })
})
