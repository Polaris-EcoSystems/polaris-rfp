'use client'

import Link from 'next/link'
import React, { useState } from 'react'
import { useToast } from '@/components/ui/Toast'
import api from '@/lib/api'

export default function ResetPasswordPage() {
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [debugResetUrl, setDebugResetUrl] = useState<string | null>(null)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      setDebugResetUrl(null)
      const resp = await api.post('/api/auth/request-password-reset', { email })
      const resetUrl =
        typeof resp?.data?.resetUrl === 'string' ? resp.data.resetUrl : null
      if (resetUrl) setDebugResetUrl(resetUrl)

      toast.success(
        'If an account exists for that email, reset instructions have been sent.',
      )
    } catch (_e) {
      toast.success(
        'If an account exists for that email, reset instructions have been sent.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="card w-full max-w-[440px] border border-gray-300 shadow-sm rounded-xl">
        <form
          className="card-body flex flex-col gap-4 p-8 sm:p-10"
          onSubmit={onSubmit}
          noValidate
        >
          <div className="text-center mb-2">
            <h3 className="text-xl font-semibold text-gray-900 leading-none mb-2">
              Reset password
            </h3>
            <p className="text-sm text-gray-600">
              Enter your email and we’ll send reset instructions (when enabled).
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-900">Email</label>
            <input
              type="email"
              placeholder="Enter email"
              autoComplete="off"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors"
            />
          </div>

          <button
            type="submit"
            className="h-11 px-6 mt-2 text-white bg-blue-700 hover:bg-blue-900 rounded-lg transition-colors flex items-center justify-center disabled:opacity-70 disabled:cursor-not-allowed"
            disabled={submitting || !email.trim()}
          >
            {submitting ? 'Please wait...' : 'Send reset link'}
          </button>

          {debugResetUrl && (
            <div className="text-sm text-gray-700 bg-blue-50 border border-blue-200 rounded-md p-3">
              <div className="font-medium text-blue-900">
                Dev shortcut (reset link)
              </div>
              <a
                className="text-blue-700 underline break-all"
                href={debugResetUrl}
              >
                {debugResetUrl}
              </a>
            </div>
          )}

          <div className="text-center">
            <Link
              href="/login"
              className="text-sm text-primary-600 hover:text-primary-700 transition-colors"
            >
              Back to login
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
