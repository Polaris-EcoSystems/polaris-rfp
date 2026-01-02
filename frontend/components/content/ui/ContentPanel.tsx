'use client'

import type { ReactNode } from 'react'

export default function ContentPanel({
  title,
  actions,
  children,
  footer,
  sticky = false,
  className = '',
}: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  footer?: ReactNode
  sticky?: boolean
  className?: string
}) {
  return (
    <div
      className={`bg-white shadow rounded-lg ${
        sticky ? 'sticky top-6' : ''
      } ${className}`.trim()}
    >
      {title || actions ? (
        <div className="px-6 py-5 border-b border-gray-200">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              {title ? (
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  {title}
                </h3>
              ) : null}
            </div>
            {actions ? (
              <div className="flex items-center gap-2">{actions}</div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="px-6 py-4">{children}</div>

      {footer ? (
        <div className="px-6 py-4 border-t border-gray-200">{footer}</div>
      ) : null}
    </div>
  )
}


