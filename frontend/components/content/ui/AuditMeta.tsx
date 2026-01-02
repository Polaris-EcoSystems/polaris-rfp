'use client'

function formatDate(iso?: string | null): string {
  const s = String(iso || '').trim()
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString()
}

export default function AuditMeta({
  createdAt,
  updatedAt,
  version,
  className = '',
}: {
  createdAt?: string | null
  updatedAt?: string | null
  version?: number | string | null
  className?: string
}) {
  const created = formatDate(createdAt)
  const updated = formatDate(updatedAt)
  const v =
    typeof version === 'number' || typeof version === 'string'
      ? String(version)
      : ''

  if (!created && !updated && !v) return null

  return (
    <div className={`text-xs text-gray-500 ${className}`.trim()}>
      {updated ? (
        <span>
          Updated <span className="font-semibold text-gray-700">{updated}</span>
        </span>
      ) : null}
      {created ? (
        <span className={updated ? 'ml-2' : ''}>
          Created <span className="font-semibold text-gray-700">{created}</span>
        </span>
      ) : null}
      {v ? (
        <span className={updated || created ? 'ml-2' : ''}>
          v<span className="font-semibold text-gray-700">{v}</span>
        </span>
      ) : null}
    </div>
  )
}


