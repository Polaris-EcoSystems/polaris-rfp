import { getBackendBaseUrl } from '@/lib/server/backend'
import { sessionCookieName } from '@/lib/session'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function isProd(): boolean {
  return process.env.NODE_ENV === 'production'
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
  const { path } = await ctx.params
  const parts = Array.isArray(path) ? path : []

  if (!isAllowedProxyPath(parts)) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  if (!sameOriginGuard(req)) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
  }

  const cookieName = sessionCookieName()
  const cookieStore = await cookies()
  const token = cookieStore.get(cookieName)?.value || ''
  if (!token) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
  }

  const upstreamUrl = buildUpstreamUrl(req)
  const method = req.method.toUpperCase()

  const headers = stripHopByHopHeaders(req.headers)
  headers.set('authorization', `Bearer ${token}`)
  headers.set('x-forwarded-host', req.headers.get('host') || '')
  headers.set(
    'x-forwarded-proto',
    req.headers.get('x-forwarded-proto') || 'https',
  )

  const body =
    method === 'GET' || method === 'HEAD' ? undefined : await req.arrayBuffer()

  const ctrl = new AbortController()
  const timeoutMs = 300_000
  const t = setTimeout(() => ctrl.abort(), timeoutMs)

  const upstream = await fetch(upstreamUrl, {
    method,
    headers,
    body,
    redirect: 'manual',
    cache: 'no-store',
    signal: ctrl.signal,
  })
  clearTimeout(t)

  const resHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    const k = key.toLowerCase()
    // Never forward upstream Set-Cookie to the browser from the proxy.
    if (k === 'set-cookie') return
    resHeaders.set(key, value)
  })
  resHeaders.set('cache-control', 'no-store')

  // Rewrite redirect locations so the browser never leaves our origin (and never hits http://).
  if ([301, 302, 303, 307, 308].includes(upstream.status)) {
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

  // If backend says unauthorized, clear the browser cookie to prevent loops.
  if (upstream.status === 401) {
    res.cookies.set(cookieName, '', {
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

