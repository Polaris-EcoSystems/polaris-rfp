import { ReactNode } from 'react'

export type StepItem = {
  title: ReactNode
  description?: ReactNode
}

export default function StepsPanel({
  title = 'Quick flow',
  steps,
  tone = 'blue',
  columns = 3,
  className = '',
}: {
  title?: ReactNode
  steps: StepItem[]
  tone?: 'blue' | 'slate'
  columns?: 2 | 3 | 4
  className?: string
}) {
  const gridCols =
    columns === 4
      ? 'sm:grid-cols-4'
      : columns === 2
      ? 'sm:grid-cols-2'
      : 'sm:grid-cols-3'

  const dot = tone === 'slate' ? 'bg-slate-900' : 'bg-blue-600'

  const list = Array.isArray(steps) ? steps : []

  return (
    <div
      className={`rounded-xl border border-gray-200 bg-white/80 backdrop-blur-sm p-4 ${className}`}
    >
      <div className="text-sm font-semibold text-gray-900">{title}</div>
      <ol className={`mt-3 grid grid-cols-1 gap-3 ${gridCols}`}>
        {list.map((s, idx) => (
          <li key={idx} className="flex items-start gap-3">
            <div
              className={`mt-0.5 h-7 w-7 rounded-full ${dot} text-white text-xs font-semibold flex items-center justify-center`}
            >
              {idx + 1}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-gray-900">{s.title}</div>
              {s.description ? (
                <div className="text-xs text-gray-600">{s.description}</div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}




