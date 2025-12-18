'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useToast } from '@/components/ui/Toast'
import { useAuth } from '@/lib/auth'

export default function MagicLinkPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const toast = useToast()
  const { verifyMagicLink } = useAuth()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const mid = searchParams.get('mid') || ''
    const email = searchParams.get('email') || ''
    const code = searchParams.get('code') || ''
    const returnTo = searchParams.get('returnTo') || ''

    const run = async () => {
      setLoading(true)
      try {
        const idOrEmail = email || mid
        if (!idOrEmail || !code) {
          toast.error('Invalid magic link')
          router.replace('/login')
          return
        }

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

