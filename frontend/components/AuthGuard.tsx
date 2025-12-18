'use client'

import { useRouter } from 'next/navigation'
import { ReactNode, useEffect } from 'react'
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

  useEffect(() => {
    if (!loading && !user) {
      // Not authenticated -> redirect to login
      router.replace(redirectTo)
    }
  }, [loading, user, router, redirectTo])

  // While loading auth state, avoid flashing protected content
  if (loading || !user) return null

  return <>{children}</>
}
