'use client'

import {
  ArrowLeftIcon,
  BoltIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { ReactNode } from 'react'
import Button from './Button'

export type PipelineContextBannerVariant = 'primary' | 'secondary' | 'tool'

export default function PipelineContextBanner({
  variant = 'secondary',
  title = 'Pipeline is the primary workflow.',
  description,
  ctaHref = '/pipeline',
  ctaLabel = 'Back to Pipeline',
  rightSlot,
  className = '',
}: {
  variant?: PipelineContextBannerVariant
  title?: ReactNode
  description: ReactNode
  ctaHref?: string
  ctaLabel?: string
  rightSlot?: ReactNode
  className?: string
}) {
  const styles =
    variant === 'primary'
      ? {
          wrap: 'border-indigo-200 bg-gradient-to-r from-indigo-50 via-blue-50 to-white text-indigo-950',
          iconWrap:
            'bg-gradient-to-br from-indigo-500 to-blue-600 text-white shadow-sm',
          Icon: ChartBarIcon,
          ctaVariant: 'primary' as const,
          ctaGradient: true,
        }
      : variant === 'tool'
      ? {
          wrap: 'border-slate-200 bg-gradient-to-r from-slate-50 via-sky-50 to-white text-slate-900',
          iconWrap:
            'bg-gradient-to-br from-slate-700 to-slate-900 text-white shadow-sm',
          Icon: BoltIcon,
          ctaVariant: 'secondary' as const,
          ctaGradient: false,
        }
      : {
          wrap: 'border-blue-200 bg-gradient-to-r from-blue-50 via-indigo-50 to-white text-blue-950',
          iconWrap:
            'bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-sm',
          Icon: ChartBarIcon,
          ctaVariant: 'secondary' as const,
          ctaGradient: false,
        }

  const Icon = styles.Icon

  return (
    <div
      className={`rounded-2xl border px-4 py-3 shadow-sm ${styles.wrap} ${className}`}
      role="note"
      aria-label="Pipeline guidance"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div
            className={`mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl ${styles.iconWrap}`}
            aria-hidden="true"
          >
            <Icon className="h-5 w-5" />
          </div>

          <div className="min-w-0">
            <div className="text-sm font-semibold leading-5">
              {title}{' '}
              <span className="font-normal text-[13px] opacity-90">
                {description}
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {rightSlot}
          <Button
            as={Link}
            href={ctaHref}
            variant={styles.ctaVariant}
            gradient={styles.ctaGradient}
            size="sm"
            icon={<ArrowLeftIcon className="h-4 w-4" />}
          >
            {ctaLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}




