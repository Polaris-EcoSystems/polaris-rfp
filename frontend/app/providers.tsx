'use client'

import { ToastProvider } from '@/components/ui/Toast'
import { AuthProvider } from '@/lib/auth'
import type { AbstractIntlMessages } from 'next-intl'
import { NextIntlClientProvider } from 'next-intl'

export default function Providers({
  children,
  locale,
  messages,
}: {
  children: React.ReactNode
  locale: string
  messages: AbstractIntlMessages
}) {
  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
    </NextIntlClientProvider>
  )
}
