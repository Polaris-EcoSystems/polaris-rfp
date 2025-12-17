import type { AppProps } from 'next/app'
import Head from 'next/head'
import { useRouter } from 'next/router'
import AuthGuard from '../components/AuthGuard'
import { ToastProvider } from '../components/ui/Toast'
import { AuthProvider } from '../lib/auth'
import '../styles/globals.css'

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter()

  const publicRoutes = new Set(['/login', '/signup', '/reset-password'])
  const isPublicRoute = publicRoutes.has(router.pathname)

  return (
    <>
      <Head>
        <link rel="icon" type="image/png" href="/favicon.png" />
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
        <link rel="shortcut icon" href="/favicon.png" />
      </Head>
      <ToastProvider>
        <AuthProvider>
          <div className="min-h-screen bg-gray-50">
            {isPublicRoute ? (
              <Component {...pageProps} />
            ) : (
              <AuthGuard>
                <Component {...pageProps} />
              </AuthGuard>
            )}
          </div>
        </AuthProvider>
      </ToastProvider>
    </>
  )
}
