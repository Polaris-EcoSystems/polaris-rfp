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
    const mid = searchParams.get('mid') || ''
    const email = searchParams.get('email') || ''
    const code = searchParams.get('code') || ''
    const returnTo = searchParams.get('returnTo') || ''

    const run = async () => {
      setLoading(true)
      try {
        // Prefer magicId (mid) when present: it pins to the exact auth session.
        // Email-based lookup can fail if multiple magic links were requested quickly.
        const idOrEmail = mid || email
        if (!idOrEmail || !code) {
          toast.error('Invalid magic link')
          router.replace('/login')
          return
        }

        // Guard against double-submits (can happen due to re-renders / param object identity changes).
        const key = `${idOrEmail}::${code}`
        if (ranKeyRef.current === key) return
        ranKeyRef.current = key

        const res = await verifyMagicLink(idOrEmail, code, true)
        if (!res.ok) {
          toast.error('Magic link expired or invalid')
          router.replace('/login')
          return
        }

        const dest = res.returnTo || returnTo || '/'
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
