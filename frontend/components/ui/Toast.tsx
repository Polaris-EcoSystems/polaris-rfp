'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

type ToastType = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  message: string
  type: ToastType
  requestId?: string
  ttlMs?: number
}

interface ToastContextValue {
  show: (
    message: string,
    type?: ToastType,
    opts?: { requestId?: string; ttlMs?: number },
  ) => void
  success: (
    message: string,
    opts?: { requestId?: string; ttlMs?: number },
  ) => void
  error: (
    message: string,
    opts?: { requestId?: string; ttlMs?: number },
  ) => void
  info: (message: string, opts?: { requestId?: string; ttlMs?: number }) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const idRef = useRef(1)

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(
    (
      message: string,
      type: ToastType = 'info',
      opts?: { requestId?: string; ttlMs?: number },
    ) => {
      const id = idRef.current++
      const ttlMs = typeof opts?.ttlMs === 'number' ? opts.ttlMs : 3000
      setToasts((prev) => [
        ...prev,
        { id, message, type, requestId: opts?.requestId, ttlMs },
      ])
      // auto dismiss
      window.setTimeout(() => remove(id), ttlMs)
    },
    [remove],
  )

  // Allow non-React code (e.g. axios interceptors) to surface an incident reference id.
  // Dispatch: window.dispatchEvent(new CustomEvent('polaris:requestId', { detail: { requestId } }))
  useEffect(() => {
    const handler = (ev: Event) => {
      const e = ev as CustomEvent
      const rid = (e?.detail as any)?.requestId
      if (typeof rid !== 'string' || !rid.trim()) return
      try {
        window.localStorage.setItem('polaris:lastRequestId', rid.trim())
        window.localStorage.setItem(
          'polaris:lastRequestIdAt',
          String(Date.now()),
        )
      } catch {
        // ignore
      }
      show(
        'Something went wrong. Include this reference if you contact support.',
        'error',
        {
          requestId: rid.trim(),
          ttlMs: 8000,
        },
      )
    }
    window.addEventListener('polaris:requestId', handler as EventListener)
    return () =>
      window.removeEventListener('polaris:requestId', handler as EventListener)
  }, [show])

  const value = useMemo<ToastContextValue>(
    () => ({
      show,
      success: (m: string, opts) => show(m, 'success', opts),
      error: (m: string, opts) => show(m, 'error', opts),
      info: (m: string, opts) => show(m, 'info', opts),
    }),
    [show],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-50 space-y-3">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={
              `max-w-sm w-80 rounded-lg shadow-lg px-4 py-3 text-sm border ` +
              (t.type === 'success'
                ? 'bg-green-50 text-green-800 border-green-200'
                : t.type === 'error'
                ? 'bg-red-50 text-red-800 border-red-200'
                : 'bg-gray-50 text-gray-800 border-gray-200')
            }
            role="status"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="break-words">{t.message}</div>
                {t.requestId ? (
                  <div className="mt-1 text-xs opacity-80 break-all">
                    Ref: <span className="font-mono">{t.requestId}</span>
                  </div>
                ) : null}
              </div>
              {t.requestId ? (
                <button
                  type="button"
                  className="shrink-0 text-xs underline"
                  onClick={() => {
                    try {
                      void navigator.clipboard.writeText(t.requestId || '')
                    } catch {
                      // ignore
                    }
                  }}
                >
                  Copy
                </button>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
