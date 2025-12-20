import { DEFAULT_LOCALE, isSupportedLocale, LOCALE_COOKIE } from '@/lib/i18n'
import type { Metadata } from 'next'
import { cookies } from 'next/headers'
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

async function loadMessages(locale: string) {
  const l = isSupportedLocale(locale) ? locale : DEFAULT_LOCALE
  if (l === 'es') return (await import('../messages/es.json')).default
  return (await import('../messages/en.json')).default
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get(LOCALE_COOKIE)?.value
  const locale = isSupportedLocale(cookieLocale) ? cookieLocale : DEFAULT_LOCALE
  const messages = await loadMessages(locale)

  return (
    <html lang={locale}>
      <body>
        <Providers locale={locale} messages={messages}>
          <div className="min-h-screen bg-gray-50">{children}</div>
        </Providers>
      </body>
    </html>
  )
}
