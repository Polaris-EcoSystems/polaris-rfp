import Head from 'next/head'
import type { GetServerSideProps } from 'next'
import Layout from '../components/Layout'
import Dashboard from '../components/Dashboard'
import AuthGuard from '../components/AuthGuard'

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