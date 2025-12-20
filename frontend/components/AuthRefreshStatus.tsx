'use client'

import { useToast } from '@/components/ui/Toast'
import Button from '@/components/ui/Button'
import { useEffect, useMemo, useRef, useState } from 'react'

type DegradedState = {
  degraded: boolean
  since: number | null // ms epoch
  lastEventAt: number | null // ms epoch
}

function getGlobalDegradedSince(): number | null {
  try {
    const g = globalThis as typeof globalThis & {
      __polaris_auth_refresh_degraded_since?: number | null
    }
    const v = g.__polaris_auth_refresh_degraded_since
    return typeof v === 'number' && v > 0 ? v : null
  } catch {
    return null
  }
}

export default function AuthRefreshStatus() {
  const toast = useToast()
  const [state, setState] = useState<DegradedState>(() => {
    const since = getGlobalDegradedSince()
    return { degraded: Boolean(since), since, lastEventAt: null }
  })
  const [dismissedUntil, setDismissedUntil] = useState<number | null>(null)
  const lastToastAtRef = useRef<number>(0)

  // Banner should appear after 30s of continuous degradation.
  const showBanner = useMemo(() => {
    if (!state.degraded || !state.since) return false
    const now = Date.now()
    if (dismissedUntil && now < dismissedUntil) return false
    return now - state.since >= 30_000
  }, [dismissedUntil, state.degraded, state.since])

  useEffect(() => {
    const onUnavailable = () => {
      const since = getGlobalDegradedSince() ?? Date.now()
      setState({ degraded: true, since, lastEventAt: Date.now() })

      // Toast at most once per 15s.
      const now = Date.now()
      if (now - lastToastAtRef.current > 15_000) {
        lastToastAtRef.current = now
        toast.info('Session refresh temporarily unavailable. Retrying…')
      }
    }

    const onRecovered = () => {
      setState({ degraded: false, since: null, lastEventAt: Date.now() })
      setDismissedUntil(null)
    }

    window.addEventListener('polaris:auth-refresh-unavailable', onUnavailable as any)
    window.addEventListener('polaris:auth-refresh-recovered', onRecovered as any)
    return () => {
      window.removeEventListener(
        'polaris:auth-refresh-unavailable',
        onUnavailable as any,
      )
      window.removeEventListener(
        'polaris:auth-refresh-recovered',
        onRecovered as any,
      )
    }
  }, [toast])

  const retry = async () => {
    try {
      const resp = await fetch('/api/session/refresh', { method: 'POST' })
      if (resp.ok) {
        // Mark recovered globally so other listeners behave consistently.
        try {
          const g = globalThis as typeof globalThis & {
            __polaris_auth_refresh_degraded_since?: number | null
          }
          g.__polaris_auth_refresh_degraded_since = null
        } catch {
          // ignore
        }
        window.dispatchEvent(new Event('polaris:auth-refresh-recovered'))
        toast.success('Session refreshed')
        return
      }
      if (resp.status === 503) {
        toast.info('Auth is still temporarily unavailable. Please try again soon.')
        return
      }
      // 401 or other: let existing logic redirect if needed on next request.
      toast.error('Unable to refresh session. Please sign in again if needed.')
    } catch {
      toast.info('Auth is still temporarily unavailable. Please try again soon.')
    }
  }

  if (!showBanner) return null

  return (
    <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="font-semibold">Session refresh is delayed</div>
        <div className="text-amber-800">
          We’re having trouble refreshing your session right now. Your work is
          safe—retry in a moment.
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <Button size="sm" variant="secondary" onClick={retry}>
          Retry
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setDismissedUntil(Date.now() + 5 * 60_000)}
        >
          Dismiss
        </Button>
      </div>
    </div>
  )
}


