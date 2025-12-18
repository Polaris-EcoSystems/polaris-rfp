import type { Metadata } from 'next'
import './globals.css'
import Providers from './providers'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: {
    default: 'RFP Proposal System',
    template: '%s · RFP Proposal System',
  },
  icons: [{ rel: 'icon', type: 'image/svg+xml', url: '/favicon.svg' }],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="min-h-screen bg-gray-50">{children}</div>
        </Providers>
      </body>
    </html>
  )
}
