'use client'

import Card, { CardBody, CardHeader } from '@/components/ui/Card'
import PageHeader from '@/components/ui/PageHeader'
import { useParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

type PortalFile = {
  id: string | null
  kind: string
  label: string
  fileName?: string | null
  contentType?: string
}

type PortalPackage = {
  name?: string | null
  publishedAt?: string | null
  portalTokenExpiresAt?: string | null
  files: PortalFile[]
}

export default function ClientPortalPage() {
  const params = useParams<{ token?: string }>()
  const token = typeof params?.token === 'string' ? params.token : ''

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')
  const [pkg, setPkg] = useState<PortalPackage | null>(null)
  const [downloadingId, setDownloadingId] = useState<string>('')

  const expiresLabel = useMemo(() => {
    const exp = String((pkg as any)?.portalTokenExpiresAt || '').trim()
    if (!exp) return ''
    return exp
  }, [pkg])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        if (!token) throw new Error('Missing portal token')
        const resp = await fetch(
          `/api/client/portal/${encodeURIComponent(token)}`,
          {
            method: 'GET',
            headers: { accept: 'application/json' },
            cache: 'no-store',
          },
        )
        const json = await resp.json().catch(() => null)
        if (!resp.ok) {
          throw new Error(
            String(json?.detail || json?.error || 'Portal package not found'),
          )
        }
        if (!cancelled) {
          setPkg((json?.package as PortalPackage) || null)
        }
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message || 'Failed to load package'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  const downloadFile = async (fileId: string) => {
    if (!token) return
    setDownloadingId(fileId)
    setError('')
    try {
      const resp = await fetch(
        `/api/client/portal/${encodeURIComponent(
          token,
        )}/files/${encodeURIComponent(fileId)}/presign`,
        {
          method: 'GET',
          headers: { accept: 'application/json' },
          cache: 'no-store',
        },
      )
      const json = await resp.json().catch(() => null)
      if (!resp.ok) {
        throw new Error(
          String(json?.detail || json?.error || 'Failed to presign download'),
        )
      }
      const url = String(json?.url || '')
      if (!url) throw new Error('Missing download URL')
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (e: any) {
      setError(String(e?.message || 'Download failed'))
    } finally {
      setDownloadingId('')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={pkg?.name || 'Client package'}
        subtitle={expiresLabel ? `Link expires: ${expiresLabel}` : undefined}
      />

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-900">Files</div>
          <div className="text-xs text-gray-600">
            Download the documents included in this package.
          </div>
        </CardHeader>
        <CardBody className="space-y-2">
          {pkg?.files?.length ? (
            pkg.files.map((f) => (
              <div
                key={String(f.id)}
                className="flex items-center justify-between gap-3 rounded border border-gray-200 bg-white px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-900">
                    {f.label || f.fileName || 'File'}
                  </div>
                  <div className="text-xs text-gray-600 truncate">{f.kind}</div>
                </div>
                <button
                  type="button"
                  disabled={!f.id || downloadingId === f.id}
                  onClick={() => f.id && downloadFile(f.id)}
                  className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100 disabled:opacity-50"
                >
                  {downloadingId === f.id ? 'Preparing…' : 'Download'}
                </button>
              </div>
            ))
          ) : (
            <div className="text-sm text-gray-600">No files available.</div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
