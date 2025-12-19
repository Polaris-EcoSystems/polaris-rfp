import Link from 'next/link'

type Crumb = { label: string; href?: string }

export function PipelineBreadcrumbs({
  items,
  className = '',
}: {
  items: Crumb[]
  className?: string
}) {
  const list = Array.isArray(items) ? items : []
  if (list.length === 0) return null

  return (
    <nav
      aria-label="Breadcrumb"
      className={`text-xs text-gray-500 flex items-center gap-2 ${className}`}
    >
      {list.map((it, idx) => {
        const isLast = idx === list.length - 1
        const sep = idx === 0 ? null : <span key={`sep-${idx}`}>/</span>
        const node = it.href ? (
          <Link key={it.label} href={it.href} className="hover:text-gray-700">
            {it.label}
          </Link>
        ) : (
          <span key={it.label} className={isLast ? 'text-gray-700' : ''}>
            {it.label}
          </span>
        )
        return (
          <span key={`${it.label}-${idx}`} className="flex items-center gap-2">
            {sep}
            {node}
          </span>
        )
      })}
    </nav>
  )
}

