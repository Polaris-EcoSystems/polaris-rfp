'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'

const ALLOWED_EMAIL_DOMAIN = String(
  process.env.NEXT_PUBLIC_ALLOWED_EMAIL_DOMAIN || 'polariseco.com',
)
  .trim()
  .toLowerCase()

export function normalizeEmail(raw: string): string {
  return String(raw || '')
    .trim()
    .toLowerCase()
}

export function isAllowedEmail(raw: string): boolean {
  const email = normalizeEmail(raw)
  const parts = email.split('@')
  if (parts.length !== 2) return false
  const domain = parts[1]
  return domain === ALLOWED_EMAIL_DOMAIN
}

interface User {
  username: string
  email?: string
}

interface AuthContextType {
  user: User | null
  requestMagicLink: (
    email: string,
    opts?: { username?: string; returnTo?: string },
  ) => Promise<boolean>
  verifyMagicLink: (
    magicId: string,
    code: string,
    remember?: boolean,
  ) => Promise<{ ok: boolean; returnTo?: string; error?: string }>
  logout: () => Promise<void>
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

async function fetchJson<T = any>(
  input: string,
  init?: RequestInit,
): Promise<{ ok: boolean; status: number; data?: T }> {
  const resp = await fetch(input, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  const status = resp.status
  const data = (await resp.json().catch(() => undefined)) as any
  return { ok: resp.ok, status, data }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void fetchCurrentUser()
  }, [])

  const fetchCurrentUser = async () => {
    try {
      const resp = await fetch('/api/session/me', { cache: 'no-store' })
      if (!resp.ok) {
        setUser(null)
        return
      }
      const u = await resp.json().catch(() => null)
      setUser(u as any)
    } catch (error) {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  const login = async (
    email: string,
    opts?: { username?: string; returnTo?: string },
  ): Promise<boolean> => {
    try {
      const normalizedEmail = normalizeEmail(email)
      if (!isAllowedEmail(normalizedEmail)) return false
      const resp = await fetchJson('/api/session/magic-link/request', {
        method: 'POST',
        body: JSON.stringify({
          email: normalizedEmail,
          username: opts?.username,
          returnTo: opts?.returnTo,
        }),
      })
      if (!resp.ok) return false
      return true
    } catch (_e) {
      return false
    }
  }

  const verifyMagicLink = async (
    magicIdOrEmail: string,
    code: string,
    remember: boolean = true,
  ): Promise<{ ok: boolean; returnTo?: string; error?: string }> => {
    try {
      const val = String(magicIdOrEmail || '').trim()
      const payload: any = { code }
      if (val.includes('@')) payload.email = val
      else payload.magicId = val

      payload.remember = Boolean(remember)
      const resp = await fetchJson<{
        ok: boolean
        returnTo?: string | null
        error?: string
      }>('/api/session/magic-link/verify', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (!resp.ok || !resp.data?.ok) {
        return {
          ok: false,
          error:
            (typeof resp.data?.error === 'string' && resp.data.error) ||
            'Invalid or expired magic link',
        }
      }
      await fetchCurrentUser()
      return {
        ok: true,
        returnTo:
          typeof resp.data?.returnTo === 'string'
            ? resp.data.returnTo
            : undefined,
      }
    } catch (_e) {
      return { ok: false, error: 'Magic link verification failed' }
    }
  }

  const logout = async () => {
    try {
      await fetch('/api/session/logout', { method: 'POST' })
    } catch {
      // ignore
    }
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        requestMagicLink: login,
        verifyMagicLink,
        logout,
        loading,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
