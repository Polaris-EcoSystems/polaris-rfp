import { sessionCookieName } from '@/lib/session'
import { NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function isProd(): boolean {
  return process.env.NODE_ENV === 'production'
}

export async function POST() {
  const res = NextResponse.json({ ok: true })
  res.cookies.set(sessionCookieName(), '', {
    httpOnly: true,
    secure: isProd(),
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  })
  return res
}


