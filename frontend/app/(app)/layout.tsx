import AuthGuard from '@/components/AuthGuard'
import Layout from '@/components/Layout'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <Layout>{children}</Layout>
    </AuthGuard>
  )
}
