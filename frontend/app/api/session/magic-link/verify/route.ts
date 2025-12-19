import { getBackendBaseUrl } from '@/lib/server/backend'
import { sessionCookieName } from '@/lib/session'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function isProd(): boolean {
  return process.env.NODE_ENV === 'production'
}

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const remember = Boolean((body as any)?.remember)

    const upstream = await fetch(
      `${getBackendBaseUrl()}/api/auth/magic-link/verify`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body ?? {}),
        cache: 'no-store',
      },
    )

    const data = await upstream.json().catch(() => ({}))

    const token = String(data?.access_token || '').trim()
    const returnTo = typeof data?.returnTo === 'string' ? data.returnTo : null
    const expiresInRaw = data?.expires_in
    const maxAgeHint =
      typeof expiresInRaw === 'number' ? Math.floor(expiresInRaw) : null
    const fallback = remember ? 60 * 60 * 24 * 30 : 60 * 60 * 8
    const maxAge = maxAgeHint
      ? Math.max(60, Math.min(60 * 60 * 24 * 30, maxAgeHint))
      : fallback

    if (!upstream.ok) {
      return NextResponse.json(
        { ok: false, error: data?.error || data?.message || 'Verify failed' },
        { status: upstream.status || 400 },
      )
    }

    if (!token) {
      return NextResponse.json(
        { ok: false, error: 'No token returned from auth provider' },
        { status: 500 },
      )
    }

    const res = NextResponse.json({ ok: true, returnTo })
    res.cookies.set(sessionCookieName(), token, {
      httpOnly: true,
      secure: isProd(),
      sameSite: 'lax',
      path: '/',
      maxAge,
    })
    return res
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message || 'Failed to verify magic link' },
      { status: 500 },
    )
  }
}
