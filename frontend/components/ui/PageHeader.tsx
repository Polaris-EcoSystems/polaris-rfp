'use client'

import { ReactNode } from 'react'

export default function PageHeader({
  title,
  subtitle,
  badge,
  actions,
  className = '',
}: {
  title: ReactNode
  subtitle?: ReactNode
  badge?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={`flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between ${className}`}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">
            {title}
          </h1>
          {badge}
        </div>
        {subtitle ? (
          <p className="mt-1 text-sm sm:text-base text-gray-600">{subtitle}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex items-center gap-2">{actions}</div>
      ) : null}
    </div>
  )
}

