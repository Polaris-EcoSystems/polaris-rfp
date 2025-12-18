import Head from 'next/head'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'
import Layout from '../components/Layout'
import { useToast } from '../components/ui/Toast'
import { useAuth } from '../lib/auth'

export default function MagicLinkPage() {
  const router = useRouter()
  const toast = useToast()
  const { verifyMagicLink } = useAuth()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!router.isReady) return

    const mid = typeof router.query.mid === 'string' ? router.query.mid : ''
    const code = typeof router.query.code === 'string' ? router.query.code : ''
    const returnTo =
      typeof router.query.returnTo === 'string' ? router.query.returnTo : ''

    const run = async () => {
      setLoading(true)
      try {
        if (!mid || !code) {
          toast.error('Invalid magic link')
          router.replace('/login')
          return
        }

        const res = await verifyMagicLink(mid, code, true)
        if (!res.ok) {
          toast.error('Magic link expired or invalid')
          router.replace('/login')
          return
        }

        const dest = res.returnTo || returnTo || '/'
        router.replace(dest)
      } finally {
        setLoading(false)
      }
    }

    run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.isReady])

  return (
    <Layout>
      <Head>
        <title>Signing in…</title>
      </Head>
      <div className="text-sm text-gray-600">
        {loading ? 'Signing you in…' : 'Redirecting…'}
      </div>
    </Layout>
  )
}
