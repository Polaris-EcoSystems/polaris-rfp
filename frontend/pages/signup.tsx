import { useFormik } from 'formik'
import Link from 'next/link'
import { useRouter } from 'next/router'
import React, { useState } from 'react'
import * as Yup from 'yup'
import { useToast } from '../components/ui/Toast'
import api from '../lib/api'
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

const signupSchema = Yup.object().shape({
  name: Yup.string()
    .min(2, 'Minimum 2 charaters')
    .max(50, 'Maximum 50 charaters')
    .required('Name is required'),
  email: Yup.string()
    .email('Wrong email format')
    .min(3, 'Minimum 3 charaters')
    .max(50, 'Maximum 50 charaters')
    .required('Email is required'),
  password: Yup.string()
    .min(8, 'Minimum 8 characters')
    .max(100, 'Maximum 100 characters')
    .required('Password is required'),
  confirmPassword: Yup.string()
    .required('Please confirm your password')
    .oneOf([Yup.ref('password')], 'Passwords must match'),
})

export default function SignupPage() {
  const router = useRouter()
  const { setToken, user, loading: authLoading } = useAuth()
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  const from = typeof router.query.from === 'string' ? router.query.from : ''

  React.useEffect(() => {
    if (!authLoading && user) {
      router.replace(from || '/')
    }
  }, [authLoading, user, router, from])

  const formik = useFormik<{
    name: string
    email: string
    password: string
    confirmPassword: string
  }>({
    initialValues: {
      name: '',
      email: '',
      password: '',
      confirmPassword: '',
    },
    validationSchema: signupSchema,
    onSubmit: async (values) => {
      setLoading(true)
      try {
        const response = await api.post(`/api/auth/signup`, {
          username: values.name,
          email: values.email,
          password: values.password,
        })

        const token = response.data?.access_token
        if (token) {
          await setToken(token, true)
          toast.success('Account created — logged in')
          router.push(from || '/')
        } else {
          toast.success('Account created — please log in')
          router.push('/login')
        }
      } catch (err: any) {
        console.error(err)
        const msg =
          err?.response?.data?.message ||
          err?.response?.data?.error ||
          'Signup failed'
        toast.error(msg)
      } finally {
        setLoading(false)
      }
    },
  })

  const togglePassword = () => setShowPassword((s) => !s)
  const toggleConfirm = () => setShowConfirmPassword((s) => !s)

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="card w-full max-w-[400px] border border-gray-300 shadow-sm rounded-xl">
        <form
          className="card-body flex flex-col gap-4 p-8 sm:p-10"
          onSubmit={formik.handleSubmit}
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

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-900">Name</label>
            <div className="relative">
              <input
                placeholder="Enter name"
                autoComplete="off"
                {...formik.getFieldProps('name')}
                className={
                  'w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors ' +
                  (formik.touched.name && formik.errors.name
                    ? 'border-danger'
                    : 'border-gray-300')
                }
              />
            </div>
            <span role="alert" className="text-danger text-xs h-2.5">
              {formik.touched.name && formik.errors.name && (
                <p className="text-red-500">{formik.errors.name}</p>
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
                {...formik.getFieldProps('email')}
                className={
                  'w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors ' +
                  (formik.touched.email && formik.errors.email
                    ? 'border-danger'
                    : 'border-gray-300')
                }
              />
            </div>
            <span role="alert" className="text-danger text-xs  h-2.5">
              {formik.touched.email && formik.errors.email && (
                <p className="text-red-500">{formik.errors.email}</p>
              )}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-900">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="Enter Password"
                autoComplete="new-password"
                {...formik.getFieldProps('password')}
                className={
                  'w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors pr-11 ' +
                  (formik.touched.password && formik.errors.password
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
            <span role="alert" className="text-danger text-xs  h-2.5">
              {formik.touched.password && formik.errors.password && (
                <p className="text-red-500">{formik.errors.password}</p>
              )}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-900">
              Confirm Password
            </label>
            <div className="relative">
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                placeholder="Confirm Password"
                autoComplete="new-password"
                {...formik.getFieldProps('confirmPassword')}
                className={
                  'w-full h-11 px-4 py-2 text-gray-900 placeholder-gray-500 border rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-colors pr-11 ' +
                  (formik.touched.confirmPassword &&
                  formik.errors.confirmPassword
                    ? 'border-danger'
                    : 'border-gray-300')
                }
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 transition-colors"
                onClick={toggleConfirm}
              >
                {showConfirmPassword ? (
                  <EyeSlashIcon className="w-5 h-5" />
                ) : (
                  <EyeIcon className="w-5 h-5" />
                )}
              </button>
            </div>
            <span role="alert" className="text-danger text-xs h-2.5">
              {formik.touched.confirmPassword &&
                formik.errors.confirmPassword && (
                  <p className="text-red-500">
                    {formik.errors.confirmPassword}
                  </p>
                )}
            </span>
          </div>

          <button
            type="submit"
            className="h-11 px-6 mt-2 text-white bg-blue-700 hover:bg-blue-900 rounded-lg transition-colors flex items-center justify-center disabled:opacity-70 disabled:cursor-not-allowed"
            disabled={loading}
          >
            {loading ? 'Please wait...' : 'Sign Up'}
          </button>
        </form>
      </div>
    </div>
  )
}
