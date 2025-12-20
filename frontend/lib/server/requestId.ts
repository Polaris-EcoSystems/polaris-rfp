import 'server-only'

export function getOrCreateRequestId(req: Request): string {
  const h =
    req.headers.get('x-request-id') ||
    req.headers.get('X-Request-Id') ||
    req.headers.get('x-amzn-trace-id') // fallback: still useful for correlation
  if (h && String(h).trim()) return String(h).trim()
  return crypto.randomUUID()
}

export function applyRequestIdHeader(headers: Headers, requestId: string) {
  if (!requestId) return
  headers.set('x-request-id', requestId)
}
