import axios from 'axios'

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error && error.message ? error.message : fallback
  }
  const detail: unknown = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map(item => typeof item === 'object' && item !== null && 'msg' in item ? item.msg : null)
      .filter((message): message is string => typeof message === 'string')
    if (messages.length) return messages.join(' ')
  }
  if (error.response) return `${fallback} (HTTP ${error.response.status}).`
  return fallback
}
