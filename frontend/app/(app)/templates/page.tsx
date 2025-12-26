'use client'

import Button from '@/components/ui/Button'
import PipelineContextBanner from '@/components/ui/PipelineContextBanner'
import StepsPanel from '@/components/ui/StepsPanel'
import { useToast } from '@/components/ui/Toast'
import {
  canvaApi,
  contentApi,
  extractList,
  proposalApi,
  rfpApi,
} from '@/lib/api'
import { getContentLibraryType } from '@/utils/proposalHelpers'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

type CanvaBrandTemplate = { id: string; title?: string; name?: string }
type CanvaDataset = Record<string, { type: 'text' | 'image' | 'chart' }>

const SOURCE_OPTIONS: { label: string; value: string }[] = [
  { label: 'RFP Title', value: 'rfp.title' },
  { label: 'Client Name', value: 'rfp.clientName' },
  { label: 'Submission Deadline', value: 'rfp.submissionDeadline' },
  { label: 'Project Deadline', value: 'rfp.projectDeadline' },
  { label: 'Proposal Title', value: 'proposal.title' },
  { label: 'Cover Letter', value: 'proposal.sections.Cover Letter.content' },
  { label: 'Methodology', value: 'proposal.sections.Methodology.content' },
  { label: 'Deliverables', value: 'proposal.sections.Deliverables.content' },
  { label: 'Timeline', value: 'proposal.sections.Timeline.content' },
  { label: 'Team', value: 'proposal.sections.Team.content' },
  { label: 'References', value: 'proposal.sections.References.content' },
]

export default function TemplatesPage() {
  const router = useRouter()
  const { success, error: showError, info } = useToast()
  const [loading, setLoading] = useState(true)

  const [status, setStatus] = useState<any>(null)
  const [companies, setCompanies] = useState<any[]>([])
  const [companyMappings, setCompanyMappings] = useState<any[]>([])

  const [brandTemplates, setBrandTemplates] = useState<CanvaBrandTemplate[]>([])
  const [brandTemplatesLoading, setBrandTemplatesLoading] = useState(false)
  const [brandTemplateQuery, setBrandTemplateQuery] = useState('')

  const [rfps, setRfps] = useState<any[]>([])
  const [rfpsLoading, setRfpsLoading] = useState(false)
  const [rfpQuery, setRfpQuery] = useState('')

  const [teamMembers, setTeamMembers] = useState<any[]>([])
  const [teamLoading, setTeamLoading] = useState(false)
  const [teamQuery, setTeamQuery] = useState('')
  const [selectedTeamIds, setSelectedTeamIds] = useState<string[]>([])

  const [selectedCompanyId, setSelectedCompanyId] = useState<string>('')
  const [selectedBrandTemplateId, setSelectedBrandTemplateId] =
    useState<string>('')
  const [selectedRfpId, setSelectedRfpId] = useState<string>('')

  const [submitting, setSubmitting] = useState(false)
  const [designResult, setDesignResult] = useState<any>(null)

  // ---- Template setup (mapping + assets) ----
  const [dataset, setDataset] = useState<CanvaDataset>({})
  const [datasetLoading, setDatasetLoading] = useState(false)
  const [datasetFilter, setDatasetFilter] = useState('')
  const [fieldMapping, setFieldMapping] = useState<Record<string, any>>({})
  const [savingMapping, setSavingMapping] = useState(false)

  const [logoUrl, setLogoUrl] = useState('')
  const [uploadingLogo, setUploadingLogo] = useState(false)
  const [companyLogoLink, setCompanyLogoLink] = useState<any>(null)

  const [headshotLinks, setHeadshotLinks] = useState<Record<string, any>>({})
  const [headshotUrls, setHeadshotUrls] = useState<Record<string, string>>({})
  const [uploadingHeadshot, setUploadingHeadshot] = useState<
    Record<string, boolean>
  >({})

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setDesignResult(null)
      try {
        const [s, c, m] = await Promise.all([
          canvaApi.status(),
          contentApi.getCompanies(),
          canvaApi.listCompanyMappings(),
        ])
        setStatus(s.data)
        const companiesList = extractList<any>(c)
        setCompanies(companiesList)
        setCompanyMappings(extractList<any>(m))

        // Default company selection (prefer Polaris if present)
        if (!selectedCompanyId && companiesList.length > 0) {
          const polaris = companiesList.find((co) =>
            String(co?.name || '')
              .toLowerCase()
              .includes('polaris'),
          )
          setSelectedCompanyId(String((polaris || companiesList[0])?.companyId))
        }
      } catch (e: any) {
        showError(
          e?.response?.data?.error ||
            e?.message ||
            'Failed to load Canva templates page',
        )
      } finally {
        setLoading(false)
      }
    }
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connect = async () => {
    try {
      const resp = await canvaApi.connectUrl('/templates')
      const url = resp.data?.url
      if (url) window.location.href = url
      else showError('No Canva connect URL returned')
    } catch (e: any) {
      showError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to start Canva connection',
      )
    }
  }

  const disconnect = async () => {
    try {
      await canvaApi.disconnect()
      const s = await canvaApi.status()
      setStatus(s.data)
      success('Disconnected Canva')
    } catch (e: any) {
      showError(
        e?.response?.data?.error || e?.message || 'Failed to disconnect Canva',
      )
    }
  }

  const loadBrandTemplates = async (query?: string) => {
    setBrandTemplatesLoading(true)
    try {
      const resp = await canvaApi.listBrandTemplates(query?.trim() || '')
      const items = resp.data?.items || resp.data?.data?.items || []
      setBrandTemplates(Array.isArray(items) ? items : [])
    } catch (e: any) {
      showError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to load Canva templates',
      )
      setBrandTemplates([])
    } finally {
      setBrandTemplatesLoading(false)
    }
  }

  const loadRfps = async () => {
    setRfpsLoading(true)
    try {
      const resp = await rfpApi.list({ limit: 200 })
      setRfps(extractList<any>(resp))
    } catch (e: any) {
      showError(
        e?.response?.data?.detail || e?.message || 'Failed to load RFPs',
      )
      setRfps([])
    } finally {
      setRfpsLoading(false)
    }
  }

  const loadTeam = async () => {
    setTeamLoading(true)
    try {
      const resp = await contentApi.getTeam()
      setTeamMembers(extractList<any>(resp))
    } catch (e: any) {
      showError(
        e?.response?.data?.detail || e?.message || 'Failed to load team',
      )
      setTeamMembers([])
    } finally {
      setTeamLoading(false)
    }
  }

  const currentCompanyMapping = useMemo(() => {
    if (!selectedCompanyId) return null
    return (
      companyMappings.find(
        (m) => String(m.companyId) === String(selectedCompanyId),
      ) || null
    )
  }, [companyMappings, selectedCompanyId])

  const selectedCompany = useMemo(() => {
    if (!selectedCompanyId) return null
    return (
      companies.find(
        (c) => String(c.companyId) === String(selectedCompanyId),
      ) || null
    )
  }, [companies, selectedCompanyId])

  // When switching companies, prefill mapping state + load logo link.
  useEffect(() => {
    const applyExisting = async () => {
      // mapping
      if (currentCompanyMapping?.fieldMapping) {
        setFieldMapping(
          typeof currentCompanyMapping.fieldMapping === 'object'
            ? currentCompanyMapping.fieldMapping
            : {},
        )
      } else {
        setFieldMapping({})
      }

      // If user hasn't chosen a template yet, default to the mapped one (if any)
      const mappedTid = String(
        currentCompanyMapping?.brandTemplateId || '',
      ).trim()
      if (!selectedBrandTemplateId && mappedTid) {
        setSelectedBrandTemplateId(mappedTid)
      }

      // logo link
      setCompanyLogoLink(null)
      if (!selectedCompanyId) return
      try {
        const resp = await canvaApi.getCompanyLogoLink(selectedCompanyId)
        setCompanyLogoLink(resp.data?.link || null)
      } catch {
        setCompanyLogoLink(null)
      }
    }
    void applyExisting()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCompanyId])

  const dsKeysToEmpty = (ds: any) => {
    const out: Record<string, any> = {}
    if (!ds || typeof ds !== 'object') return out
    Object.keys(ds).forEach((k) => {
      out[k] = out[k] || { kind: '', source: '', value: '', assetId: '' }
    })
    return out
  }

  const loadDataset = async (brandTemplateId: string) => {
    if (!brandTemplateId) return
    setDatasetLoading(true)
    try {
      const resp = await canvaApi.getDataset(brandTemplateId)
      const ds = (resp.data?.dataset || {}) as CanvaDataset
      setDataset(ds)
      setFieldMapping((prev) => ({ ...dsKeysToEmpty(ds), ...(prev || {}) }))
    } catch (e: any) {
      showError(
        e?.response?.data?.error ||
          e?.message ||
          'Failed to load template dataset',
      )
      setDataset({})
    } finally {
      setDatasetLoading(false)
    }
  }

  useEffect(() => {
    if (!selectedBrandTemplateId) {
      setDataset({})
      return
    }
    if (!status?.connected) return
    void loadDataset(selectedBrandTemplateId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBrandTemplateId, status?.connected])

  const datasetKeys = useMemo(() => Object.keys(dataset || {}), [dataset])
  const filteredDatasetKeys = useMemo(() => {
    const q = datasetFilter.trim().toLowerCase()
    if (!q) return datasetKeys
    return datasetKeys.filter((k) => k.toLowerCase().includes(q))
  }, [datasetKeys, datasetFilter])

  const applyCompanyLogoForField = (key: string) => {
    const assetId = String(companyLogoLink?.assetId || '').trim()
    if (!assetId) {
      info('Company has no Canva logo asset_id yet. Upload it first.')
      return
    }
    setFieldMapping((prev) => ({
      ...(prev || {}),
      [key]: { ...((prev || {})[key] || {}), kind: 'asset', assetId },
    }))
  }

  const autoMapCommonFields = () => {
    const next = { ...(fieldMapping || {}) }
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
    success('Auto-mapped common fields')
  }

  const saveMapping = async () => {
    if (!selectedCompanyId) {
      info('Select a company first')
      return
    }
    if (!selectedBrandTemplateId) {
      info('Select a Canva template first')
      return
    }
    setSavingMapping(true)
    try {
      await canvaApi.saveCompanyMapping(selectedCompanyId, {
        brandTemplateId: selectedBrandTemplateId,
        fieldMapping: fieldMapping || {},
      })
      const m = await canvaApi.listCompanyMappings()
      setCompanyMappings(extractList<any>(m))
      success('Saved Canva mapping')
    } catch (e: any) {
      showError(
        e?.response?.data?.error || e?.message || 'Failed to save mapping',
      )
    } finally {
      setSavingMapping(false)
    }
  }

  const uploadLogoToCanva = async () => {
    if (!selectedCompany) {
      info('Select a company first')
      return
    }
    const url = String(logoUrl || '').trim()
    if (!url) {
      info('Paste a public logo URL first')
      return
    }
    setUploadingLogo(true)
    try {
      const resp = await canvaApi.uploadCompanyLogoFromUrl(
        selectedCompany.companyId,
        url,
        `${selectedCompany.name} logo`,
      )
      setCompanyLogoLink(resp.data?.link || null)
      setLogoUrl('')
      success('Uploaded company logo to Canva')
    } catch (e: any) {
      showError(
        e?.response?.data?.error || e?.message || 'Failed to upload logo',
      )
    } finally {
      setUploadingLogo(false)
    }
  }

  const refreshHeadshotLinks = async () => {
    if (!status?.connected) {
      info('Connect Canva first')
      return
    }
    const members = teamMembers || []
    if (members.length === 0) {
      await loadTeam()
      return
    }
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
      success('Refreshed headshot status')
    } catch {
      // ignore
    }
  }

  const uploadHeadshot = async (memberId: string, memberName: string) => {
    const url = String(headshotUrls[memberId] || '').trim()
    if (!url) {
      info('Paste a public headshot URL first')
      return
    }
    setUploadingHeadshot((prev) => ({ ...(prev || {}), [memberId]: true }))
    try {
      const resp = await canvaApi.uploadTeamHeadshotFromUrl(
        memberId,
        url,
        `${memberName} headshot`,
      )
      setHeadshotLinks((prev) => ({
        ...(prev || {}),
        [memberId]: resp.data?.link || null,
      }))
      setHeadshotUrls((prev) => ({ ...(prev || {}), [memberId]: '' }))
      success('Uploaded headshot to Canva')
    } catch (e: any) {
      showError(
        e?.response?.data?.error || e?.message || 'Failed to upload headshot',
      )
    } finally {
      setUploadingHeadshot((prev) => ({ ...(prev || {}), [memberId]: false }))
    }
  }

  const filteredBrandTemplates = useMemo(() => {
    const q = brandTemplateQuery.trim().toLowerCase()
    if (!q) return brandTemplates
    return (brandTemplates || []).filter((t) => {
      const name = String(t.title || t.name || '').toLowerCase()
      const id = String(t.id || '').toLowerCase()
      return name.includes(q) || id.includes(q)
    })
  }, [brandTemplates, brandTemplateQuery])

  const filteredRfps = useMemo(() => {
    const q = rfpQuery.trim().toLowerCase()
    if (!q) return rfps
    return (rfps || []).filter((r) => {
      const title = String(r?.title || '').toLowerCase()
      const client = String(r?.clientName || '').toLowerCase()
      const id = String(r?._id || '').toLowerCase()
      return title.includes(q) || client.includes(q) || id.includes(q)
    })
  }, [rfps, rfpQuery])

  const filteredTeam = useMemo(() => {
    const q = teamQuery.trim().toLowerCase()
    if (!q) return teamMembers
    return (teamMembers || []).filter((m) => {
      const name = String(m?.nameWithCredentials || '').toLowerCase()
      const pos = String(m?.position || '').toLowerCase()
      return name.includes(q) || pos.includes(q)
    })
  }, [teamMembers, teamQuery])

  const toggleTeam = (memberId: string) => {
    setSelectedTeamIds((prev) =>
      prev.includes(memberId)
        ? prev.filter((x) => x !== memberId)
        : [...prev, memberId],
    )
  }

  const ensureCompanyMapping = async (
    companyId: string,
    brandTemplateId: string,
  ) => {
    if (!companyId || !brandTemplateId) return
    const existing =
      companyMappings.find((m) => String(m.companyId) === String(companyId)) ||
      null
    if (
      existing &&
      String(existing.brandTemplateId) === String(brandTemplateId)
    )
      return

    const fieldMapping =
      existing?.fieldMapping && typeof existing.fieldMapping === 'object'
        ? existing.fieldMapping
        : {}
    await canvaApi.saveCompanyMapping(companyId, {
      brandTemplateId,
      fieldMapping,
    })
    const m = await canvaApi.listCompanyMappings()
    setCompanyMappings(extractList<any>(m))
  }

  const findTeamSectionName = (sections: any): string | null => {
    const obj = sections && typeof sections === 'object' ? sections : {}
    const keys = Object.keys(obj)
    for (const k of keys) {
      const typ = getContentLibraryType(k)
      if (typ === 'team') return k
    }
    return null
  }

  const createFromSelections = async () => {
    if (!status?.connected) {
      info('Connect Canva first')
      return
    }
    if (!selectedCompanyId) {
      info('Select a company/branding')
      return
    }
    if (!selectedBrandTemplateId) {
      info('Select a Canva template')
      return
    }
    if (!selectedRfpId) {
      info('Select an RFP')
      return
    }

    setSubmitting(true)
    setDesignResult(null)
    try {
      await ensureCompanyMapping(selectedCompanyId, selectedBrandTemplateId)

      const rfp = rfps.find((r) => String(r?._id) === String(selectedRfpId))
      const titleBase = String(rfp?.title || 'RFP').trim()

      const proposalResp = await proposalApi.generate({
        rfpId: selectedRfpId,
        templateId: 'ai-template',
        title: `Canva proposal for ${titleBase.slice(0, 60)}`,
        companyId: selectedCompanyId,
        customContent: {},
      })

      const proposalId = String((proposalResp.data as any)?._id || '')
      const proposalSections = (proposalResp.data as any)?.sections

      if (proposalId && selectedTeamIds.length > 0) {
        const teamSection = findTeamSectionName(proposalSections)
        if (teamSection) {
          await proposalApi.updateContentLibrarySection(
            proposalId,
            teamSection,
            {
              type: 'team',
              selectedIds: selectedTeamIds,
            },
          )
        }
      }

      const designResp = await canvaApi.createDesignFromProposal(proposalId)
      setDesignResult({ ...designResp.data, proposalId })
      success('Created Canva design')
    } catch (e: any) {
      showError(
        e?.response?.data?.error ||
          e?.response?.data?.detail ||
          e?.message ||
          'Failed to create Canva design',
      )
    } finally {
      setSubmitting(false)
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
      <PipelineContextBanner
        variant="secondary"
        title="Templates support the Pipeline workflow."
        description="Use them to generate polished proposal outputs."
        rightSlot={
          <Button as={Link} href="/proposals" variant="ghost" size="sm">
            Go to Proposals
          </Button>
        }
      />

      <StepsPanel
        title="Quick flow"
        tone="blue"
        columns={3}
        steps={[
          {
            title: 'Connect Canva',
            description: 'Connect once for your user.',
          },
          {
            title: 'Select inputs',
            description: 'Choose branding, template, RFP, and team.',
          },
          {
            title: 'Generate output',
            description:
              'Create a proposal + Canva design, then continue in Pipeline.',
          },
        ]}
      />
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Canva Templates</h1>
          <p className="mt-1 text-sm text-gray-600">
            Pick a Canva template, RFP, and team members — we’ll generate the
            design automatically.
          </p>
        </div>
        <div className="text-xs text-gray-500">
          {status?.connected ? 'Canva connected' : 'Canva not connected'}
        </div>
      </div>

      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-gray-900">
              Canva connection
            </div>
            <div className="text-xs text-gray-600 mt-1">
              {status?.connected ? 'Connected' : 'Not connected'}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!status?.connected ? (
              <button
                onClick={connect}
                className="px-4 py-2 rounded-md text-white bg-primary-600 hover:bg-primary-700 text-sm"
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
      </div>

      <div className="bg-white shadow rounded-lg p-6 space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Company / branding
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
            {currentCompanyMapping?.brandTemplateId && (
              <div className="mt-1 text-xs text-gray-500">
                Current mapped Canva template:{' '}
                <span className="font-mono">
                  {String(currentCompanyMapping.brandTemplateId)}
                </span>
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-900 mb-2">
                Canva template
              </label>
              <button
                onClick={() => loadBrandTemplates()}
                className="text-xs text-primary-600 hover:text-primary-800"
                disabled={!status?.connected || brandTemplatesLoading}
                title={
                  !status?.connected
                    ? 'Connect Canva first'
                    : 'Load templates from Canva'
                }
              >
                {brandTemplatesLoading ? 'Loading…' : 'Load'}
              </button>
            </div>
            <input
              value={brandTemplateQuery}
              onChange={(e) => setBrandTemplateQuery(e.target.value)}
              placeholder="Filter templates…"
              className="mb-2 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
            />
            <select
              value={selectedBrandTemplateId}
              onChange={(e) => setSelectedBrandTemplateId(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
              disabled={!status?.connected || brandTemplates.length === 0}
            >
              <option value="">Select Canva template</option>
              {filteredBrandTemplates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title || t.name || t.id}
                </option>
              ))}
            </select>
            <div className="mt-1 text-[11px] text-gray-500">
              Brand Templates + autofill requires Canva Enterprise for the
              connected user.
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-900 mb-2">
                RFP
              </label>
              <button
                onClick={loadRfps}
                className="text-xs text-primary-600 hover:text-primary-800"
                disabled={rfpsLoading}
              >
                {rfpsLoading ? 'Loading…' : 'Load'}
              </button>
            </div>
            <input
              value={rfpQuery}
              onChange={(e) => setRfpQuery(e.target.value)}
              placeholder="Filter RFPs…"
              className="mb-2 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
            />
            <select
              value={selectedRfpId}
              onChange={(e) => setSelectedRfpId(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
              disabled={rfps.length === 0}
            >
              <option value="">Select RFP</option>
              {filteredRfps
                .slice()
                .sort((a, b) => {
                  const at = new Date(a?.createdAt || 0).getTime()
                  const bt = new Date(b?.createdAt || 0).getTime()
                  return bt - at
                })
                .slice(0, 200)
                .map((r) => (
                  <option key={r._id} value={r._id}>
                    {r.title} {r.clientName ? `— ${r.clientName}` : ''}
                  </option>
                ))}
            </select>
          </div>
        </div>

        {/* Template setup */}
        <details className="border border-gray-200 rounded-lg bg-gray-50 p-4">
          <summary className="cursor-pointer select-none">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-gray-900">
                  Template setup (mapping + assets)
                </div>
                <div className="mt-1 text-xs text-gray-600">
                  Upload company logo/headshots and map Canva dataset fields.
                </div>
              </div>
              <div className="text-xs text-gray-500">
                {datasetLoading ? 'Loading dataset…' : 'Open'}
              </div>
            </div>
          </summary>

          <div className="mt-4 space-y-6">
            {/* Company assets */}
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="text-sm font-semibold text-gray-900">
                Company logo (Canva asset)
              </div>
              <div className="mt-1 text-xs text-gray-600">
                Logo asset_id:{' '}
                <span className="font-mono">
                  {companyLogoLink?.assetId || '—'}
                </span>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <input
                  value={logoUrl}
                  onChange={(e) => setLogoUrl(e.target.value)}
                  placeholder="Public logo URL (png/jpg)"
                  className="flex-1 border border-gray-300 rounded-md px-3 py-2 bg-white text-gray-900 text-sm"
                />
                <button
                  onClick={uploadLogoToCanva}
                  disabled={
                    !status?.connected || uploadingLogo || !selectedCompanyId
                  }
                  className="px-3 py-2 rounded-md text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  {uploadingLogo ? 'Uploading…' : 'Upload'}
                </button>
              </div>
              <div className="mt-2 text-[11px] text-gray-500">
                The URL must be public (Canva fetches it directly).
              </div>
            </div>

            {/* Headshots */}
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-gray-900">
                    Team headshots (Canva assets)
                  </div>
                  <div className="mt-1 text-xs text-gray-600">
                    Upload each headshot once. Dataset photo fields can be
                    filled from selected team.
                  </div>
                </div>
                <button
                  onClick={refreshHeadshotLinks}
                  className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200 disabled:opacity-50"
                  disabled={!status?.connected}
                >
                  Refresh
                </button>
              </div>

              {(teamMembers || []).length === 0 ? (
                <div className="mt-3 text-sm text-gray-500">
                  Load team members above to manage headshots.
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  {(teamMembers || []).slice(0, 20).map((m: any) => {
                    const memberId = String(m.memberId)
                    const link = headshotLinks[memberId]
                    const busy = !!uploadingHeadshot[memberId]
                    return (
                      <div
                        key={memberId}
                        className="border border-gray-200 rounded-lg p-3 bg-white"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-gray-900 truncate">
                              {m.nameWithCredentials}
                            </div>
                            <div className="text-xs text-gray-600 truncate">
                              {m.position}
                            </div>
                            <div className="mt-1 text-xs text-gray-700">
                              Headshot asset_id:{' '}
                              <span className="font-mono">
                                {link?.assetId || '—'}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="mt-2 flex items-center gap-2">
                          <input
                            value={headshotUrls[memberId] || ''}
                            onChange={(e) =>
                              setHeadshotUrls((prev) => ({
                                ...(prev || {}),
                                [memberId]: e.target.value,
                              }))
                            }
                            placeholder="Public headshot URL (png/jpg)"
                            className="flex-1 border border-gray-300 rounded-md px-3 py-2 bg-white text-gray-900 text-sm"
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
                      </div>
                    )
                  })}
                  {(teamMembers || []).length > 20 && (
                    <div className="text-xs text-gray-500">
                      Showing first 20 team members (use Content Library to
                      edit/add more).
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Dataset mapping */}
            <div className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-gray-900">
                    Dataset field mapping
                  </div>
                  <div className="mt-1 text-xs text-gray-600">
                    Map text fields to RFP/proposal sources; map image fields to
                    Canva asset_id.
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={autoMapCommonFields}
                    className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200"
                    disabled={!selectedBrandTemplateId || datasetLoading}
                  >
                    Auto-map
                  </button>
                  <button
                    onClick={saveMapping}
                    className="px-3 py-2 rounded-md text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
                    disabled={
                      !status?.connected ||
                      !selectedCompanyId ||
                      !selectedBrandTemplateId ||
                      savingMapping
                    }
                  >
                    {savingMapping ? 'Saving…' : 'Save mapping'}
                  </button>
                </div>
              </div>

              {!selectedBrandTemplateId ? (
                <div className="mt-3 text-sm text-gray-500">
                  Select a Canva template above to load dataset fields.
                </div>
              ) : datasetLoading ? (
                <div className="mt-3 text-sm text-gray-500">
                  Loading dataset…
                </div>
              ) : datasetKeys.length === 0 ? (
                <div className="mt-3 text-sm text-gray-500">
                  No dataset fields found (or unable to load).
                </div>
              ) : (
                <>
                  <div className="mt-3 flex items-center gap-2">
                    <input
                      value={datasetFilter}
                      onChange={(e) => setDatasetFilter(e.target.value)}
                      placeholder="Filter fields…"
                      className="w-full sm:w-96 border border-gray-300 rounded-md px-3 py-2 bg-white text-gray-900 text-sm"
                    />
                    <button
                      onClick={() => loadDataset(selectedBrandTemplateId)}
                      className="px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200"
                      disabled={datasetLoading}
                    >
                      Refresh
                    </button>
                  </div>

                  <div className="mt-4 space-y-3">
                    {filteredDatasetKeys.slice(0, 60).map((key) => {
                      const def = (dataset as any)?.[key]
                      const m = (fieldMapping as any)?.[key] || {
                        kind: '',
                        source: '',
                        value: '',
                        assetId: '',
                      }
                      return (
                        <div
                          key={key}
                          className="border border-gray-200 rounded-lg p-3"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-gray-900 break-all">
                                {key}
                              </div>
                              <div className="text-xs text-gray-500">
                                {def?.type || 'unknown'}
                              </div>
                            </div>
                          </div>

                          {def?.type === 'text' && (
                            <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                              <select
                                value={m.kind || ''}
                                onChange={(e) => {
                                  const nextKind = e.target.value
                                  setFieldMapping((prev) => ({
                                    ...(prev || {}),
                                    [key]: {
                                      ...((prev || {})[key] || {}),
                                      kind: nextKind,
                                    },
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
                                      ...(prev || {}),
                                      [key]: {
                                        ...((prev || {})[key] || {}),
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
                                      ...(prev || {}),
                                      [key]: {
                                        ...((prev || {})[key] || {}),
                                        kind: 'literal',
                                        value: next,
                                      },
                                    }))
                                  }}
                                  placeholder="Literal text"
                                  className="border border-gray-300 rounded-md px-2 py-2 bg-white text-gray-900 text-sm md:col-span-2"
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
                                    ...(prev || {}),
                                    [key]: {
                                      ...((prev || {})[key] || {}),
                                      kind: 'asset',
                                      assetId: next,
                                    },
                                  }))
                                }}
                                placeholder="asset_id"
                                className="border border-gray-300 rounded-md px-2 py-2 bg-white text-gray-900 text-sm md:col-span-2"
                              />
                              <div className="md:col-span-3">
                                <button
                                  onClick={() => applyCompanyLogoForField(key)}
                                  className="text-xs text-primary-600 hover:text-primary-800"
                                  disabled={!selectedCompanyId}
                                >
                                  Use company logo
                                </button>
                              </div>
                            </div>
                          )}

                          {def?.type === 'chart' && (
                            <div className="mt-2 text-xs text-gray-500">
                              Chart fields are not handled in the mapping UI
                              yet.
                            </div>
                          )}
                        </div>
                      )
                    })}

                    {datasetKeys.length > 60 && (
                      <div className="text-xs text-gray-500">
                        Showing first 60 fields. Filter to narrow further.
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </details>

        <div className="border-t border-gray-200 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-gray-900">
                Team members
              </div>
              <div className="text-xs text-gray-600 mt-1">
                Selected:{' '}
                <span className="font-semibold">{selectedTeamIds.length}</span>
              </div>
            </div>
            <button
              onClick={loadTeam}
              className="text-xs text-primary-600 hover:text-primary-800"
              disabled={teamLoading}
            >
              {teamLoading ? 'Loading…' : 'Load'}
            </button>
          </div>

          <div className="mt-3">
            <input
              value={teamQuery}
              onChange={(e) => setTeamQuery(e.target.value)}
              placeholder="Filter team…"
              className="w-full sm:w-96 border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
            />
          </div>

          {teamMembers.length === 0 ? (
            <div className="mt-3 text-sm text-gray-500">
              No team members loaded yet. Click “Load”.
            </div>
          ) : (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              {filteredTeam.slice(0, 30).map((m) => {
                const id = String(m.memberId)
                const checked = selectedTeamIds.includes(id)
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => toggleTeam(id)}
                    className={`text-left border rounded-lg p-3 hover:border-primary-300 ${
                      checked
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 bg-white'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-900 truncate">
                          {m.nameWithCredentials}
                        </div>
                        <div className="text-xs text-gray-600 truncate">
                          {m.position}
                        </div>
                      </div>
                      <input type="checkbox" checked={checked} readOnly />
                    </div>
                  </button>
                )
              })}
            </div>
          )}

          {teamMembers.length > 30 && (
            <div className="mt-2 text-xs text-gray-500">
              Showing first 30 team members (filter to narrow).
            </div>
          )}
        </div>

        <div className="border-t border-gray-200 pt-6 flex items-center justify-between">
          <div className="text-xs text-gray-600">
            This will create a proposal record, apply team selections, then
            generate the Canva design.
          </div>
          <button
            onClick={createFromSelections}
            disabled={submitting}
            className="px-4 py-2 rounded-md text-white bg-primary-600 hover:bg-primary-700 text-sm disabled:opacity-50"
          >
            {submitting ? 'Creating…' : 'Create Canva design'}
          </button>
        </div>
      </div>

      {designResult?.design?.urls?.edit_url && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="text-sm font-semibold text-gray-900">Result</div>
          <div className="mt-2 text-sm text-gray-700">
            <div>
              Canva design:{' '}
              <a
                href={designResult.design.urls.edit_url}
                target="_blank"
                rel="noreferrer"
                className="text-primary-600 hover:text-primary-800"
              >
                Open edit link →
              </a>
            </div>
            {designResult?.proposalId && (
              <div className="mt-2">
                Proposal:{' '}
                <Link
                  href={`/proposals/${encodeURIComponent(
                    designResult.proposalId,
                  )}`}
                  className="text-primary-600 hover:text-primary-800"
                >
                  Open proposal →
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}



