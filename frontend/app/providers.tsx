'use client'

import { ToastProvider } from '@/components/ui/Toast'
import { AuthProvider } from '@/lib/auth'

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <AuthProvider>{children}</AuthProvider>
    </ToastProvider>
  )
}
