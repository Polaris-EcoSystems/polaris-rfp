'use client'

import type { ReactNode } from 'react'

export default function ContentSplitLayout({
  list,
  details,
  className = '',
}: {
  list: ReactNode
  details: ReactNode
  className?: string
}) {
  return (
    <div className={`grid grid-cols-1 gap-6 lg:grid-cols-3 ${className}`.trim()}>
      <div className="lg:col-span-2">{list}</div>
      <div className="lg:col-span-1">{details}</div>
    </div>
  )
}
