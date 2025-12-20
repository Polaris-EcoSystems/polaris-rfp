'use client'

import { userProfileApi } from '@/lib/api'
import { usePathname, useRouter } from 'next/navigation'
import { ReactNode, useEffect, useState } from 'react'
import { useAuth } from '../lib/auth'

export default function AuthGuard({
  children,
  redirectTo = '/login',
}: {
  children: ReactNode
  redirectTo?: string
}) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [profileChecked, setProfileChecked] = useState(false)

  useEffect(() => {
    if (!loading && !user) {
      // Not authenticated -> redirect to login
      router.replace(redirectTo)
    }
  }, [loading, user, router, redirectTo])

  useEffect(() => {
    if (loading) return
    if (!user) return

    // Don't gate the onboarding page itself.
    if (pathname === '/onboarding') {
      setProfileChecked(true)
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        const resp = await userProfileApi.get()
        const isComplete = Boolean(resp?.data?.isComplete)
        if (!isComplete && !cancelled) {
          router.replace('/onboarding')
          return
        }
      } catch {
        // If profile API fails, do not hard-block the app.
      } finally {
        if (!cancelled) setProfileChecked(true)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [loading, user, pathname, router])

  // While loading auth state, avoid flashing protected content
  if (loading || !user) return null
  if (!profileChecked) return null

  return <>{children}</>
}
