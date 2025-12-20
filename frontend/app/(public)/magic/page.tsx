'use client'

import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/lib/auth'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

export default function MagicLinkPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const toast = useToast()
  const { verifyMagicLink } = useAuth()
  const [loading, setLoading] = useState(true)
  const ranKeyRef = useRef<string>('')

  useEffect(() => {
    const mid =
      searchParams.get('mid') ||
      searchParams.get('magicId') ||
      searchParams.get('magic_id') ||
      ''
    const email = searchParams.get('email') || ''
    const code =
      searchParams.get('code') ||
      searchParams.get('c') ||
      searchParams.get('otp') ||
      ''
    const returnTo = searchParams.get('returnTo') || ''

    const run = async () => {
      setLoading(true)
      try {
        if (!code || (!mid && !email)) {
          toast.error('Invalid magic link')
          router.replace('/login')
          return
        }

        // Guard against double-submits (can happen due to re-renders / param object identity changes).
        const key = `${mid || email}::${code}`
        if (ranKeyRef.current === key) return
        ranKeyRef.current = key

        // Robust verification strategy:
        // 1) If magicId is present, try that first (pins to specific session).
        // 2) If that fails and email exists, retry with email (handles missing MAGIC# entry, etc).
        const attempts = [mid, email].filter(Boolean)
        let ok = false
        let finalReturnTo: string | undefined
        let lastErr = ''
        for (const a of attempts) {
          const res = await verifyMagicLink(a, code, true)
          if (res.ok) {
            ok = true
            finalReturnTo = res.returnTo || undefined
            break
          }
          lastErr = String(res.error || '')
        }

        if (!ok) {
          toast.error(lastErr || 'Magic link expired or invalid')
          router.replace('/login')
          return
        }

        const dest = finalReturnTo || returnTo || '/'
        // Important: use a hard navigation after setting the session cookie.
        // Next's client router can reuse prefetched unauthenticated redirects
        // (and/or AuthGuard can evaluate before the new cookie is reflected),
        // which looks like "bounced back to login" until a manual refresh.
        if (typeof window !== 'undefined') {
          window.location.replace(dest)
          return
        }
        router.replace(dest)
      } finally {
        setLoading(false)
      }
    }

    run()
  }, [router, searchParams, toast, verifyMagicLink])

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="text-sm text-gray-600">
        {loading ? 'Signing you in…' : 'Redirecting…'}
      </div>
    </div>
  )
}
