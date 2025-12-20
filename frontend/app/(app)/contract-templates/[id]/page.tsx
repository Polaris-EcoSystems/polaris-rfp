'use client'

import Card, { CardBody, CardHeader } from '@/components/ui/Card'
import PageHeader from '@/components/ui/PageHeader'
import {
  ContractTemplate,
  ContractTemplateVersion,
  contractTemplatesApi,
} from '@/lib/api'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

export default function ContractTemplateDetailPage() {
  const params = useParams<{ id?: string }>()
  const templateId = typeof params?.id === 'string' ? params.id : ''

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [tpl, setTpl] = useState<ContractTemplate | null>(null)
  const [versions, setVersions] = useState<ContractTemplateVersion[]>([])

  const [currentVersionId, setCurrentVersionId] = useState('')
  const [savingCurrent, setSavingCurrent] = useState(false)

  const [uploading, setUploading] = useState(false)
  const [changelog, setChangelog] = useState('')
  const [variablesSchemaJson, setVariablesSchemaJson] = useState('{}')

  const [previewKeyTermsJson, setPreviewKeyTermsJson] = useState('{}')
  const [previewing, setPreviewing] = useState(false)

  const hasVersions = versions.length > 0

  const latestVersionId = useMemo(() => {
    const v = versions?.[0]
    return String((v as any)?.versionId || (v as any)?._id || '').trim()
  }, [versions])

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      if (!templateId) throw new Error('Missing template id')
      const [tResp, vResp] = await Promise.all([
        contractTemplatesApi.get(templateId),
        contractTemplatesApi.listVersions(templateId),
      ])
      const t = tResp.data as any as ContractTemplate
      setTpl(t)
      setVersions(((vResp.data as any)?.data as any) || [])
      setCurrentVersionId(String((t as any)?.currentVersionId || ''))
    } catch (e: any) {
      setError(
        String(e?.response?.data?.detail || e?.message || 'Failed to load'),
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId])

  const setCurrent = async () => {
    if (!templateId) return
    setSavingCurrent(true)
    setError('')
    try {
      if (!currentVersionId.trim())
        throw new Error('Select a version to set as current')
      await contractTemplatesApi.update(templateId, {
        currentVersionId: currentVersionId.trim(),
      })
      await load()
    } catch (e: any) {
      setError(
        String(e?.response?.data?.detail || e?.message || 'Failed to update'),
      )
    } finally {
      setSavingCurrent(false)
    }
  }

  const uploadVersion = async (file: File) => {
    if (!templateId) return
    setUploading(true)
    setError('')
    try {
      if (!file) throw new Error('Pick a DOCX file')
      const presign = await contractTemplatesApi.presignVersionUpload(
        templateId,
        {
          fileName: file.name || 'template.docx',
          contentType:
            file.type ||
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        },
      )
      const putUrl = String((presign.data as any)?.putUrl || '')
      const key = String((presign.data as any)?.key || '')
      const versionId = String((presign.data as any)?.versionId || '')
      if (!putUrl || !key || !versionId)
        throw new Error('Failed to presign upload')

      const putResp = await fetch(putUrl, { method: 'PUT', body: file })
      if (!putResp.ok) throw new Error('Upload failed')

      let vars: any = {}
      try {
        vars = JSON.parse(variablesSchemaJson || '{}')
      } catch {
        throw new Error('variablesSchema JSON is invalid')
      }

      await contractTemplatesApi.commitVersion(templateId, {
        versionId,
        key,
        changelog: changelog.trim() || undefined,
        variablesSchema: vars,
      })

      setChangelog('')
      setVariablesSchemaJson('{}')
      await load()
    } catch (e: any) {
      setError(
        String(e?.response?.data?.detail || e?.message || 'Failed to upload'),
      )
    } finally {
      setUploading(false)
    }
  }

  const preview = async () => {
    if (!templateId) return
    const vid = currentVersionId.trim() || latestVersionId
    if (!vid) {
      setError('Select or upload a version first')
      return
    }
    setPreviewing(true)
    setError('')
    try {
      let keyTerms: any = {}
      try {
        keyTerms = JSON.parse(previewKeyTermsJson || '{}')
      } catch {
        throw new Error('Preview keyTerms JSON is invalid')
      }
      const r = await contractTemplatesApi.previewVersion(templateId, vid, {
        keyTerms,
        renderInputs: {},
      })
      const url = String((r.data as any)?.url || '')
      if (!url) throw new Error('Preview URL missing')
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (e: any) {
      setError(
        String(e?.response?.data?.detail || e?.message || 'Failed to preview'),
      )
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Contract template"
        subtitle={
          <div className="flex items-center gap-2">
            <Link
              href="/contract-templates"
              className="text-sm text-gray-700 hover:underline"
            >
              Back to templates
            </Link>
            {tpl ? (
              <span className="text-sm text-gray-600">· {tpl.name}</span>
            ) : null}
          </div>
        }
      />

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">Current</div>
            <div className="text-xs text-gray-600">
              Set which version will be used by default for generation.
            </div>
          </CardHeader>
          <CardBody className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Current version
              </label>
              <select
                value={currentVersionId}
                onChange={(e) => setCurrentVersionId(e.target.value)}
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">(none)</option>
                {versions.map((v) => (
                  <option
                    key={v._id || v.versionId}
                    value={v.versionId || v._id}
                  >
                    {v.versionId || v._id}
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={setCurrent}
              disabled={savingCurrent || !hasVersions}
              className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
            >
              {savingCurrent ? 'Saving…' : 'Set current'}
            </button>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">Upload</div>
            <div className="text-xs text-gray-600">
              Upload a DOCX template version (becomes current on commit).
            </div>
          </CardHeader>
          <CardBody className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Changelog (optional)
              </label>
              <input
                value={changelog}
                onChange={(e) => setChangelog(e.target.value)}
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                placeholder="Add termination clause; update SOW header…"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                variablesSchema (JSON, optional)
              </label>
              <textarea
                value={variablesSchemaJson}
                onChange={(e) => setVariablesSchemaJson(e.target.value)}
                rows={6}
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-xs"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                DOCX file
              </label>
              <input
                type="file"
                accept=".docx"
                disabled={uploading}
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void uploadVersion(f)
                  e.currentTarget.value = ''
                }}
                className="mt-1 w-full text-sm"
              />
            </div>
            <div className="text-xs text-gray-500">
              {uploading
                ? 'Uploading…'
                : 'Tip: keep placeholders stable across versions.'}
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">Versions</div>
            <div className="text-xs text-gray-600">
              {loading ? 'Loading…' : `${versions.length} version(s)`}
            </div>
          </CardHeader>
          <CardBody>
            {versions.length === 0 ? (
              <div className="text-sm text-gray-600">No versions yet.</div>
            ) : (
              <div className="space-y-2">
                {versions.map((v) => (
                  <div
                    key={v._id || v.versionId}
                    className="rounded-md border border-gray-200 bg-white px-3 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium text-gray-900">
                        {v.versionId}
                      </div>
                      {String(tpl?.currentVersionId || '') === v.versionId ? (
                        <span className="text-[11px] rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-green-800">
                          current
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-1 text-xs text-gray-600 break-all">
                      {v.s3Key}
                    </div>
                    {v.changelog ? (
                      <div className="mt-1 text-xs text-gray-700">
                        {v.changelog}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">Preview</div>
            <div className="text-xs text-gray-600">
              Render the current (or latest) version with sample key terms.
            </div>
          </CardHeader>
          <CardBody className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Sample keyTerms (JSON)
              </label>
              <textarea
                value={previewKeyTermsJson}
                onChange={(e) => setPreviewKeyTermsJson(e.target.value)}
                rows={8}
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-xs"
              />
            </div>
            <button
              onClick={preview}
              disabled={previewing}
              className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
            >
              {previewing ? 'Rendering…' : 'Render preview DOCX'}
            </button>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
