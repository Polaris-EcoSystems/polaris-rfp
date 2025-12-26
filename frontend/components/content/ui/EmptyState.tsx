'use client'

import type { ReactNode } from 'react'

export default function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: ReactNode
  description?: ReactNode
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="text-center py-10">
      {icon ? (
        <div className="mx-auto h-10 w-10 text-gray-400">{icon}</div>
      ) : null}
      <div className="mt-3 text-sm font-medium text-gray-900">{title}</div>
      {description ? (
        <div className="mt-1 text-sm text-gray-500">{description}</div>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
}

