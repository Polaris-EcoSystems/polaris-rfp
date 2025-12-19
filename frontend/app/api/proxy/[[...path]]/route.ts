import { getBackendBaseUrl } from '@/lib/server/backend'
import { sessionCookieName } from '@/lib/session'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function isProd(): boolean {
  return process.env.NODE_ENV === 'production'
}

function buildUpstreamUrl(req: Request, pathParts: string[]): string {
  const u = new URL(req.url)
  const base = getBackendBaseUrl()
  const joined = pathParts.join('/')
  const upstreamPath = joined ? `/${joined}` : '/'
  return `${base}${upstreamPath}${u.search}`
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

  const upstreamUrl = buildUpstreamUrl(req, parts)
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
