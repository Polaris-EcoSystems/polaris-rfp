import 'server-only'

function normalizeBackendBaseUrl(input: string): string {
  const raw = String(input || '').trim()
  if (!raw) return ''
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw
  // If a hostname was provided, default to https (production).
  if (raw.includes('localhost') || raw.includes('127.0.0.1'))
    return `http://${raw}`
  return `https://${raw}`
}

export function getBackendBaseUrl(): string {
  const fromEnv =
    process.env.API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    'https://api.rfp.polariseco.com'
  const base = normalizeBackendBaseUrl(fromEnv)
  if (!base) throw new Error('Missing backend base URL (API_BASE_URL)')
  return base.replace(/\/+$/, '')
}



