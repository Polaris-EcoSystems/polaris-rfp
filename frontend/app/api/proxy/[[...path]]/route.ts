import { getBackendBaseUrl } from '@/lib/server/backend'
import {
  applyRequestIdHeader,
  getOrCreateRequestId,
} from '@/lib/server/requestId'
import { sessionCookieName, sessionIdCookieName } from '@/lib/session'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function isProd(): boolean {
  return process.env.NODE_ENV === 'production'
}

function maxAgeFromExpiresAt(expiresAt: number | null): number | null {
  if (!expiresAt) return null
  const now = Math.floor(Date.now() / 1000)
  if (expiresAt <= now) return 0
  return Math.max(60, Math.min(60 * 60 * 24 * 30, expiresAt - now))
}

async function tryRefreshWithSid(sid: string): Promise<{
  ok: boolean
  token?: string
  maxAge?: number
  status?: number
}> {
  const upstream = await fetch(
    `${getBackendBaseUrl()}/api/auth/session/refresh`,
    {
      method: 'POST',
      headers: { 'x-session-id': sid, accept: 'application/json' },
      cache: 'no-store',
    },
  )
  const data = await upstream.json().catch(() => ({}))
  if (!upstream.ok || !data?.access_token)
    return { ok: false, status: upstream.status }
  const expiresAtRaw = data?.session_expires_at
  const expiresAt =
    typeof expiresAtRaw === 'number' ? Math.floor(expiresAtRaw) : null
  const maxAge = maxAgeFromExpiresAt(expiresAt) ?? 60 * 60 * 8
  return {
    ok: true,
    token: String(data.access_token),
    maxAge,
    status: upstream.status,
  }
}

function buildUpstreamUrl(req: Request): string {
  const u = new URL(req.url)
  const base = getBackendBaseUrl()

  // Preserve the original request pathname, including trailing slash.
  // Next catch-all params drop empty segments, which can cause FastAPI to 307 redirect
  // (and those redirects can carry an http:// Location behind an ALB, triggering mixed content).
  const rawPath = u.pathname || ''
  const prefix = '/api/proxy'
  const suffix = rawPath.startsWith(prefix)
    ? rawPath.slice(prefix.length)
    : rawPath
  const upstreamPath =
    suffix && suffix.startsWith('/') ? suffix : `/${suffix || ''}`

  return `${base}${upstreamPath || '/'}${u.search}`
}

function isAllowedProxyPath(parts: string[]): boolean {
  // We only proxy:
  // - "/" health check
  // - "/api/**" (FastAPI)
  // - "/googledrive/**" (FastAPI integration)
  if (parts.length === 0) return true
  const head = String(parts[0] || '').trim()
  return head === 'api' || head === 'googledrive'
}

function stripHopByHopHeaders(h: Headers): Headers {
  const out = new Headers()
  h.forEach((value, key) => {
    const k = key.toLowerCase()
    if (
      k === 'host' ||
      k === 'connection' ||
      k === 'keep-alive' ||
      k === 'proxy-authenticate' ||
      k === 'proxy-authorization' ||
      k === 'te' ||
      k === 'trailers' ||
      k === 'transfer-encoding' ||
      k === 'upgrade' ||
      k === 'content-length' ||
      k === 'cookie'
    ) {
      return
    }
    out.set(key, value)
  })
  return out
}

function rewriteUpstreamLocationHeader(args: {
  req: Request
  upstreamUrl: string
  outHeaders: Headers
}) {
  const { req, upstreamUrl, outHeaders } = args
  const location = outHeaders.get('location') || outHeaders.get('Location')
  if (!location) return

  // Only rewrite when it is an actual redirect response. (We pass status separately below via argument.)
  // This helper expects upstream status to be checked by caller.
  try {
    const upstreamBase = new URL(getBackendBaseUrl())
    const reqUrl = new URL(req.url)

    // Resolve relative Location against upstream URL.
    const resolved = new URL(location, upstreamUrl)

    // If redirect target is NOT the backend host, drop it (avoid open redirects via proxy).
    if (resolved.host !== upstreamBase.host) {
      outHeaders.delete('location')
      outHeaders.delete('Location')
      return
    }

    const newPath = resolved.pathname + resolved.search
    const proxied = `/api/proxy${
      newPath.startsWith('/') ? newPath : `/${newPath}`
    }`

    // Keep redirect on our own origin.
    const finalUrl = new URL(proxied, `${reqUrl.protocol}//${reqUrl.host}`)
    outHeaders.set('location', `${finalUrl.pathname}${finalUrl.search}`)
  } catch {
    // If anything goes wrong, strip Location to avoid mixed-content / redirect escapes.
    outHeaders.delete('location')
    outHeaders.delete('Location')
  }
}

function sameOriginGuard(req: Request): boolean {
  const method = req.method.toUpperCase()
  const isMutating =
    method === 'POST' ||
    method === 'PUT' ||
    method === 'PATCH' ||
    method === 'DELETE'
  if (!isMutating) return true

  const host = req.headers.get('host') || ''
  if (!host) return false

  const proto = req.headers.get('x-forwarded-proto') || 'https'
  const expected = `${proto}://${host}`

  const origin = req.headers.get('origin')
  if (origin && origin !== expected) return false

  const referer = req.headers.get('referer')
  if (referer) {
    try {
      const r = new URL(referer)
      if (`${r.protocol}//${r.host}` !== expected) return false
    } catch {
      return false
    }
  }

  return true
}

async function handler(
  req: Request,
  ctx: { params: Promise<{ path?: string[] }> },
) {
  const requestId = getOrCreateRequestId(req)
  const { path } = await ctx.params
  const parts = Array.isArray(path) ? path : []

  if (!isAllowedProxyPath(parts)) {
    return NextResponse.json(
      { error: 'Not found', requestId },
      { status: 404, headers: { 'x-request-id': requestId } },
    )
  }

  if (!sameOriginGuard(req)) {
    return NextResponse.json(
      { error: 'Forbidden', requestId },
      { status: 403, headers: { 'x-request-id': requestId } },
    )
  }

  const cookieName = sessionCookieName()
  const cookieStore = await cookies()
  let token = cookieStore.get(cookieName)?.value || ''
  const sid = cookieStore.get(sessionIdCookieName())?.value || ''
  let rotatedMaxAge: number | null = null

  // If the access token cookie is missing but we still have a refreshable session,
  // refresh before proxying to the backend.
  if (!token && sid) {
    const r = await tryRefreshWithSid(sid)
    if (r.ok && r.token) {
      token = r.token
      rotatedMaxAge = typeof r.maxAge === 'number' ? r.maxAge : null
    } else if (r.status === 503) {
      const res = NextResponse.json(
        { error: 'Auth refresh temporarily unavailable', requestId },
        { status: 503, headers: { 'x-request-id': requestId } },
      )
      res.headers.set('x-polaris-auth-refresh', 'unavailable')
      return res
    }
  }

  if (!token) {
    return NextResponse.json(
      { error: 'Not authenticated', requestId },
      { status: 401, headers: { 'x-request-id': requestId } },
    )
  }

  const upstreamUrl = buildUpstreamUrl(req)
  const method = req.method.toUpperCase()
  const isMutating =
    method === 'POST' ||
    method === 'PUT' ||
    method === 'PATCH' ||
    method === 'DELETE'

  const baseHeaders = stripHopByHopHeaders(req.headers)
  applyRequestIdHeader(baseHeaders, requestId)
  baseHeaders.set('x-forwarded-host', req.headers.get('host') || '')
  baseHeaders.set(
    'x-forwarded-proto',
    req.headers.get('x-forwarded-proto') || 'https',
  )

  const body =
    method === 'GET' || method === 'HEAD' ? undefined : await req.arrayBuffer()

  const fetchUpstream = async (tok: string) => {
    const ctrl = new AbortController()
    const timeoutMs = 300_000
    const t = setTimeout(() => ctrl.abort(), timeoutMs)
    const h = new Headers(baseHeaders)
    h.set('authorization', `Bearer ${tok}`)
    try {
      return await fetch(upstreamUrl, {
        method,
        headers: h,
        body,
        redirect: 'manual',
        cache: 'no-store',
        signal: ctrl.signal,
      })
    } finally {
      clearTimeout(t)
    }
  }

  let upstream = await fetchUpstream(token)

  // If backend says unauthorized, attempt a one-time refresh and retry.
  if (upstream.status === 401 && sid) {
    const r = await tryRefreshWithSid(sid)
    if (r.ok && r.token) {
      token = r.token
      rotatedMaxAge = typeof r.maxAge === 'number' ? r.maxAge : rotatedMaxAge
      upstream = await fetchUpstream(token)
    } else if (r.status === 503) {
      // Preserve cookies/session; indicate retryable failure.
      const res = NextResponse.json(
        { error: 'Auth refresh temporarily unavailable', requestId },
        { status: 503, headers: { 'x-request-id': requestId } },
      )
      res.headers.set('x-polaris-auth-refresh', 'unavailable')
      return res
    }
  }

  const resHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    const k = key.toLowerCase()
    // Never forward upstream Set-Cookie to the browser from the proxy.
    if (k === 'set-cookie') return
    resHeaders.set(key, value)
  })
  resHeaders.set('cache-control', 'no-store')

  const isRedirect = [301, 302, 303, 307, 308].includes(upstream.status)

  // Prevent infinite redirect loops on mutating requests.
  // Browsers will auto-follow redirects for XHR/fetch POSTs in many cases; when the backend
  // is doing slash normalization redirects, our proxy rewrite can make that loop on itself.
  if (isRedirect && isMutating) {
    const location =
      upstream.headers.get('location') || upstream.headers.get('Location')
    return NextResponse.json(
      {
        error: 'Upstream redirect blocked',
        status: upstream.status,
        location: location || null,
        requestId,
      },
      { status: 502, headers: { 'x-request-id': requestId } },
    )
  }

  // Rewrite redirect locations so the browser never leaves our origin (and never hits http://).
  if (isRedirect) {
    rewriteUpstreamLocationHeader({
      req,
      upstreamUrl,
      outHeaders: resHeaders,
    })
  }

  const res = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  })

  // Always provide an incident correlation id to the client.
  // Prefer the backend's id if present; otherwise use the local id.
  const upstreamRid =
    upstream.headers.get('x-request-id') || upstream.headers.get('X-Request-Id')
  res.headers.set('x-request-id', upstreamRid || requestId)

  // If we refreshed, rotate cookies so subsequent requests don't re-401.
  if (rotatedMaxAge && token) {
    res.cookies.set(cookieName, token, {
      httpOnly: true,
      secure: isProd(),
      sameSite: 'lax',
      path: '/',
      maxAge: rotatedMaxAge,
    })
    if (sid) {
      res.cookies.set(sessionIdCookieName(), sid, {
        httpOnly: true,
        secure: isProd(),
        sameSite: 'lax',
        path: '/',
        maxAge: rotatedMaxAge,
      })
    }
  }

  // If backend still says unauthorized, clear cookies to prevent loops.
  if (upstream.status === 401) {
    res.cookies.set(cookieName, '', {
      httpOnly: true,
      secure: isProd(),
      sameSite: 'lax',
      path: '/',
      maxAge: 0,
    })
    res.cookies.set(sessionIdCookieName(), '', {
      httpOnly: true,
      secure: isProd(),
      sameSite: 'lax',
      path: '/',
      maxAge: 0,
    })
  }

  return res
}

export const GET = handler
export const POST = handler
export const PUT = handler
export const PATCH = handler
export const DELETE = handler
export const OPTIONS = handler


