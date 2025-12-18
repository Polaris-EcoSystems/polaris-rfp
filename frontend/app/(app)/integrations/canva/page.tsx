'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  canvaApi,
  contentApi,
  extractList,
  proposalApi,
} from '@/lib/api'

type CanvaDataset = Record<string, { type: 'text' | 'image' | 'chart' }>

const SOURCE_OPTIONS: { label: string; value: string }[] = [
  { label: 'RFP Title', value: 'rfp.title' },
  { label: 'Client Name', value: 'rfp.clientName' },
  { label: 'Submission Deadline', value: 'rfp.submissionDeadline' },
  { label: 'Project Deadline', value: 'rfp.projectDeadline' },
  { label: 'Proposal Title', value: 'proposal.title' },
  { label: 'Title section (raw)', value: 'proposal.sections.Title.content' },
  { label: 'Cover Letter', value: 'proposal.sections.Cover Letter.content' },
  {
    label: 'Executive Summary',
    value: 'proposal.sections.Executive Summary.content',
  },
  {
    label: 'Project Understanding',
    value: 'proposal.sections.Project Understanding.content',
  },
  { label: 'Methodology', value: 'proposal.sections.Methodology.content' },
  { label: 'Deliverables', value: 'proposal.sections.Deliverables.content' },
  { label: 'Timeline / Schedule', value: 'proposal.sections.Timeline.content' },
  { label: 'Team', value: 'proposal.sections.Team.content' },
  { label: 'References', value: 'proposal.sections.References.content' },
]

export default function CanvaIntegrationPage() {
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<any>(null)
  const [companies, setCompanies] = useState<any[]>([])
  const [mappings, setMappings] = useState<any[]>([])
  const [teamMembers, setTeamMembers] = useState<any[]>([])
  const [headshotLinks, setHeadshotLinks] = useState<Record<string, any>>({})
  const [headshotUrls, setHeadshotUrls] = useState<Record<string, string>>({})
  const [uploadingHeadshot, setUploadingHeadshot] = useState<
    Record<string, boolean>
  >({})
  const [proposals, setProposals] = useState<any[]>([])
  const [selectedProposalId, setSelectedProposalId] = useState<string>('')
  const [proposalFilter, setProposalFilter] = useState('')
  const [proposalPage, setProposalPage] = useState(1)
  const proposalPageSize = 50
  const [creatingDesign, setCreatingDesign] = useState(false)
  const [designResult, setDesignResult] = useState<any>(null)
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null)
  const [generatingPreviewPdf, setGeneratingPreviewPdf] = useState(false)
  const [validating, setValidating] = useState(false)
  const [validation, setValidation] = useState<any>(null)
  const [validationFilter, setValidationFilter] = useState('')

  const [selectedCompanyId, setSelectedCompanyId] = useState<string>('')
  const [templates, setTemplates] = useState<any[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(false)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('')
  const [dataset, setDataset] = useState<CanvaDataset>({})
  const [datasetLoading, setDatasetLoading] = useState(false)
  const [datasetFilter, setDatasetFilter] = useState('')

  const [fieldMapping, setFieldMapping] = useState<Record<string, any>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [logoUrl, setLogoUrl] = useState('')
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [companyLogoLink, setCompanyLogoLink] = useState<any>(null)

  const selectedCompany = useMemo(
    () => companies.find((c) => c.companyId === selectedCompanyId) || null,
    [companies, selectedCompanyId],
  )

  const currentMapping = useMemo(() => {
    if (!selectedCompanyId) return null
    return mappings.find((m) => m.companyId === selectedCompanyId) || null
  }, [mappings, selectedCompanyId])

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [s, c, m] = await Promise.all([
          canvaApi.status(),
          contentApi.getCompanies(),
          canvaApi.listCompanyMappings(),
        ])
        setStatus(s.data)
        setCompanies(extractList<any>(c))
        setMappings(extractList<any>(m))

        // Load team members for headshot management
        try {
          const t = await contentApi.getTeam()
          const list = extractList<any>(t)
          setTeamMembers(list)
        } catch (_e) {
          setTeamMembers([])
        }

        // Load proposals for test run (lightweight list endpoint)
        try {
          const p = await proposalApi.list()
          const list = extractList<any>(p)
          setProposals(list)
        } catch (_e) {
          setProposals([])
        }
      } catch (e: any) {
        setError(
          e?.response?.data?.error ||
            e?.message ||
            'Failed to load Canva integration data',
        )
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  useEffect(() => {
    // Cleanup preview URL when navigating away / changing
    return () => {
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl)
    }
  }, [pdfPreviewUrl])

  const selectedProposal = useMemo(
    () =>
      proposals.find((p) => String(p._id) === String(selectedProposalId)) ||
      null,
    [proposals, selectedProposalId],
  )

  const runCreateDesign = async (force: boolean) => {
    if (!selectedProposalId) return
    setCreatingDesign(true)
    setError(null)
    setDesignResult(null)
    try {
      const resp = await canvaApi.createDesignFromProposal(selectedProposalId, {
        force,
      })
      setDesignResult(resp.data)

      // If this proposal belongs to a different company than selected in mapping UI,
      // switch UI to that company so user sees the correct mapping.
      const proposalCompanyId = String(
        (selectedProposal as any)?.companyId || '',
      )
      if (proposalCompanyId && proposalCompanyId !== selectedCompanyId) {
        setSelectedCompanyId(proposalCompanyId)
      }
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.response?.data?.message ||
          e?.message ||
          'Failed to create Canva design',
      )
    } finally {
      setCreatingDesign(false)
    }
  }

  const generatePdfPreview = async () => {
    if (!selectedProposalId) return
    setGeneratingPreviewPdf(true)
    setError(null)
    try {
      const resp = await canvaApi.exportProposalPdf(selectedProposalId)
      const blob = new Blob([resp.data], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl)
      setPdfPreviewUrl(url)
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.response?.data?.message ||
          e?.message ||
          'Failed to generate Canva PDF preview',
      )
    } finally {
      setGeneratingPreviewPdf(false)
    }
  }

  const runValidation = async () => {
    if (!selectedProposalId) return
    setValidating(true)
    setError(null)
    setValidation(null)
    try {
      const resp = await canvaApi.validateProposal(selectedProposalId)
      setValidation(resp.data)
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.response?.data?.message ||
          e?.message ||
          'Failed to validate template',
      )
    } finally {
      setValidating(false)
    }
  }

  const refreshHeadshotLinks = async () => {
    if (!status?.connected) return
    const members = teamMembers || []
    if (members.length === 0) return
    try {
      const results = await Promise.all(
        members.map(async (m: any) => {
          try {
            const resp = await canvaApi.getTeamHeadshotLink(m.memberId)
            return { memberId: m.memberId, link: resp.data?.link || null }
          } catch {
            return { memberId: m.memberId, link: null }
          }
        }),
      )
      const next: Record<string, any> = {}
      results.forEach((r) => {
        next[String(r.memberId)] = r.link
      })
      setHeadshotLinks(next)
    } catch {
      // ignore
    }
  }

  const uploadHeadshot = async (memberId: string, memberName: string) => {
    const url = String(headshotUrls[memberId] || '').trim()
    if (!url) {
      setError('Paste a public headshot URL first.')
      return
    }
    setUploadingHeadshot((prev) => ({ ...prev, [memberId]: true }))
    setError(null)
    try {
      const resp = await canvaApi.uploadTeamHeadshotFromUrl(
        memberId,
        url,
        `${memberName} headshot`,
      )
      setHeadshotLinks((prev) => ({
        ...prev,
        [memberId]: resp.data?.link || null,
      }))
      setHeadshotUrls((prev) => ({ ...prev, [memberId]: '' }))
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to upload headshot to Canva',
      )
    } finally {
      setUploadingHeadshot((prev) => ({ ...prev, [memberId]: false }))
    }
  }

  useEffect(() => {
    // Apply saved mapping when company changes
    if (!currentMapping) {
      setSelectedTemplateId('')
      setFieldMapping({})
      setDataset({})
      return
    }
    setSelectedTemplateId(currentMapping.brandTemplateId || '')
    setFieldMapping(currentMapping.fieldMapping || {})
  }, [currentMapping])

  useEffect(() => {
    const loadLogoLink = async () => {
      setCompanyLogoLink(null)
      if (!selectedCompanyId) return
      try {
        const resp = await canvaApi.getCompanyLogoLink(selectedCompanyId)
        setCompanyLogoLink(resp.data?.link || null)
      } catch {
        setCompanyLogoLink(null)
      }
    }
    loadLogoLink()
  }, [selectedCompanyId])

  const connect = async () => {
    setError(null)
    try {
      const resp = await canvaApi.connectUrl('/integrations/canva')
      const url = resp.data?.url
      if (url) window.location.href = url
      else setError('No Canva connect URL returned')
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to start Canva connection',
      )
    }
  }

  const disconnect = async () => {
    setError(null)
    try {
      await canvaApi.disconnect()
      const s = await canvaApi.status()
      setStatus(s.data)
    } catch (e: any) {
      setError(
        e?.response?.data?.error || e?.message || 'Failed to disconnect Canva',
      )
    }
  }

  const loadTemplates = async () => {
    setTemplatesLoading(true)
    setError(null)
    try {
      const resp = await canvaApi.listBrandTemplates()
      // Canva returns { items: [...] } shape
      const items = resp.data?.items || resp.data?.data?.items || []
      setTemplates(Array.isArray(items) ? items : [])
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to load brand templates',
      )
    } finally {
      setTemplatesLoading(false)
    }
  }

  const loadDataset = async (brandTemplateId: string) => {
    if (!brandTemplateId) return
    setDatasetLoading(true)
    setError(null)
    try {
      const resp = await canvaApi.getDataset(brandTemplateId)
      const ds = resp.data?.dataset || {}
      setDataset(ds)
      // initialize mapping keys so UI renders
      setFieldMapping((prev) => ({ ...dsKeysToEmpty(ds), ...prev }))
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to load template dataset',
      )
    } finally {
      setDatasetLoading(false)
    }
  }

  const dsKeysToEmpty = (ds: any) => {
    const out: Record<string, any> = {}
    if (!ds || typeof ds !== 'object') return out
    Object.keys(ds).forEach((k) => {
      if (!out[k])
        out[k] = out[k] || { kind: '', source: '', value: '', assetId: '' }
    })
    return out
  }

  const save = async () => {
    if (!selectedCompanyId) return
    if (!selectedTemplateId) {
      setError('Select a brand template first.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const resp = await canvaApi.saveCompanyMapping(selectedCompanyId, {
        brandTemplateId: selectedTemplateId,
        fieldMapping,
      })
      // refresh mappings list
      const m = await canvaApi.listCompanyMappings()
      setMappings(extractList<any>(m))
      // keep local mapping
      setFieldMapping(resp.data?.fieldMapping || fieldMapping)
    } catch (e: any) {
      setError(
        e?.response?.data?.error || e?.message || 'Failed to save mapping',
      )
    } finally {
      setSaving(false)
    }
  }

  const uploadLogoToCanva = async () => {
    if (!selectedCompany) return
    if (!logoUrl.trim()) {
      setError('Paste a public logo URL first.')
      return
    }
    setUploadingLogo(true)
    setError(null)
    try {
      const resp = await canvaApi.uploadCompanyLogoFromUrl(
        selectedCompany.companyId,
        logoUrl.trim(),
        `${selectedCompany.name} logo`,
      )
      setCompanyLogoLink(resp.data?.link || null)
      setLogoUrl('')
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to upload logo to Canva',
      )
    } finally {
      setUploadingLogo(false)
    }
  }

  const applyCompanyLogoForField = (key: string) => {
    const assetId = String(companyLogoLink?.assetId || '').trim()
    if (!assetId) {
      setError('Company has no Canva logo asset_id yet. Upload it first.')
      return
    }
    setFieldMapping((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || {}), kind: 'asset', assetId },
    }))
  }

  const datasetKeys = Object.keys(dataset || {})
  const filteredDatasetKeys = datasetFilter.trim()
    ? datasetKeys.filter((k) =>
        k.toLowerCase().includes(datasetFilter.trim().toLowerCase()),
      )
    : datasetKeys

  const proposalsForPicker = useMemo(() => {
    const q = proposalFilter.trim().toLowerCase()
    const base = (proposals || [])
      .filter((p) => !!p?.companyId)
      .sort((a, b) => {
        const at = new Date(a?.updatedAt || a?.createdAt || 0).getTime()
        const bt = new Date(b?.updatedAt || b?.createdAt || 0).getTime()
        return bt - at
      })
    if (!q) return base
    return base.filter((p) => {
      const title = String(p?.title || '').toLowerCase()
      const pid = String(p?._id || '').toLowerCase()
      const cid = String(p?.companyId || '').toLowerCase()
      return title.includes(q) || pid.includes(q) || cid.includes(q)
    })
  }, [proposals, proposalFilter])

  const proposalPageCount = Math.max(
    1,
    Math.ceil(proposalsForPicker.length / proposalPageSize),
  )
  const proposalPageItems = proposalsForPicker.slice(
    (proposalPage - 1) * proposalPageSize,
    proposalPage * proposalPageSize,
  )

  useEffect(() => {
    setProposalPage(1)
  }, [proposalFilter])

  const getFieldDiagnostic = (key: string) => {
    const def = (dataset as any)?.[key]
    const m = fieldMapping?.[key]
    const kind = String(m?.kind || '')
    const low = String(key).toLowerCase()

    if (kind) {
      if (def?.type === 'image') {
        const assetId = String(m?.assetId || '').trim()
        if (assetId) return { tone: 'ok', text: 'Mapped image asset_id set.' }
        return {
          tone: 'warn',
          text: 'Image mapping selected but asset_id is empty.',
        }
      }
      if (kind === 'source')
        return {
          tone: 'ok',
          text: `Mapped to source: ${String(m?.source || '')}`,
        }
      if (kind === 'literal')
        return { tone: 'ok', text: 'Mapped to a literal value.' }
      return { tone: 'ok', text: 'Mapped.' }
    }

    if (def?.type === 'image') {
      if (low.includes('logo') || low.includes('company_logo')) {
        if (companyLogoLink?.assetId) {
          return {
            tone: 'info',
            text: 'Auto: will use company logo asset for this field.',
          }
        }
        return {
          tone: 'warn',
          text: 'Blank: upload company logo, then click “Use company logo”.',
        }
      }
      if (
        /(team|personnel|staff|key_personnel)[^0-9]*[0-9]{1,2}.*(photo|headshot|image)$/.test(
          low,
        )
      ) {
        return {
          tone: 'warn',
          text: 'Blank: upload team headshots below; autofill uses selected team members.',
        }
      }
      return { tone: 'warn', text: 'Blank: image field needs an asset_id.' }
    }

    if (def?.type === 'text') {
      if (low.includes('client'))
        return { tone: 'info', text: 'Auto: will try RFP client name.' }
      if (low.includes('rfp') && low.includes('title'))
        return { tone: 'info', text: 'Auto: will try RFP title.' }
      if (low.includes('submission') || low.includes('due'))
        return { tone: 'info', text: 'Auto: will try RFP submission deadline.' }
      if (low.includes('cover') && low.includes('letter'))
        return { tone: 'info', text: 'Auto: will try Cover Letter section.' }
      if (low.includes('method') || low.includes('approach'))
        return { tone: 'info', text: 'Auto: will try Methodology section.' }
      if (low.includes('deliverable'))
        return { tone: 'info', text: 'Auto: will try Deliverables section.' }
      if (low.includes('timeline') || low.includes('schedule'))
        return { tone: 'info', text: 'Auto: will try Timeline section.' }
      if (
        /(reference|past_performance)[^0-9]*[0-9]{1,2}.*(title|name|client|scope|description|summary|outcome|results)$/.test(
          low,
        )
      ) {
        return {
          tone: 'info',
          text: 'Auto: will try selected references from proposal sections.',
        }
      }
      if (
        /(team|personnel|staff|key_personnel)[^0-9]*[0-9]{1,2}.*(name|bio|biography|position|role|title)$/.test(
          low,
        )
      ) {
        return {
          tone: 'info',
          text: 'Auto: will try selected team members from proposal sections.',
        }
      }
      return {
        tone: 'warn',
        text: 'Unmapped: choose a source or literal value.',
      }
    }

    if (def?.type === 'chart')
      return {
        tone: 'warn',
        text: 'Chart fields not supported in mapping UI yet.',
      }
    return { tone: 'warn', text: 'Unmapped.' }
  }

  const mappingStats = useMemo(() => {
    const keys = datasetKeys
    let mapped = 0
    let imageMissing = 0
    const missingImageKeys: string[] = []
    keys.forEach((k) => {
      const def = (dataset as any)?.[k]
      const m = fieldMapping?.[k]
      const kind = String(m?.kind || '')
      if (kind) mapped++
      if (def?.type === 'image') {
        const assetId = String(m?.assetId || '').trim()
        if (!assetId && !companyLogoLink?.assetId) {
          imageMissing++
          missingImageKeys.push(k)
        }
      }
    })
    return { total: keys.length, mapped, imageMissing, missingImageKeys }
  }, [datasetKeys, dataset, fieldMapping, companyLogoLink])

  const autoMapCommonFields = () => {
    const next = { ...(fieldMapping || {}) }
    // Prefer mapping obvious text fields so exports are stable across templates
    Object.keys(dataset || {}).forEach((k) => {
      const key = String(k)
      const low = key.toLowerCase()
      const def = (dataset as any)?.[k]
      if (!def?.type) return
      if (def.type === 'text') {
        if (low.includes('client'))
          next[key] = { kind: 'source', source: 'rfp.clientName' }
        else if (low.includes('rfp') && low.includes('title'))
          next[key] = { kind: 'source', source: 'rfp.title' }
        else if (low.includes('submission') || low.includes('due'))
          next[key] = { kind: 'source', source: 'rfp.submissionDeadline' }
        else if (low.includes('cover') && low.includes('letter'))
          next[key] = {
            kind: 'source',
            source: 'proposal.sections.Cover Letter.content',
          }
        else if (low.includes('method') || low.includes('approach'))
          next[key] = {
            kind: 'source',
            source: 'proposal.sections.Methodology.content',
          }
        else if (low.includes('deliverable'))
          next[key] = {
            kind: 'source',
            source: 'proposal.sections.Deliverables.content',
          }
        else if (low.includes('timeline') || low.includes('schedule'))
          next[key] = {
            kind: 'source',
            source: 'proposal.sections.Timeline.content',
          }
      }
      if (
        def.type === 'image' &&
        (low.includes('logo') || low.includes('company_logo'))
      ) {
        const assetId = String(companyLogoLink?.assetId || '').trim()
        if (assetId) next[key] = { kind: 'asset', assetId }
      }
    })
    setFieldMapping(next)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Canva Integration</h1>
        <p className="mt-1 text-sm text-gray-600">
          Connect Canva Connect to generate branded proposal designs from your
          proposals using Canva Brand Templates.
        </p>
        <p className="mt-1 text-xs text-gray-500">
          Note: Brand Templates + Autofill requires Canva Enterprise for the
          connected user.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg p-3 text-sm">
          {error}
        </div>
      )}

      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-gray-900">
              Connection
            </div>
            <div className="text-sm text-gray-600 mt-1">
              {status?.connected ? 'Connected' : 'Not connected'}
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {!status?.connected ? (
              <button
                onClick={connect}
                className="px-4 py-2 rounded-md text-white bg-primary-600 hover:bg-primary-700 text-sm"
                disabled={loading}
              >
                Connect Canva
              </button>
            ) : (
              <button
                onClick={disconnect}
                className="px-4 py-2 rounded-md text-gray-700 bg-gray-100 hover:bg-gray-200 text-sm"
              >
                Disconnect
              </button>
            )}
          </div>
        </div>

        {status?.connected && Array.isArray(status?.connection?.scopes) && (
          <div className="mt-4">
            <div className="text-xs font-semibold text-gray-700">Scopes</div>
            <div className="mt-1 text-xs text-gray-600">
              {status.connection.scopes.join(', ')}
            </div>
          </div>
        )}
      </div>

      <div className="bg-white shadow rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-gray-900">
              Company → Brand Template Mapping
            </div>
            <div className="text-xs text-gray-600 mt-1">
              Choose a company and a Canva Brand Template, then map dataset
              fields to proposal/RFP fields.
            </div>
          </div>
          <button
            onClick={loadTemplates}
            className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 disabled:opacity-50"
            disabled={!status?.connected || templatesLoading}
            title={
              !status?.connected
                ? 'Connect Canva first'
                : 'Load templates from Canva'
            }
          >
            {templatesLoading ? 'Loading templates…' : 'Load templates'}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Company
            </label>
            <select
              value={selectedCompanyId}
              onChange={(e) => setSelectedCompanyId(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
            >
              <option value="">Select company</option>
              {companies.map((c) => (
                <option key={c.companyId} value={c.companyId}>
                  {c.name}
                </option>
              ))}
            </select>
            {selectedCompany && (
              <div className="mt-1 text-xs text-gray-500">
                Selected: {selectedCompany.name}
              </div>
            )}
            {selectedCompany && (
              <div className="mt-3 border border-gray-200 rounded-lg p-3 bg-gray-50">
                <div className="text-xs font-semibold text-gray-800">
                  Company Canva assets
                </div>
                <div className="mt-1 text-xs text-gray-700">
                  Logo asset_id:{' '}
                  <span className="font-mono">
                    {companyLogoLink?.assetId || '—'}
                  </span>
                </div>
                <div className="mt-2 flex items-center space-x-2">
                  <input
                    value={logoUrl}
                    onChange={(e) => setLogoUrl(e.target.value)}
                    placeholder="Public logo URL (png/jpg)"
                    className="flex-1 border border-gray-300 rounded-md px-3 py-2 bg-white text-gray-900 text-sm"
                  />
                  <button
                    onClick={uploadLogoToCanva}
                    disabled={!status?.connected || uploadingLogo}
                    className="px-3 py-2 rounded-md text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                    title="Uploads the logo to Canva and stores an asset link"
                  >
                    {uploadingLogo ? 'Uploading…' : 'Upload'}
                  </button>
                </div>
                <div className="mt-2 text-[11px] text-gray-500">
                  The URL must be public (Canva fetches it directly).
                </div>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Brand Template
            </label>
            <select
              value={selectedTemplateId}
              onChange={(e) => {
                const next = e.target.value
                setSelectedTemplateId(next)
                if (next) loadDataset(next)
              }}
              className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
              disabled={!selectedCompanyId}
            >
              <option value="">Select template</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title || t.name || t.id}
                </option>
              ))}
            </select>
            <div className="mt-1 text-xs text-gray-500">
              Tip: templates list requires Canva Enterprise access.
            </div>
          </div>
        </div>

        {selectedTemplateId && (
          <div className="pt-2">
            <button
              onClick={() => loadDataset(selectedTemplateId)}
              className="text-sm text-primary-600 hover:text-primary-800"
              disabled={datasetLoading}
            >
              {datasetLoading ? 'Loading dataset…' : 'Refresh dataset fields'}
            </button>
          </div>
        )}

        {datasetKeys.length > 0 && (
          <div className="border-t border-gray-200 pt-4">
            <div className="text-sm font-semibold text-gray-900">
              Dataset field mappings
            </div>
            <div className="mt-1 text-xs text-gray-600">
              For text fields, choose a source (RFP/proposal field) or set a
              literal value. For image fields, provide a Canva asset ID.
            </div>

            <div className="mt-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div className="text-xs text-gray-600">
                Fields:{' '}
                <span className="font-semibold">{mappingStats.total}</span> •
                Mapped:{' '}
                <span className="font-semibold">{mappingStats.mapped}</span>
                {mappingStats.imageMissing > 0 && (
                  <>
                    {' '}
                    • Image fields needing assets:{' '}
                    <span className="font-semibold">
                      {mappingStats.imageMissing}
                    </span>
                  </>
                )}
              </div>
              <div className="flex items-center gap-2">
                <input
                  value={datasetFilter}
                  onChange={(e) => setDatasetFilter(e.target.value)}
                  placeholder="Filter fields…"
                  className="border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
                />
                <button
                  onClick={autoMapCommonFields}
                  className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200"
                  disabled={!selectedTemplateId}
                  title="Auto-map common fields (client, title, deadlines, cover letter, etc.)"
                >
                  Auto-map
                </button>
              </div>
            </div>

            {mappingStats.imageMissing > 0 && (
              <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
                <div className="text-xs font-semibold text-amber-900">
                  Some image fields will stay blank unless you upload assets.
                </div>
                <div className="mt-1 text-xs text-amber-800">
                  Tip: upload company logo above, and team headshots below.
                </div>
              </div>
            )}

            <div className="mt-4 space-y-3">
              {filteredDatasetKeys.slice(0, 60).map((key) => {
                const def = dataset[key]
                const m = fieldMapping[key] || {
                  kind: '',
                  source: '',
                  value: '',
                  assetId: '',
                }
                const diag = getFieldDiagnostic(key)
                return (
                  <div
                    key={key}
                    className="border border-gray-200 rounded-lg p-3"
                  >
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium text-gray-900 break-all">
                        {key}
                      </div>
                      <div className="text-xs text-gray-500">{def?.type}</div>
                    </div>
                    <div
                      className={`mt-1 text-xs ${
                        diag.tone === 'ok'
                          ? 'text-green-700'
                          : diag.tone === 'info'
                          ? 'text-slate-700'
                          : 'text-amber-700'
                      }`}
                    >
                      {diag.text}
                    </div>

                    {def?.type === 'text' && (
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                        <select
                          value={m.kind || ''}
                          onChange={(e) => {
                            const nextKind = e.target.value
                            setFieldMapping((prev) => ({
                              ...prev,
                              [key]: { ...(prev[key] || {}), kind: nextKind },
                            }))
                          }}
                          className="border border-gray-300 rounded-md px-2 py-2 bg-gray-100 text-gray-900 text-sm"
                        >
                          <option value="">(leave empty)</option>
                          <option value="source">Source</option>
                          <option value="literal">Literal</option>
                        </select>

                        {m.kind === 'source' && (
                          <select
                            value={m.source || ''}
                            onChange={(e) => {
                              const next = e.target.value
                              setFieldMapping((prev) => ({
                                ...prev,
                                [key]: {
                                  ...(prev[key] || {}),
                                  kind: 'source',
                                  source: next,
                                },
                              }))
                            }}
                            className="border border-gray-300 rounded-md px-2 py-2 bg-gray-100 text-gray-900 text-sm md:col-span-2"
                          >
                            <option value="">Select source</option>
                            {SOURCE_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        )}

                        {m.kind === 'literal' && (
                          <input
                            value={m.value || ''}
                            onChange={(e) => {
                              const next = e.target.value
                              setFieldMapping((prev) => ({
                                ...prev,
                                [key]: {
                                  ...(prev[key] || {}),
                                  kind: 'literal',
                                  value: next,
                                },
                              }))
                            }}
                            placeholder="Literal text"
                            className="border border-gray-300 rounded-md px-2 py-2 bg-gray-100 text-gray-900 text-sm md:col-span-2"
                          />
                        )}
                      </div>
                    )}

                    {def?.type === 'image' && (
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className="text-sm text-gray-700">
                          Image fields require a Canva{' '}
                          <span className="font-medium">asset_id</span>.
                        </div>
                        <input
                          value={m.assetId || ''}
                          onChange={(e) => {
                            const next = e.target.value
                            setFieldMapping((prev) => ({
                              ...prev,
                              [key]: {
                                ...(prev[key] || {}),
                                kind: 'asset',
                                assetId: next,
                              },
                            }))
                          }}
                          placeholder="asset_id"
                          className="border border-gray-300 rounded-md px-2 py-2 bg-gray-100 text-gray-900 text-sm md:col-span-2"
                        />
                        <div className="md:col-span-3">
                          <button
                            onClick={() => applyCompanyLogoForField(key)}
                            className="text-xs text-primary-600 hover:text-primary-800"
                            disabled={!selectedCompanyId}
                            title="Set this field to the selected company's Canva logo asset"
                          >
                            Use company logo
                          </button>
                        </div>
                      </div>
                    )}

                    {def?.type === 'chart' && (
                      <div className="mt-2 text-xs text-gray-500">
                        Chart fields are not handled in the MVP mapping UI yet.
                      </div>
                    )}
                  </div>
                )
              })}

              {datasetKeys.length > 60 && (
                <div className="text-xs text-gray-500">
                  Showing first 60 fields. If your template has more, we can
                  expand this.
                </div>
              )}
            </div>
          </div>
        )}

        <div className="pt-2 flex items-center justify-end">
          <button
            onClick={save}
            disabled={
              !status?.connected ||
              !selectedCompanyId ||
              !selectedTemplateId ||
              saving
            }
            className="px-4 py-2 rounded-md text-white bg-primary-600 hover:bg-primary-700 text-sm disabled:opacity-50"
            title={!status?.connected ? 'Connect Canva first' : 'Save mapping'}
          >
            {saving ? 'Saving…' : 'Save mapping'}
          </button>
        </div>
      </div>

      {/* Test run / preview */}
      <div className="bg-white shadow rounded-lg p-6 space-y-4">
        <div>
          <div className="text-sm font-semibold text-gray-900">
            Test run (generate Canva design + preview PDF)
          </div>
          <div className="text-xs text-gray-600 mt-1">
            Pick a proposal, generate/reuse its Canva design, open in Canva, or
            render a PDF preview.
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Proposal
            </label>
            <input
              value={proposalFilter}
              onChange={(e) => setProposalFilter(e.target.value)}
              placeholder="Search proposals…"
              className="mb-2 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
            />
            <select
              value={selectedProposalId}
              onChange={(e) => {
                setSelectedProposalId(e.target.value)
                setDesignResult(null)
                if (pdfPreviewUrl) {
                  URL.revokeObjectURL(pdfPreviewUrl)
                  setPdfPreviewUrl(null)
                }
              }}
              className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
              disabled={proposals.length === 0}
            >
              <option value="">Select proposal</option>
              {proposalPageItems.map((p) => (
                <option key={p._id} value={p._id}>
                  {p.title}
                </option>
              ))}
            </select>
            <div className="mt-1 text-xs text-gray-500">
              Only proposals with a selected company/branding are listed.
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-gray-600">
              <div>
                Showing {(proposalPage - 1) * proposalPageSize + 1}-
                {Math.min(
                  proposalPage * proposalPageSize,
                  proposalsForPicker.length,
                )}{' '}
                of {proposalsForPicker.length}
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                  onClick={() => setProposalPage((p) => Math.max(1, p - 1))}
                  disabled={proposalPage <= 1}
                >
                  Prev
                </button>
                <span>
                  {proposalPage}/{proposalPageCount}
                </span>
                <button
                  className="px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
                  onClick={() =>
                    setProposalPage((p) => Math.min(proposalPageCount, p + 1))
                  }
                  disabled={proposalPage >= proposalPageCount}
                >
                  Next
                </button>
              </div>
            </div>
            {selectedProposal && (
              <div className="mt-2 text-xs text-gray-600">
                CompanyId:{' '}
                <span className="font-mono">
                  {String((selectedProposal as any).companyId)}
                </span>
              </div>
            )}
          </div>

          <div className="flex flex-col justify-end gap-2">
            <div className="flex items-center gap-2">
              <button
                onClick={() => runCreateDesign(false)}
                disabled={
                  !status?.connected || !selectedProposalId || creatingDesign
                }
                className="px-3 py-2 rounded-md text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {creatingDesign ? 'Generating…' : 'Generate / Reuse design'}
              </button>
              <button
                onClick={() => runCreateDesign(true)}
                disabled={
                  !status?.connected || !selectedProposalId || creatingDesign
                }
                className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 disabled:opacity-50"
                title="Forces a rebuild even if cached"
              >
                Force rebuild
              </button>
            </div>
            <button
              onClick={runValidation}
              disabled={!status?.connected || !selectedProposalId || validating}
              className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 disabled:opacity-50"
              title="Simulate how the template will fill (no Canva design created)"
            >
              {validating ? 'Validating…' : 'Validate template fill'}
            </button>
            <button
              onClick={generatePdfPreview}
              disabled={
                !status?.connected ||
                !selectedProposalId ||
                generatingPreviewPdf
              }
              className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 disabled:opacity-50"
            >
              {generatingPreviewPdf ? 'Rendering PDF…' : 'Generate PDF preview'}
            </button>
          </div>
        </div>

        {validation?.ok && Array.isArray(validation?.results) && (
          <div className="border border-gray-200 rounded-lg p-4 bg-white">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div className="text-sm font-semibold text-gray-900">
                Validation report
              </div>
              <div className="text-xs text-gray-600">
                Total:{' '}
                <span className="font-semibold">
                  {validation?.totals?.total ?? '-'}
                </span>{' '}
                • Filled:{' '}
                <span className="font-semibold">
                  {validation?.totals?.filled ?? '-'}
                </span>{' '}
                • Blank:{' '}
                <span className="font-semibold">
                  {validation?.totals?.blank ?? '-'}
                </span>{' '}
                • Unsupported:{' '}
                <span className="font-semibold">
                  {validation?.totals?.unsupported ?? '-'}
                </span>
              </div>
            </div>

            <div className="mt-3 flex items-center gap-2">
              <input
                value={validationFilter}
                onChange={(e) => setValidationFilter(e.target.value)}
                placeholder="Filter report…"
                className="w-full sm:w-96 border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
              />
              <button
                onClick={() => setValidationFilter('')}
                className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200"
              >
                Clear
              </button>
            </div>

            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Key
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Type
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Source
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Preview / Reason
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {validation.results
                    .filter((r: any) => {
                      const q = validationFilter.trim().toLowerCase()
                      if (!q) return true
                      return (
                        String(r?.key || '')
                          .toLowerCase()
                          .includes(q) ||
                        String(r?.reason || '')
                          .toLowerCase()
                          .includes(q) ||
                        String(r?.preview || '')
                          .toLowerCase()
                          .includes(q) ||
                        String(r?.source || '')
                          .toLowerCase()
                          .includes(q)
                      )
                    })
                    .slice(0, 200)
                    .map((r: any) => (
                      <tr key={r.key} className="hover:bg-gray-50">
                        <td className="px-3 py-2 text-xs text-gray-900 font-mono break-all">
                          {r.key}
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-700">
                          {r.fieldType}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          <span
                            className={`px-2 py-1 rounded-full ${
                              r.source === 'mapped'
                                ? 'bg-green-100 text-green-800'
                                : r.source === 'auto'
                                ? 'bg-slate-100 text-slate-800'
                                : r.source === 'unsupported'
                                ? 'bg-gray-100 text-gray-700'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            {r.source}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-700">
                          {r.filled ? (
                            <span className="text-gray-900">{r.preview}</span>
                          ) : (
                            <span className="text-amber-800">{r.reason}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {validation.results.length > 200 && (
                <div className="mt-2 text-xs text-gray-500">
                  Showing first 200 rows. Use filter to narrow further.
                </div>
              )}
            </div>
          </div>
        )}

        {designResult?.design?.urls?.edit_url && (
          <div className="border border-gray-200 rounded-lg p-3 bg-gray-50">
            <div className="text-xs font-semibold text-gray-800">
              Canva design
            </div>
            <div className="mt-1 text-xs text-gray-700">
              Cached:{' '}
              <span className="font-semibold">
                {String(!!designResult?.cached)}
              </span>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <a
                href={designResult.design.urls.edit_url}
                target="_blank"
                rel="noreferrer"
                className="text-sm text-primary-600 hover:text-primary-800"
              >
                Open edit link →
              </a>
              {designResult.design.urls.view_url && (
                <a
                  href={designResult.design.urls.view_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-primary-600 hover:text-primary-800"
                >
                  Open view link →
                </a>
              )}
            </div>
            {designResult?.meta?.lastGeneratedAt && (
              <div className="mt-2 text-[11px] text-gray-500">
                Last generated: {String(designResult.meta.lastGeneratedAt)}
              </div>
            )}
          </div>
        )}

        {pdfPreviewUrl && (
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-900">
              PDF preview (Canva export)
            </div>
            <iframe
              src={pdfPreviewUrl}
              className="w-full"
              style={{ height: 600 }}
              title="Canva PDF preview"
            />
          </div>
        )}
      </div>

      {/* Team headshots */}
      <div className="bg-white shadow rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-gray-900">
              Team headshots (Canva assets)
            </div>
            <div className="text-xs text-gray-600 mt-1">
              Upload each headshot once; dataset fields like team_member_1_photo
              will autofill from selected team members.
            </div>
          </div>
          <button
            onClick={refreshHeadshotLinks}
            className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 disabled:opacity-50"
            disabled={!status?.connected || teamMembers.length === 0}
            title="Fetch stored headshot asset links"
          >
            Refresh headshot status
          </button>
        </div>

        {teamMembers.length === 0 ? (
          <div className="text-sm text-gray-500">No team members found.</div>
        ) : (
          <div className="space-y-3">
            {teamMembers.slice(0, 30).map((m: any) => {
              const memberId = String(m.memberId)
              const link = headshotLinks[memberId]
              const busy = !!uploadingHeadshot[memberId]
              return (
                <div
                  key={memberId}
                  className="border border-gray-200 rounded-lg p-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">
                        {m.nameWithCredentials}
                      </div>
                      <div className="text-xs text-gray-600">{m.position}</div>
                      <div className="mt-1 text-xs text-gray-700">
                        Headshot asset_id:{' '}
                        <span className="font-mono">
                          {link?.assetId || '—'}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-2 flex items-center space-x-2">
                    <input
                      value={headshotUrls[memberId] || ''}
                      onChange={(e) =>
                        setHeadshotUrls((prev) => ({
                          ...prev,
                          [memberId]: e.target.value,
                        }))
                      }
                      placeholder="Public headshot URL (png/jpg)"
                      className="flex-1 border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
                    />
                    <button
                      onClick={() =>
                        uploadHeadshot(memberId, m.nameWithCredentials)
                      }
                      disabled={!status?.connected || busy}
                      className="px-3 py-2 rounded-md text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                    >
                      {busy ? 'Uploading…' : 'Upload'}
                    </button>
                  </div>
                  <div className="mt-2 text-[11px] text-gray-500">
                    URL must be public (Canva fetches it directly).
                  </div>
                </div>
              )
            })}

            {teamMembers.length > 30 && (
              <div className="text-xs text-gray-500">
                Showing first 30 team members. (We can add paging/search.)
              </div>
            )}
          </div>
        )}
      </div>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
    </div>
  )
}

