import Head from 'next/head'
import { useRouter } from 'next/router'
import React, { useMemo, useState } from 'react'
import { useToast } from '../../components/ui/Toast'
import api from '../../lib/api'

export default function ResetPasswordTokenPage() {
  const router = useRouter()
  const toast = useToast()
  const token = useMemo(() => {
    const t = router.query.token
    return typeof t === 'string' ? t : ''
  }, [router.query.token])

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token) return
    if (password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    if (password !== confirm) {
      toast.error('Passwords must match')
      return
    }

    setSubmitting(true)
    try {
      await api.post('/api/auth/reset-password', { token, password })
      toast.success('Password updated. Please log in.')
      router.push('/login')
    } catch (_e) {
      toast.error('Invalid or expired reset link')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Head>
        <title>Set New Password - RFP Proposal System</title>
      </Head>
      <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
        <div className="card w-full max-w-[440px] border border-gray-300 shadow-sm rounded-xl">
          <form
            className="card-body flex flex-col gap-4 p-8 sm:p-10"
            onSubmit={onSubmit}
            noValidate
          >
            <div className="text-center mb-2">
              <h3 className="text-xl font-semibold text-gray-900 leading-none mb-2">
                Set a new password
              </h3>
              <p className="text-sm text-gray-600">
                Choose a strong password (8+ characters).
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-900">
                New password
              </label>
              <input
                type="password"
                placeholder="Enter new password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors"
                disabled={submitting}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-gray-900">
                Confirm password
              </label>
              <input
                type="password"
                placeholder="Confirm new password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors"
                disabled={submitting}
              />
            </div>

            <button
              type="submit"
              className="h-11 px-6 mt-2 text-white bg-blue-700 hover:bg-blue-900 rounded-lg transition-colors flex items-center justify-center disabled:opacity-70 disabled:cursor-not-allowed"
              disabled={submitting || !token}
              title={!token ? 'Invalid reset link' : undefined}
            >
              {submitting ? 'Please wait...' : 'Update password'}
            </button>
          </form>
        </div>
      </div>
    </>
  )
}
