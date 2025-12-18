'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'
import api from './api'

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
  ) => Promise<{ ok: boolean; returnTo?: string }>
  setToken: (token: string, remember?: boolean) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function readStoredToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('token') || sessionStorage.getItem('token')
}

function storeToken(token: string, remember: boolean) {
  if (typeof window === 'undefined') return
  if (remember) {
    localStorage.setItem('token', token)
    sessionStorage.removeItem('token')
  } else {
    sessionStorage.setItem('token', token)
    localStorage.removeItem('token')
  }
}

function clearStoredToken() {
  if (typeof window === 'undefined') return
  localStorage.removeItem('token')
  sessionStorage.removeItem('token')
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = readStoredToken()
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
      fetchCurrentUser()
    } else {
      setLoading(false)
    }
  }, [])

  const fetchCurrentUser = async () => {
    try {
      const response = await api.get(`/api/auth/me`)
      setUser(response.data)
    } catch (error) {
      clearStoredToken()
      delete api.defaults.headers.common['Authorization']
    } finally {
      setLoading(false)
    }
  }

  const setToken = async (token: string, remember: boolean = true) => {
    try {
      storeToken(token, remember)
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
      // fetch and set current user
      await fetchCurrentUser()
    } catch (err) {
      console.error('setToken error', err)
    }
  }

  const login = async (
    email: string,
    opts?: { username?: string; returnTo?: string },
  ): Promise<boolean> => {
    try {
      await api.post(`/api/auth/magic-link/request`, {
        email,
        username: opts?.username,
        returnTo: opts?.returnTo,
      })
      return true
    } catch (_e) {
      return false
    }
  }

  const verifyMagicLink = async (
    magicIdOrEmail: string,
    code: string,
    remember: boolean = true,
  ): Promise<{ ok: boolean; returnTo?: string }> => {
    try {
      const val = String(magicIdOrEmail || '').trim()
      const payload: any = { code }
      if (val.includes('@')) payload.email = val
      else payload.magicId = val

      const resp = await api.post(`/api/auth/magic-link/verify`, payload)
      const token = resp.data?.access_token
      const returnTo = resp.data?.returnTo
      if (!token) return { ok: false }
      await setToken(token, remember)
      return { ok: true, returnTo }
    } catch (_e) {
      return { ok: false }
    }
  }

  const logout = () => {
    clearStoredToken()
    delete api.defaults.headers.common['Authorization']
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        requestMagicLink: login,
        verifyMagicLink,
        setToken,
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
