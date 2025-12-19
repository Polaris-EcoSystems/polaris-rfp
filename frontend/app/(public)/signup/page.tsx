'use client'

import { useToast } from '@/components/ui/Toast'
import { isAllowedEmail, normalizeEmail, useAuth } from '@/lib/auth'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import React, { useState } from 'react'

export default function SignupPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { requestMagicLink, user, loading: authLoading } = useAuth()
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [touched, setTouched] = useState<{ name?: boolean; email?: boolean }>(
    {},
  )
  const [errors, setErrors] = useState<{ name?: string; email?: string }>({})

  const from = searchParams.get('from') || ''

  React.useEffect(() => {
    if (!authLoading && user) {
      router.replace(from || '/')
    }
  }, [authLoading, user, router, from])

  const validate = () => {
    const e: { name?: string; email?: string } = {}
    if (!name.trim()) e.name = 'Name is required'
    if (!email.trim()) e.email = 'Email is required'
    else if (!/^\S+@\S+\.\S+$/.test(email)) e.email = 'Invalid email'
    else if (!isAllowedEmail(email)) e.email = 'Use your @polariseco.com email'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = async (ev: React.FormEvent) => {
    ev.preventDefault()
    setTouched({ name: true, email: true })
    if (!validate()) return

    setLoading(true)
    try {
      const ok = await requestMagicLink(normalizeEmail(email), {
        username: name,
        returnTo: from || '/',
      })
      if (ok) {
        setSent(true)
        toast.success('Magic link sent (check your email)')
      } else {
        toast.error('Failed to send magic link')
      }
    } catch (_e) {
      toast.error('Failed to send magic link')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="card w-full max-w-[400px] border border-gray-300 shadow-sm rounded-xl">
        <form
          className="card-body flex flex-col gap-4 p-8 sm:p-10"
          onSubmit={handleSubmit}
          noValidate
        >
          <div className="text-center mb-2">
            <h3 className="text-xl font-semibold text-gray-900 leading-none mb-3">
              Sign up
            </h3>
            <div className="flex items-center justify-center font-medium">
              <span className="text-sm text-gray-600 me-1.5">
                Already have an account?
              </span>
              <Link
                href={from ? `/login?from=${from}` : '/login'}
                className="text-sm text-blue-600 hover:text-blue-700 transition-colors"
              >
                Log in
              </Link>
            </div>
          </div>

          {sent && (
            <div className="text-sm text-gray-700 bg-blue-50 border border-blue-100 rounded-lg p-3">
              We sent a sign-in link to{' '}
              <span className="font-medium">{email}</span>. Open it to finish
              creating your account.
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-900">Name</label>
            <div className="relative">
              <input
                placeholder="Enter name"
                autoComplete="off"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, name: true }))}
                className={
                  'w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors ' +
                  (touched.name && errors.name
                    ? 'border-danger'
                    : 'border-gray-300')
                }
              />
            </div>
            <span role="alert" className="text-danger text-xs h-2.5">
              {touched.name && errors.name && (
                <p className="text-red-500">{errors.name}</p>
              )}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-900">Email</label>
            <div className="relative">
              <input
                type="email"
                placeholder="Enter email"
                autoComplete="off"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, email: true }))}
                className={
                  'w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors ' +
                  (touched.email && errors.email
                    ? 'border-danger'
                    : 'border-gray-300')
                }
              />
            </div>
            <span role="alert" className="text-danger text-xs  h-2.5">
              {touched.email && errors.email && (
                <p className="text-red-500">{errors.email}</p>
              )}
            </span>
          </div>

          <button
            type="submit"
            className="h-11 px-6 mt-2 text-white bg-blue-700 hover:bg-blue-900 rounded-lg transition-colors flex items-center justify-center disabled:opacity-70 disabled:cursor-not-allowed"
            disabled={loading}
          >
            {loading ? 'Please wait...' : 'Send magic link'}
          </button>
        </form>
      </div>
    </div>
  )
}

