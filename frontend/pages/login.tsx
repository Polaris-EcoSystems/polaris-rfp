import Link from 'next/link'
import { useRouter } from 'next/router'
import React, { useState } from 'react'
import { useToast } from '../components/ui/Toast'
import { useAuth } from '../lib/auth'

function EyeIcon(props: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <path
        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.477 0 8.268 2.943 9.542 7-1.274 4.057-5.065 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function EyeSlashIcon(props: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
    >
      <path
        d="M3 3l18 18"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10.477 10.477A3.5 3.5 0 0113.523 13.523"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.477 0 8.268 2.943 9.542 7-1.035 3.299-3.423 5.8-6.332 6.92"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function LoginPage() {
  const router = useRouter()
  const { login, user, loading: authLoading } = useAuth()
  const toast = useToast()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [touched, setTouched] = useState<{
    email?: boolean
    password?: boolean
  }>({})
  const [errors, setErrors] = useState<{ email?: string; password?: string }>(
    {},
  )

  const from = typeof router.query.from === 'string' ? router.query.from : ''

  React.useEffect(() => {
    if (!authLoading && user) {
      router.replace(from || '/')
    }
  }, [authLoading, user, router, from])

  const validate = () => {
    const e: { email?: string; password?: string } = {}
    if (!email) e.email = 'Email is required'
    else if (!/^\S+@\S+\.\S+$/.test(email)) e.email = 'Invalid email'
    if (!password) e.password = 'Password is required'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const togglePassword = () => setShowPassword((s) => !s)

  const handleSubmit = async (ev: React.FormEvent) => {
    ev.preventDefault()
    setTouched({ email: true, password: true })
    if (!validate()) return
    setLoading(true)
    try {
      const ok = await login(email, password, remember)
      if (ok) {
        toast.success('Logged in')
        router.push(from || '/')
      } else {
        toast.error('Invalid credentials')
      }
    } catch (err) {
      console.error(err)
      toast.error('Login failed')
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
              Log in
            </h3>
            <div className="flex items-center justify-center font-medium">
              <span className="text-sm text-gray-600 me-1.5">
                Need an account?
              </span>
              <Link
                href={from ? `/signup?from=${from}` : '/signup'}
                className="text-sm text-blue-600 hover:text-blue-700 transition-colors"
              >
                Sign up
              </Link>
            </div>
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
            <span role="alert" className="text-danger text-xs h-2.5">
              {touched.email && errors.email && (
                <p className="text-red-500">{errors.email}</p>
              )}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-900">
                Password
              </label>
              <Link
                href={'/reset-password'}
                className="text-sm text-primary-600 hover:text-primary-700 transition-colors"
              >
                Forgot Password?
              </Link>
            </div>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="Enter Password"
                autoComplete="off"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, password: true }))}
                className={
                  'w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors pr-11 ' +
                  (touched.password && errors.password
                    ? 'border-danger'
                    : 'border-gray-300')
                }
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 transition-colors"
                onClick={togglePassword}
              >
                {showPassword ? (
                  <EyeSlashIcon className="w-5 h-5" />
                ) : (
                  <EyeIcon className="w-5 h-5" />
                )}
              </button>
            </div>
            <span role="alert" className="text-danger text-xs h-2.5">
              {touched.password && errors.password && (
                <p className="text-red-500">{errors.password}</p>
              )}
            </span>
          </div>

          <label className="flex items-center gap-2 relative">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="w-4 h-4 border border-gray-300 rounded bg-white focus:ring-primary appearance-none checked:bg-white checked:border-gray-400"
            />
            {/* Custom checkmark for checked state */}
            {remember && (
              <span className="absolute left-1 top-1 pointer-events-none">
                <svg
                  className="w-2.5 h-2.5"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="black"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="3.5 8.5 7 12 12.5 5.5" />
                </svg>
              </span>
            )}
            <span className="text-sm text-gray-700 ml-1">Remember me</span>
          </label>

          <button
            type="submit"
            className="h-11 px-6 mt-2 text-white bg-blue-700 hover:bg-blue-900 rounded-lg transition-colors flex items-center justify-center disabled:opacity-70 disabled:cursor-not-allowed"
            disabled={loading}
          >
            {loading ? 'Please wait...' : 'Log In'}
          </button>
        </form>
      </div>
    </div>
  )
}
