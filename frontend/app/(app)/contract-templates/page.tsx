'use client'

import Card, { CardBody, CardHeader } from '@/components/ui/Card'
import PageHeader from '@/components/ui/PageHeader'
import { ContractTemplate, contractTemplatesApi } from '@/lib/api'
import Link from 'next/link'
import { useEffect, useState } from 'react'

export default function ContractTemplatesPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [templates, setTemplates] = useState<ContractTemplate[]>([])

  const [name, setName] = useState('')
  const [kind, setKind] = useState<'msa' | 'sow' | 'combined'>('combined')
  const [creating, setCreating] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await contractTemplatesApi.list({ limit: 200 })
      setTemplates((resp.data.data as any) || [])
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
  }, [])

  const create = async () => {
    setCreating(true)
    setError('')
    try {
      if (!name.trim()) throw new Error('Name is required')
      await contractTemplatesApi.create({ name: name.trim(), kind })
      setName('')
      await load()
    } catch (e: any) {
      setError(
        String(e?.response?.data?.detail || e?.message || 'Failed to create'),
      )
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Contract templates"
        subtitle="Manage DOCX templates used for contracting."
      />

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">Create</div>
            <div className="text-xs text-gray-600">
              Create a template container, then upload versions.
            </div>
          </CardHeader>
          <CardBody className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Name
              </label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                placeholder="Master Services Agreement"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Kind
              </label>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as any)}
                className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              >
                <option value="msa">MSA</option>
                <option value="sow">SOW</option>
                <option value="combined">Combined</option>
              </select>
            </div>
            <button
              onClick={create}
              disabled={creating}
              className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
            >
              {creating ? 'Creating…' : 'Create template'}
            </button>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">Templates</div>
            <div className="text-xs text-gray-600">
              {loading ? 'Loading…' : `${templates.length} template(s)`}
            </div>
          </CardHeader>
          <CardBody>
            {templates.length === 0 ? (
              <div className="text-sm text-gray-600">No templates yet.</div>
            ) : (
              <div className="space-y-2">
                {templates.map((t) => (
                  <div
                    key={t._id}
                    className="flex items-center justify-between rounded-md border border-gray-200 bg-white px-3 py-2"
                  >
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {t.name}
                      </div>
                      <div className="text-xs text-gray-600">
                        kind: {t.kind} · current:{' '}
                        {t.currentVersionId || '(none)'}
                      </div>
                    </div>
                    <Link
                      href={`/contract-templates/${encodeURIComponent(t._id)}`}
                      className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                    >
                      Manage
                    </Link>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
