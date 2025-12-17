import type { GetServerSideProps } from 'next'
import Head from 'next/head'
import AuthGuard from '../components/AuthGuard'
import Dashboard from '../components/Dashboard'
import Layout from '../components/Layout'

export const getServerSideProps: GetServerSideProps = async () => {
  // Force SSR so the app is deployed via Amplify WEB_COMPUTE (not pure static export).
  return { props: {} }
}

export default function Home() {
  return (
    <AuthGuard>
      <Layout>
        <Head>
          <title>Dashboard - RFP Proposal System</title>
        </Head>
        <Dashboard />
      </Layout>
    </AuthGuard>
  )
}
