'use client'

import Card, { CardBody, CardHeader } from '@/components/ui/Card'
import PageHeader from '@/components/ui/PageHeader'
import {
  BudgetVersion,
  ClientPackage,
  ContractDocumentVersion,
  contractingApi,
  ContractingCase,
  contractTemplatesApi,
  ESignEnvelope,
  Proposal,
  proposalApi,
  SupportingDoc,
  tasksApi,
  WorkflowTask,
} from '@/lib/api'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

type BudgetItem = {
  phase?: string
  name?: string
  role?: string
  rate?: number
  hours?: number
  cost?: number
  notes?: string
}

type KeyTerms = {
  commercialTerms?: {
    pricingModel?: string | null
    currency?: string | null
    capNte?: number | null
    paymentSchedule?: string | null
    invoicingCadence?: string | null
    lateFeePolicy?: string | null
  }
  schedule?: {
    startDate?: string | null
    endDate?: string | null
    milestones?: { title: string; dueDate?: string | null; acceptanceCriteria?: string[] }[]
  }
  assumptions?: { text: string; owner?: string | null }[]
  riskMitigations?: {
    risk: string
    severity?: string | null
    mitigation?: string | null
    owner?: string | null
  }[]
  acceptanceCriteria?: string[]
  changeControl?: {
    policyText?: string | null
    requiresWrittenApproval?: boolean
    allowsVerbalApprovals?: boolean
  }
  insuranceRequirements?: { kind: string; required?: boolean; notes?: string | null }[]
  contacts?: { role?: string | null; name?: string | null; email?: string | null; phone?: string | null }[]
  additionalTerms?: Record<string, any>
}

const REQUIRED_SUPPORTING: Array<{ kind: string; label: string }> = [
  { kind: 'insurance', label: 'Insurance certificate' },
  { kind: 'w9', label: 'W-9 (or equivalent)' },
  { kind: 'certifications', label: 'Certifications' },
  { kind: 'other', label: 'Other required doc' },
]

export default function ProposalContractingPage() {
  const params = useParams<{ id?: string }>()
  const proposalId = typeof params?.id === 'string' ? params.id : ''

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')

  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [caseObj, setCaseObj] = useState<ContractingCase | null>(null)

  const [templates, setTemplates] = useState<any[]>([])
  const [templateId, setTemplateId] = useState<string>('')
  const [templateVersionId, setTemplateVersionId] = useState<string>('')
  const [templateVersions, setTemplateVersions] = useState<any[]>([])

  const [contractVersions, setContractVersions] = useState<
    ContractDocumentVersion[]
  >([])
  const [budgetVersions, setBudgetVersions] = useState<BudgetVersion[]>([])
  const [supportingDocs, setSupportingDocs] = useState<SupportingDoc[]>([])
  const [packages, setPackages] = useState<ClientPackage[]>([])
  const [envelopes, setEnvelopes] = useState<ESignEnvelope[]>([])

  const [caseStatus, setCaseStatus] = useState<string>('draft')
  const [keyTerms, setKeyTerms] = useState<KeyTerms>({})
  const [advancedKeyTerms, setAdvancedKeyTerms] = useState(false)
  const [keyTermsJson, setKeyTermsJson] = useState<string>('{}')
  const [keyTermsValidationError, setKeyTermsValidationError] =
    useState<string>('')
  const [keyTermsFieldErrors, setKeyTermsFieldErrors] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<
    'case' | 'contract' | 'budget' | 'docs' | 'package' | 'esign'
  >('case')
  const [tasks, setTasks] = useState<WorkflowTask[]>([])

  const [generatingContract, setGeneratingContract] = useState(false)
  const [generatingBudget, setGeneratingBudget] = useState(false)
  const [uploadingSupport, setUploadingSupport] = useState<string>('') // kind

  const [budgetItems, setBudgetItems] = useState<BudgetItem[]>([])
  const [budgetNotes, setBudgetNotes] = useState<string>('')

  const [packageName, setPackageName] = useState<string>('Client package')
  const [packageSelected, setPackageSelected] = useState<
    Record<string, boolean>
  >({})
  const [portalToken, setPortalToken] = useState<string>('')

  const isWon = useMemo(() => {
    return (
      String(proposal?.status || '')
        .trim()
        .toLowerCase() === 'won'
    )
  }, [proposal?.status])

  const portalLink = useMemo(() => {
    if (!portalToken) return ''
    if (typeof window === 'undefined') return `/client-portal/${portalToken}`
    return `${window.location.origin}/client-portal/${portalToken}`
  }, [portalToken])

  const refreshAll = async (caseId: string) => {
    const [cv, bv, sd, pk, ev] = await Promise.all([
      contractingApi.listContractVersions(caseId).catch(() => null),
      contractingApi.listBudgetVersions(caseId).catch(() => null),
      contractingApi.listSupportingDocs(caseId).catch(() => null),
      contractingApi.listPackages(caseId).catch(() => null),
      contractingApi.listEnvelopes(caseId).catch(() => null),
    ])
    setContractVersions((cv?.data?.data as any) || [])
    setBudgetVersions((bv?.data?.data as any) || [])
    setSupportingDocs((sd?.data?.data as any) || [])
    setPackages((pk?.data?.data as any) || [])
    setEnvelopes((ev?.data?.data as any) || [])
  }

  const refreshTab = async (
    tab:
      | 'case'
      | 'contract'
      | 'budget'
      | 'docs'
      | 'package'
      | 'esign',
    caseId: string,
    rfpId?: string,
  ) => {
    if (!caseId) return
    if (tab === 'case') {
      if (!rfpId) return
      const t = await tasksApi.listForRfp(rfpId).catch(() => null)
      const list = (t?.data?.data as any[]) || []
      const filtered = list.filter((x: any) =>
        String(x?.templateId || '').startsWith('contracting_'),
      )
      setTasks(filtered as any)
      return
    }
    if (tab === 'contract') {
      const cv = await contractingApi.listContractVersions(caseId).catch(() => null)
      setContractVersions((cv?.data?.data as any) || [])
      return
    }
    if (tab === 'budget') {
      const bv = await contractingApi.listBudgetVersions(caseId).catch(() => null)
      setBudgetVersions((bv?.data?.data as any) || [])
      return
    }
    if (tab === 'docs') {
      const sd = await contractingApi.listSupportingDocs(caseId).catch(() => null)
      setSupportingDocs((sd?.data?.data as any) || [])
      return
    }
    if (tab === 'package') {
      const [cv, bv, sd, pk] = await Promise.all([
        contractingApi.listContractVersions(caseId).catch(() => null),
        contractingApi.listBudgetVersions(caseId).catch(() => null),
        contractingApi.listSupportingDocs(caseId).catch(() => null),
        contractingApi.listPackages(caseId).catch(() => null),
      ])
      setContractVersions((cv?.data?.data as any) || [])
      setBudgetVersions((bv?.data?.data as any) || [])
      setSupportingDocs((sd?.data?.data as any) || [])
      setPackages((pk?.data?.data as any) || [])
      return
    }
    if (tab === 'esign') {
      const ev = await contractingApi.listEnvelopes(caseId).catch(() => null)
      setEnvelopes((ev?.data?.data as any) || [])
      return
    }
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        if (!proposalId) throw new Error('Missing proposal id')
        const pResp = await proposalApi.get(proposalId)
        const p = pResp.data as Proposal
        if (cancelled) return
        setProposal(p)

        // Load contracting case if proposal is won (or if it already has an attached case).
        if (String(p?.contractingCaseId || '').trim()) {
          const cResp = await contractingApi.get(String(p.contractingCaseId))
          if (cancelled) return
          const c = cResp.data.case
          setCaseObj(c)
          setCaseStatus(String(c?.status || 'draft'))
          try {
            const kt = ((c as any)?.keyTerms || {}) as KeyTerms
            setKeyTerms(kt)
            setKeyTermsJson(JSON.stringify(kt || {}, null, 2))
          } catch {
            setKeyTerms({})
            setKeyTermsJson('{}')
          }
          setActiveTab('case')
          await refreshTab('case', String(c._id), String(p?.rfpId || c?.rfpId || ''))
        } else if (String(p?.status || '').toLowerCase() === 'won') {
          const cResp = await contractingApi.getByProposal(proposalId)
          if (cancelled) return
          const c = cResp.data.case
          setCaseObj(c)
          setCaseStatus(String(c?.status || 'draft'))
          try {
            const kt = ((c as any)?.keyTerms || {}) as KeyTerms
            setKeyTerms(kt)
            setKeyTermsJson(JSON.stringify(kt || {}, null, 2))
          } catch {
            setKeyTerms({})
            setKeyTermsJson('{}')
          }
          setActiveTab('case')
          await refreshTab('case', String(c._id), String(p?.rfpId || c?.rfpId || ''))
        }

        // Load templates for contract generation UI.
        try {
          const tResp = await contractTemplatesApi.list({ limit: 200 })
          if (!cancelled) setTemplates((tResp?.data?.data as any) || [])
        } catch {
          // ignore
        }
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message || 'Failed to load'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [proposalId])

  useEffect(() => {
    if (!caseObj?._id) return
    void refreshTab(
      activeTab,
      String(caseObj._id),
      String(proposal?.rfpId || caseObj?.rfpId || ''),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, caseObj?._id, proposal?.rfpId])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const tid = String(templateId || '').trim()
      if (!tid) {
        setTemplateVersions([])
        setTemplateVersionId('')
        return
      }
      try {
        const v = await contractTemplatesApi.listVersions(tid)
        if (cancelled) return
        const list = (v?.data?.data as any[]) || []
        setTemplateVersions(list)
        // Default to newest version
        const first = list?.[0]
        const vid =
          String(first?.versionId || first?._id || '').trim() ||
          String(first?._id || '').trim()
        setTemplateVersionId(vid)
      } catch {
        if (!cancelled) {
          setTemplateVersions([])
          setTemplateVersionId('')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [templateId])

  const saveCase = async () => {
    if (!caseObj?._id) return
    try {
      setKeyTermsValidationError('')
      setKeyTermsFieldErrors([])

      let patch: any = { status: caseStatus as any }
      if (advancedKeyTerms) {
        let rawObj: any = {}
        try {
          rawObj = JSON.parse(keyTermsJson || '{}')
        } catch {
          throw new Error('Key terms JSON is invalid')
        }
        patch = { ...patch, keyTermsRawJson: rawObj }
      } else {
        patch = { ...patch, keyTerms: keyTerms || {} }
      }

      const resp = await contractingApi.update(caseObj._id, patch)
      const c = resp.data.case
      setCaseObj(c)
      try {
        const kt = ((c as any)?.keyTerms || {}) as KeyTerms
        setKeyTerms(kt)
        setKeyTermsJson(JSON.stringify(kt || {}, null, 2))
      } catch {
        // ignore
      }
    } catch (e: any) {
      const detail = (e as any)?.response?.data?.detail
      if (detail && typeof detail === 'object' && Array.isArray((detail as any).errors)) {
        setKeyTermsValidationError(String((detail as any).message || 'Invalid key terms'))
        const errs = ((detail as any).errors as any[]).map((x) => {
          const loc = Array.isArray(x?.loc) ? x.loc.join('.') : ''
          const msg = String(x?.msg || 'Invalid')
          return loc ? `${loc}: ${msg}` : msg
        })
        setKeyTermsFieldErrors(errs)
        setError('')
        return
      }
      setError(String(e?.message || 'Failed to save case'))
    }
  }

  const markWon = async () => {
    if (!proposal?._id) return
    try {
      const resp = await proposalApi.update(proposal._id, { status: 'won' })
      setProposal(resp.data as Proposal)
      // backend creates case on transition; refresh
      const cResp = await contractingApi.getByProposal(proposal._id)
      const c = cResp.data.case
      setCaseObj(c)
      setCaseStatus(String(c?.status || 'draft'))
      const kt = ((c as any)?.keyTerms || {}) as KeyTerms
      setKeyTerms(kt)
      setKeyTermsJson(JSON.stringify(kt || {}, null, 2))
      setActiveTab('case')
      await refreshTab(
        'case',
        String(c._id),
        String((resp.data as any)?.rfpId || proposal?.rfpId || c?.rfpId || ''),
      )
    } catch (e: any) {
      setError(String(e?.message || 'Failed to mark won'))
    }
  }

  const generateContract = async () => {
    if (!caseObj?._id) return
    if (!templateId) {
      setError('Select a contract template first')
      return
    }
    setGeneratingContract(true)
    setError('')
    try {
      const idem = `contract:${caseObj._id}:${templateId}:${templateVersionId || ''}`
      const started = await contractingApi.generateContract(caseObj._id, {
        templateId,
        templateVersionId: templateVersionId || null,
        renderInputs: {},
        idempotencyKey: idem,
      })
      const jobId = String((started as any)?.data?.job?.jobId || '')
      if (jobId) {
        const start = Date.now()
        const maxMs = 5 * 60 * 1000
        let delay = 600
        while (Date.now() - start < maxMs) {
          await new Promise((r) => setTimeout(r, delay))
          delay = Math.min(4000, Math.round(delay * 1.4))
          const j = await contractingApi.getJob(jobId).catch(() => null)
          const st = String((j as any)?.data?.job?.status || '')
          if (st === 'completed') break
          if (st === 'failed') {
            const msg = String((j as any)?.data?.job?.error || 'Generation failed')
            throw new Error(msg)
          }
        }
      }
      await refreshAll(caseObj._id)
    } catch (e: any) {
      setError(String(e?.message || 'Contract generation failed'))
    } finally {
      setGeneratingContract(false)
    }
  }

  const downloadContract = async (v: ContractDocumentVersion) => {
    if (!caseObj?._id) return
    try {
      const r = await contractingApi.presignContractVersion(caseObj._id, v._id)
      const url = String(r?.data?.url || '')
      if (url) window.open(url, '_blank', 'noopener,noreferrer')
    } catch (e: any) {
      setError(String(e?.message || 'Download failed'))
    }
  }

  const generateBudget = async () => {
    if (!caseObj?._id) return
    setGeneratingBudget(true)
    setError('')
    try {
      const model = { currency: 'USD', items: budgetItems, notes: budgetNotes }
      const idem = `budget:${caseObj._id}:${JSON.stringify(model)}`
      const started = await contractingApi.generateBudgetXlsx(caseObj._id, {
        budgetModel: model,
        idempotencyKey: idem,
      })
      const jobId = String((started as any)?.data?.job?.jobId || '')
      if (jobId) {
        const start = Date.now()
        const maxMs = 5 * 60 * 1000
        let delay = 600
        while (Date.now() - start < maxMs) {
          await new Promise((r) => setTimeout(r, delay))
          delay = Math.min(4000, Math.round(delay * 1.4))
          const j = await contractingApi.getJob(jobId).catch(() => null)
          const st = String((j as any)?.data?.job?.status || '')
          if (st === 'completed') break
          if (st === 'failed') {
            const msg = String((j as any)?.data?.job?.error || 'Generation failed')
            throw new Error(msg)
          }
        }
      }
      await refreshAll(caseObj._id)
    } catch (e: any) {
      setError(String(e?.message || 'Budget generation failed'))
    } finally {
      setGeneratingBudget(false)
    }
  }

  const downloadBudget = async (v: BudgetVersion) => {
    if (!caseObj?._id) return
    try {
      const r = await contractingApi.presignBudgetVersion(caseObj._id, v._id)
      const url = String(r?.data?.url || '')
      if (url) window.open(url, '_blank', 'noopener,noreferrer')
    } catch (e: any) {
      setError(String(e?.message || 'Download failed'))
    }
  }

  const uploadSupportingDoc = async (kind: string, required: boolean) => {
    if (!caseObj?._id) return
    const input = document.createElement('input')
    input.type = 'file'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      setUploadingSupport(kind)
      setError('')
      try {
        const presign = await contractingApi.presignSupportingDoc(caseObj._id, {
          fileName: file.name,
          contentType: file.type || 'application/octet-stream',
          kind,
          required,
          expiresAt: null,
        })
        const putUrl = String(presign.data.putUrl || '')
        const key = String(presign.data.key || '')
        const docId = String((presign.data as any).docId || '')
        if (!putUrl || !key || !docId)
          throw new Error('Failed to presign upload')
        const putResp = await fetch(putUrl, {
          method: 'PUT',
          headers: { 'Content-Type': file.type || 'application/octet-stream' },
          body: file,
        })
        if (!putResp.ok) throw new Error(`Upload failed (${putResp.status})`)
        await contractingApi.commitSupportingDoc(caseObj._id, {
          docId,
          key,
          kind,
          required,
          fileName: file.name,
          contentType: file.type || 'application/octet-stream',
          expiresAt: null,
        })
        await refreshAll(caseObj._id)
      } catch (e: any) {
        setError(String(e?.message || 'Upload failed'))
      } finally {
        setUploadingSupport('')
      }
    }
    input.click()
  }

  const availableFilesForPackage = useMemo(() => {
    const files: Array<{
      id: string
      kind: string
      label: string
      s3Key: string
      contentType: string
      fileName?: string
    }> = []
    const latestContract = contractVersions?.[0]
    if (latestContract?.docxS3Key) {
      files.push({
        id: 'contract_latest',
        kind: 'contract',
        label: `Contract (latest)`,
        s3Key: latestContract.docxS3Key,
        contentType:
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        fileName: 'contract.docx',
      })
    }
    const latestBudget = budgetVersions?.[0]
    if (latestBudget?.xlsxS3Key) {
      files.push({
        id: 'budget_latest',
        kind: 'budget',
        label: `Budget (latest)`,
        s3Key: latestBudget.xlsxS3Key,
        contentType:
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        fileName: 'budget.xlsx',
      })
    }
    supportingDocs.forEach((d) => {
      files.push({
        id: `support_${d._id}`,
        kind: `supporting:${d.kind}`,
        label: d.fileName || d.kind,
        s3Key: d.s3Key,
        contentType: d.contentType,
        fileName: d.fileName,
      })
    })
    return files
  }, [contractVersions, budgetVersions, supportingDocs])

  const createAndPublishPackage = async () => {
    if (!caseObj?._id) return
    setError('')
    try {
      const selected = availableFilesForPackage.filter(
        (f) => packageSelected[f.id],
      )
      if (selected.length === 0) throw new Error('Select at least one file')
      const created = await contractingApi.createPackage(caseObj._id, {
        name: packageName,
        selectedFiles: selected,
      })
      const pkgId = String(created.data.package._id || '')
      const published = await contractingApi.publishPackage(
        caseObj._id,
        pkgId,
        {
          ttlDays: 7,
        },
      )
      setPortalToken(String(published.data.portalToken || ''))
      await refreshAll(caseObj._id)
    } catch (e: any) {
      setError(String(e?.message || 'Failed to publish package'))
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Contracting"
        subtitle={
          <span>
            Proposal:{' '}
            <Link
              className="text-primary-700 hover:underline"
              href={`/proposals/${proposalId}`}
            >
              {proposal?.title || proposalId}
            </Link>
          </span>
        }
        actions={
          <div className="flex items-center gap-2">
            <Link
              href={`/proposals/${proposalId}`}
              className="px-3 py-2 text-sm rounded-md border border-gray-200 bg-white hover:bg-gray-50"
            >
              Back to proposal
            </Link>
            {!isWon ? (
              <button
                onClick={markWon}
                className="px-3 py-2 text-sm rounded-md text-white bg-green-600 hover:bg-green-700"
              >
                Mark as won
              </button>
            ) : null}
          </div>
        }
      />

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      {!isWon ? (
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">
              Contracting starts when a proposal is marked won
            </div>
          </CardHeader>
          <CardBody>
            <div className="text-sm text-gray-700">
              Mark this proposal as <span className="font-semibold">won</span>{' '}
              to create a contracting case, generate a contract, create a
              budget, collect supporting documents, and publish a client
              package.
            </div>
          </CardBody>
        </Card>
      ) : null}

      {isWon && !caseObj ? (
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-900">
              Initializing contracting…
            </div>
          </CardHeader>
          <CardBody>
            <div className="text-sm text-gray-700">
              If this doesn’t resolve, refresh the page — the backend creates
              the case on the won transition.
            </div>
          </CardBody>
        </Card>
      ) : null}

      {caseObj ? (
        <div className="flex flex-wrap gap-2">
          {[
            { id: 'case', label: 'Case' },
            { id: 'contract', label: 'Contract' },
            { id: 'budget', label: 'Budget' },
            { id: 'docs', label: 'Docs' },
            { id: 'package', label: 'Package' },
            { id: 'esign', label: 'E-sign' },
          ].map((t) => {
            const isActive = activeTab === (t.id as any)
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTab(t.id as any)}
                className={`px-3 py-1.5 text-sm rounded-md border ${
                  isActive
                    ? 'border-primary-300 bg-primary-50 text-primary-900'
                    : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                {t.label}
              </button>
            )
          })}
        </div>
      ) : null}

      {caseObj && (activeTab === 'case' || activeTab === 'contract') ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {activeTab === 'case' ? (
            <>
              <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-gray-900">
                    Contracting case
                  </div>
                  <div className="text-xs text-gray-600">
                    Case ID: {caseObj._id}
                  </div>
                </div>
                <button
                  onClick={saveCase}
                  className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700"
                >
                  Save
                </button>
              </div>
            </CardHeader>
            <CardBody className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Status
                </label>
                <select
                  value={caseStatus}
                  onChange={(e) => setCaseStatus(e.target.value)}
                  className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                >
                  {[
                    'draft',
                    'in_review',
                    'ready',
                    'sent',
                    'signed',
                    'archived',
                  ].map((s) => (
                    <option key={s} value={s}>
                      {s.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-gray-700">
                    Key terms
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setKeyTermsValidationError('')
                      setKeyTermsFieldErrors([])
                      if (!advancedKeyTerms) {
                        try {
                          setKeyTermsJson(JSON.stringify(keyTerms || {}, null, 2))
                          setAdvancedKeyTerms(true)
                        } catch {
                          setKeyTermsJson('{}')
                          setAdvancedKeyTerms(true)
                        }
                        return
                      }
                      // Switching from JSON -> form: parse and sync.
                      try {
                        const obj = JSON.parse(keyTermsJson || '{}')
                        setKeyTerms((obj || {}) as any)
                        setAdvancedKeyTerms(false)
                      } catch {
                        setKeyTermsValidationError(
                          'JSON is invalid — fix it before switching back to the form.',
                        )
                      }
                    }}
                    className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                  >
                    {advancedKeyTerms ? 'Use form' : 'Advanced JSON'}
                  </button>
                </div>

                {keyTermsValidationError ? (
                  <div className="mt-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                    {keyTermsValidationError}
                    {keyTermsFieldErrors.length ? (
                      <ul className="mt-2 list-disc pl-4 space-y-1">
                        {keyTermsFieldErrors.slice(0, 8).map((x, i) => (
                          <li key={`${i}-${x}`}>{x}</li>
                        ))}
                        {keyTermsFieldErrors.length > 8 ? (
                          <li>…and {keyTermsFieldErrors.length - 8} more</li>
                        ) : null}
                      </ul>
                    ) : null}
                  </div>
                ) : null}

                {advancedKeyTerms ? (
                  <div className="mt-2">
                    <textarea
                      value={keyTermsJson}
                      onChange={(e) => setKeyTermsJson(e.target.value)}
                      rows={12}
                      className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-xs"
                    />
                    <div className="mt-2 text-xs text-gray-500">
                      This is an advanced escape hatch. It round-trips through
                      the typed key-terms schema on save.
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 space-y-4">
                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="text-xs font-semibold text-gray-900">
                        Commercial terms
                      </div>
                      <div className="mt-2 grid gap-3 sm:grid-cols-2">
                        <div>
                          <div className="text-xs font-medium text-gray-700">
                            Pricing model
                          </div>
                          <select
                            value={String(
                              (keyTerms?.commercialTerms as any)?.pricingModel ||
                                '',
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                commercialTerms: {
                                  ...((prev || {}).commercialTerms || {}),
                                  pricingModel: e.target.value || null,
                                },
                              }))
                            }
                            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                          >
                            <option value="">Select…</option>
                            {[
                              'fixed_fee',
                              'time_and_materials',
                              'retainer',
                              'milestone',
                              'other',
                            ].map((v) => (
                              <option key={v} value={v}>
                                {v.replaceAll('_', ' ')}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-700">
                            Currency
                          </div>
                          <input
                            value={String(
                              (keyTerms?.commercialTerms as any)?.currency ||
                                'USD',
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                commercialTerms: {
                                  ...((prev || {}).commercialTerms || {}),
                                  currency: e.target.value || null,
                                },
                              }))
                            }
                            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                            placeholder="USD"
                          />
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-700">
                            Cap / NTE (optional)
                          </div>
                          <input
                            type="number"
                            value={String(
                              (keyTerms?.commercialTerms as any)?.capNte ?? '',
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                commercialTerms: {
                                  ...((prev || {}).commercialTerms || {}),
                                  capNte:
                                    e.target.value === ''
                                      ? null
                                      : Number(e.target.value || 0),
                                },
                              }))
                            }
                            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                            placeholder="100000"
                          />
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-700">
                            Invoicing cadence
                          </div>
                          <select
                            value={String(
                              (keyTerms?.commercialTerms as any)
                                ?.invoicingCadence || '',
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                commercialTerms: {
                                  ...((prev || {}).commercialTerms || {}),
                                  invoicingCadence: e.target.value || null,
                                },
                              }))
                            }
                            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                          >
                            <option value="">Select…</option>
                            {[
                              'weekly',
                              'biweekly',
                              'monthly',
                              'milestone',
                              'upon_completion',
                              'other',
                            ].map((v) => (
                              <option key={v} value={v}>
                                {v.replaceAll('_', ' ')}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="sm:col-span-2">
                          <div className="text-xs font-medium text-gray-700">
                            Payment schedule / terms
                          </div>
                          <textarea
                            value={String(
                              (keyTerms?.commercialTerms as any)
                                ?.paymentSchedule || '',
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                commercialTerms: {
                                  ...((prev || {}).commercialTerms || {}),
                                  paymentSchedule: e.target.value || null,
                                },
                              }))
                            }
                            rows={3}
                            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                            placeholder="Net 30; invoices monthly; milestone-based payments…"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="text-xs font-semibold text-gray-900">
                        Schedule
                      </div>
                      <div className="mt-2 grid gap-3 sm:grid-cols-2">
                        <div>
                          <div className="text-xs font-medium text-gray-700">
                            Start date
                          </div>
                          <input
                            type="date"
                            value={String(
                              (keyTerms?.schedule as any)?.startDate || '',
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                schedule: {
                                  ...((prev || {}).schedule || {}),
                                  startDate: e.target.value || null,
                                },
                              }))
                            }
                            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                          />
                        </div>
                        <div>
                          <div className="text-xs font-medium text-gray-700">
                            End date
                          </div>
                          <input
                            type="date"
                            value={String(
                              (keyTerms?.schedule as any)?.endDate || '',
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                schedule: {
                                  ...((prev || {}).schedule || {}),
                                  endDate: e.target.value || null,
                                },
                              }))
                            }
                            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-semibold text-gray-900">
                          Assumptions
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setKeyTerms((prev) => ({
                              ...(prev || {}),
                              assumptions: [
                                ...(((prev || {}).assumptions as any[]) || []),
                                { text: '', owner: '' },
                              ],
                            }))
                          }
                          className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                        >
                          Add
                        </button>
                      </div>
                      <div className="mt-2 space-y-2">
                        {(((keyTerms || {}).assumptions as any[]) || []).length ===
                        0 ? (
                          <div className="text-xs text-gray-500">(none)</div>
                        ) : null}
                        {(((keyTerms || {}).assumptions as any[]) || []).map(
                          (a, idx) => (
                            <div key={idx} className="grid gap-2 sm:grid-cols-3">
                              <input
                                value={String(a?.text || '')}
                                onChange={(e) =>
                                  setKeyTerms((prev) => ({
                                    ...(prev || {}),
                                    assumptions: (
                                      ((prev || {}).assumptions as any[]) || []
                                    ).map((x, i) =>
                                      i === idx
                                        ? { ...(x || {}), text: e.target.value }
                                        : x,
                                    ),
                                  }))
                                }
                                className="sm:col-span-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                placeholder="Assumption…"
                              />
                              <div className="flex gap-2">
                                <input
                                  value={String(a?.owner || '')}
                                  onChange={(e) =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      assumptions: (
                                        ((prev || {}).assumptions as any[]) || []
                                      ).map((x, i) =>
                                        i === idx
                                          ? { ...(x || {}), owner: e.target.value }
                                          : x,
                                      ),
                                    }))
                                  }
                                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                  placeholder="Owner"
                                />
                                <button
                                  type="button"
                                  onClick={() =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      assumptions: (
                                        ((prev || {}).assumptions as any[]) || []
                                      ).filter((_, i) => i !== idx),
                                    }))
                                  }
                                  className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                                  title="Remove"
                                >
                                  ✕
                                </button>
                              </div>
                            </div>
                          ),
                        )}
                      </div>
                    </div>

                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-semibold text-gray-900">
                          Risk mitigations
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setKeyTerms((prev) => ({
                              ...(prev || {}),
                              riskMitigations: [
                                ...(((prev || {}).riskMitigations as any[]) || []),
                                { risk: '', severity: 'medium', mitigation: '', owner: '' },
                              ],
                            }))
                          }
                          className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                        >
                          Add
                        </button>
                      </div>
                      <div className="mt-2 space-y-2">
                        {(((keyTerms || {}).riskMitigations as any[]) || []).length ===
                        0 ? (
                          <div className="text-xs text-gray-500">(none)</div>
                        ) : null}
                        {(((keyTerms || {}).riskMitigations as any[]) || []).map(
                          (r, idx) => (
                            <div key={idx} className="rounded border border-gray-200 p-2">
                              <div className="grid gap-2 sm:grid-cols-3">
                                <input
                                  value={String(r?.risk || '')}
                                  onChange={(e) =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      riskMitigations: (
                                        ((prev || {}).riskMitigations as any[]) || []
                                      ).map((x, i) =>
                                        i === idx
                                          ? { ...(x || {}), risk: e.target.value }
                                          : x,
                                      ),
                                    }))
                                  }
                                  className="sm:col-span-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                  placeholder="Risk…"
                                />
                                <div className="flex gap-2">
                                  <select
                                    value={String(r?.severity || 'medium')}
                                    onChange={(e) =>
                                      setKeyTerms((prev) => ({
                                        ...(prev || {}),
                                        riskMitigations: (
                                          ((prev || {}).riskMitigations as any[]) || []
                                        ).map((x, i) =>
                                          i === idx
                                            ? { ...(x || {}), severity: e.target.value }
                                            : x,
                                        ),
                                      }))
                                    }
                                    className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                  >
                                    {['low', 'medium', 'high', 'critical'].map((v) => (
                                      <option key={v} value={v}>
                                        {v}
                                      </option>
                                    ))}
                                  </select>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setKeyTerms((prev) => ({
                                        ...(prev || {}),
                                        riskMitigations: (
                                          ((prev || {}).riskMitigations as any[]) || []
                                        ).filter((_, i) => i !== idx),
                                      }))
                                    }
                                    className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                                    title="Remove"
                                  >
                                    ✕
                                  </button>
                                </div>
                              </div>
                              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                                <input
                                  value={String(r?.mitigation || '')}
                                  onChange={(e) =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      riskMitigations: (
                                        ((prev || {}).riskMitigations as any[]) || []
                                      ).map((x, i) =>
                                        i === idx
                                          ? { ...(x || {}), mitigation: e.target.value }
                                          : x,
                                      ),
                                    }))
                                  }
                                  className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                  placeholder="Mitigation…"
                                />
                                <input
                                  value={String(r?.owner || '')}
                                  onChange={(e) =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      riskMitigations: (
                                        ((prev || {}).riskMitigations as any[]) || []
                                      ).map((x, i) =>
                                        i === idx
                                          ? { ...(x || {}), owner: e.target.value }
                                          : x,
                                      ),
                                    }))
                                  }
                                  className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                  placeholder="Owner…"
                                />
                              </div>
                            </div>
                          ),
                        )}
                      </div>
                    </div>

                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="text-xs font-semibold text-gray-900">
                        Acceptance criteria (one per line)
                      </div>
                      <textarea
                        value={String(
                          (((keyTerms || {}).acceptanceCriteria as any[]) || []).join(
                            '\n',
                          ),
                        )}
                        onChange={(e) =>
                          setKeyTerms((prev) => ({
                            ...(prev || {}),
                            acceptanceCriteria: String(e.target.value || '')
                              .split('\n')
                              .map((x) => x.trim())
                              .filter(Boolean),
                          }))
                        }
                        rows={4}
                        className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                        placeholder="Must pass UAT…"
                      />
                    </div>

                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="text-xs font-semibold text-gray-900">
                        Change control
                      </div>
                      <div className="mt-2 space-y-2">
                        <textarea
                          value={String(
                            (keyTerms?.changeControl as any)?.policyText || '',
                          )}
                          onChange={(e) =>
                            setKeyTerms((prev) => ({
                              ...(prev || {}),
                              changeControl: {
                                ...((prev || {}).changeControl || {}),
                                policyText: e.target.value || null,
                              },
                            }))
                          }
                          rows={3}
                          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                          placeholder="All scope changes require a written change order…"
                        />
                        <label className="flex items-center gap-2 text-xs text-gray-700">
                          <input
                            type="checkbox"
                            checked={Boolean(
                              (keyTerms?.changeControl as any)
                                ?.requiresWrittenApproval ?? true,
                            )}
                            onChange={(e) =>
                              setKeyTerms((prev) => ({
                                ...(prev || {}),
                                changeControl: {
                                  ...((prev || {}).changeControl || {}),
                                  requiresWrittenApproval: Boolean(e.target.checked),
                                },
                              }))
                            }
                          />
                          Requires written approval
                        </label>
                      </div>
                    </div>

                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-semibold text-gray-900">
                          Insurance requirements
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setKeyTerms((prev) => ({
                              ...(prev || {}),
                              insuranceRequirements: [
                                ...(((prev || {}).insuranceRequirements as any[]) || []),
                                { kind: '', required: true, notes: '' },
                              ],
                            }))
                          }
                          className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                        >
                          Add
                        </button>
                      </div>
                      <div className="mt-2 space-y-2">
                        {(((keyTerms || {}).insuranceRequirements as any[]) || []).length ===
                        0 ? (
                          <div className="text-xs text-gray-500">(none)</div>
                        ) : null}
                        {(((keyTerms || {}).insuranceRequirements as any[]) || []).map(
                          (ir, idx) => (
                            <div key={idx} className="grid gap-2 sm:grid-cols-3">
                              <input
                                value={String(ir?.kind || '')}
                                onChange={(e) =>
                                  setKeyTerms((prev) => ({
                                    ...(prev || {}),
                                    insuranceRequirements: (
                                      ((prev || {}).insuranceRequirements as any[]) || []
                                    ).map((x, i) =>
                                      i === idx
                                        ? { ...(x || {}), kind: e.target.value }
                                        : x,
                                    ),
                                  }))
                                }
                                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                placeholder="Kind (e.g., general_liability)…"
                              />
                              <label className="flex items-center gap-2 text-xs text-gray-700">
                                <input
                                  type="checkbox"
                                  checked={Boolean(ir?.required ?? true)}
                                  onChange={(e) =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      insuranceRequirements: (
                                        ((prev || {}).insuranceRequirements as any[]) || []
                                      ).map((x, i) =>
                                        i === idx
                                          ? {
                                              ...(x || {}),
                                              required: Boolean(e.target.checked),
                                            }
                                          : x,
                                      ),
                                    }))
                                  }
                                />
                                Required
                              </label>
                              <div className="flex gap-2">
                                <input
                                  value={String(ir?.notes || '')}
                                  onChange={(e) =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      insuranceRequirements: (
                                        ((prev || {}).insuranceRequirements as any[]) || []
                                      ).map((x, i) =>
                                        i === idx
                                          ? { ...(x || {}), notes: e.target.value }
                                          : x,
                                      ),
                                    }))
                                  }
                                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                  placeholder="Notes…"
                                />
                                <button
                                  type="button"
                                  onClick={() =>
                                    setKeyTerms((prev) => ({
                                      ...(prev || {}),
                                      insuranceRequirements: (
                                        ((prev || {}).insuranceRequirements as any[]) || []
                                      ).filter((_, i) => i !== idx),
                                    }))
                                  }
                                  className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                                  title="Remove"
                                >
                                  ✕
                                </button>
                              </div>
                            </div>
                          ),
                        )}
                      </div>
                    </div>

                    <div className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-xs font-semibold text-gray-900">
                          Contacts
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setKeyTerms((prev) => ({
                              ...(prev || {}),
                              contacts: [
                                ...(((prev || {}).contacts as any[]) || []),
                                { role: '', name: '', email: '', phone: '' },
                              ],
                            }))
                          }
                          className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                        >
                          Add
                        </button>
                      </div>
                      <div className="mt-2 space-y-2">
                        {(((keyTerms || {}).contacts as any[]) || []).length === 0 ? (
                          <div className="text-xs text-gray-500">(none)</div>
                        ) : null}
                        {(((keyTerms || {}).contacts as any[]) || []).map((c, idx) => (
                          <div key={idx} className="rounded border border-gray-200 p-2">
                            <div className="flex justify-end">
                              <button
                                type="button"
                                onClick={() =>
                                  setKeyTerms((prev) => ({
                                    ...(prev || {}),
                                    contacts: (
                                      ((prev || {}).contacts as any[]) || []
                                    ).filter((_, i) => i !== idx),
                                  }))
                                }
                                className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                              >
                                Remove
                              </button>
                            </div>
                            <div className="mt-2 grid gap-2 sm:grid-cols-2">
                              <input
                                value={String(c?.role || '')}
                                onChange={(e) =>
                                  setKeyTerms((prev) => ({
                                    ...(prev || {}),
                                    contacts: (
                                      ((prev || {}).contacts as any[]) || []
                                    ).map((x, i) =>
                                      i === idx ? { ...(x || {}), role: e.target.value } : x,
                                    ),
                                  }))
                                }
                                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                placeholder="Role (client PM, legal, procurement)…"
                              />
                              <input
                                value={String(c?.name || '')}
                                onChange={(e) =>
                                  setKeyTerms((prev) => ({
                                    ...(prev || {}),
                                    contacts: (
                                      ((prev || {}).contacts as any[]) || []
                                    ).map((x, i) =>
                                      i === idx ? { ...(x || {}), name: e.target.value } : x,
                                    ),
                                  }))
                                }
                                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                placeholder="Name…"
                              />
                              <input
                                value={String(c?.email || '')}
                                onChange={(e) =>
                                  setKeyTerms((prev) => ({
                                    ...(prev || {}),
                                    contacts: (
                                      ((prev || {}).contacts as any[]) || []
                                    ).map((x, i) =>
                                      i === idx ? { ...(x || {}), email: e.target.value } : x,
                                    ),
                                  }))
                                }
                                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                placeholder="Email…"
                              />
                              <input
                                value={String(c?.phone || '')}
                                onChange={(e) =>
                                  setKeyTerms((prev) => ({
                                    ...(prev || {}),
                                    contacts: (
                                      ((prev || {}).contacts as any[]) || []
                                    ).map((x, i) =>
                                      i === idx ? { ...(x || {}), phone: e.target.value } : x,
                                    ),
                                  }))
                                }
                                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                                placeholder="Phone…"
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </CardBody>
              </Card>

              <Card>
                <CardHeader>
                  <div className="text-sm font-semibold text-gray-900">
                    Workflow tasks
                  </div>
                  <div className="text-xs text-gray-600">
                    Track the Contracting checklist for this RFP.
                  </div>
                </CardHeader>
                <CardBody>
                  {tasks.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No contracting tasks found (seeded from the pipeline stage).
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {tasks.slice(0, 30).map((t) => (
                        <div
                          key={t._id}
                          className="flex items-center justify-between rounded border border-gray-200 bg-white px-3 py-2"
                        >
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-gray-900 truncate">
                              {t.title}
                            </div>
                            <div className="text-xs text-gray-600 truncate">
                              {t.description}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-gray-700">
                              {t.status}
                            </span>
                            <button
                              type="button"
                              onClick={async () => {
                                try {
                                  if (String(t.status || '') === 'completed') {
                                    await tasksApi.reopen(t._id)
                                  } else {
                                    await tasksApi.complete(t._id)
                                  }
                                  await refreshTab(
                                    'case',
                                    String(caseObj?._id || ''),
                                    String(proposal?.rfpId || caseObj?.rfpId || ''),
                                  )
                                } catch (e: any) {
                                  setError(
                                    String(
                                      e?.response?.data?.detail ||
                                        e?.message ||
                                        'Failed to update task',
                                    ),
                                  )
                                }
                              }}
                              className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                            >
                              {String(t.status || '') === 'completed'
                                ? 'Reopen'
                                : 'Complete'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardBody>
              </Card>
            </>
          ) : null}

          {activeTab === 'contract' ? (
            <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-900">
                Contract
              </div>
              <div className="text-xs text-gray-600">
                Pick a template and generate a draft contract.
              </div>
            </CardHeader>
            <CardBody className="space-y-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Template
                  </label>
                  <select
                    value={templateId}
                    onChange={(e) => setTemplateId(e.target.value)}
                    className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                  >
                    <option value="">Select…</option>
                    {templates.map((t: any) => (
                      <option
                        key={t._id || t.templateId}
                        value={t._id || t.templateId}
                      >
                        {t.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Version
                  </label>
                  <select
                    value={templateVersionId}
                    onChange={(e) => setTemplateVersionId(e.target.value)}
                    className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                    disabled={!templateId}
                  >
                    {templateVersions.length === 0 ? (
                      <option value="">(none)</option>
                    ) : (
                      templateVersions.map((v: any) => (
                        <option
                          key={v._id || v.versionId}
                          value={v.versionId || v._id}
                        >
                          {v.versionId || v._id}
                        </option>
                      ))
                    )}
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={generateContract}
                  disabled={generatingContract || !templateId}
                  className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                >
                  {generatingContract
                    ? 'Generating…'
                    : 'Generate contract DOCX'}
                </button>
                <Link
                  href="/templates"
                  className="text-sm text-gray-600 hover:underline"
                >
                  Manage templates
                </Link>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-semibold text-gray-900">
                  Generated versions
                </div>
                {contractVersions.length === 0 ? (
                  <div className="text-sm text-gray-600">
                    No contract versions yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {contractVersions.slice(0, 10).map((v) => (
                      <div
                        key={v._id}
                        className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {v.createdAt || v._id}
                          </div>
                          <div className="text-xs text-gray-600 truncate">
                            Template {v.sourceTemplateId || '—'} /{' '}
                            {v.sourceTemplateVersionId || '—'}
                          </div>
                        </div>
                        <button
                          onClick={() => downloadContract(v)}
                          className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                        >
                          Download
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardBody>
            </Card>
          ) : null}
        </div>
      ) : null}

      {caseObj && (activeTab === 'budget' || activeTab === 'docs') ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {activeTab === 'budget' ? (
            <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-900">Budget</div>
              <div className="text-xs text-gray-600">
                Build an internal budget model and generate Excel.
              </div>
            </CardHeader>
            <CardBody className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-gray-900">
                  Line items
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setBudgetItems((prev) => [
                      ...prev,
                      {
                        phase: '',
                        name: '',
                        role: '',
                        rate: 0,
                        hours: 0,
                        cost: 0,
                        notes: '',
                      },
                    ])
                  }
                  className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                >
                  Add item
                </button>
              </div>
              <div className="space-y-2">
                {budgetItems.length === 0 ? (
                  <div className="text-sm text-gray-600">
                    No budget items yet. Add a line item, then generate.
                  </div>
                ) : (
                  budgetItems.map((it, idx) => (
                    <div
                      key={idx}
                      className="grid grid-cols-1 gap-2 rounded border border-gray-200 bg-gray-50 p-3 sm:grid-cols-6"
                    >
                      <input
                        value={it.phase || ''}
                        onChange={(e) => {
                          const v = e.target.value
                          setBudgetItems((prev) =>
                            prev.map((x, i) =>
                              i === idx ? { ...x, phase: v } : x,
                            ),
                          )
                        }}
                        placeholder="Phase"
                        className="sm:col-span-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs"
                      />
                      <input
                        value={it.name || ''}
                        onChange={(e) => {
                          const v = e.target.value
                          setBudgetItems((prev) =>
                            prev.map((x, i) =>
                              i === idx ? { ...x, name: v } : x,
                            ),
                          )
                        }}
                        placeholder="Name"
                        className="sm:col-span-2 rounded border border-gray-300 bg-white px-2 py-1 text-xs"
                      />
                      <input
                        value={it.role || ''}
                        onChange={(e) => {
                          const v = e.target.value
                          setBudgetItems((prev) =>
                            prev.map((x, i) =>
                              i === idx ? { ...x, role: v } : x,
                            ),
                          )
                        }}
                        placeholder="Role"
                        className="sm:col-span-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs"
                      />
                      <input
                        value={String(it.rate ?? '')}
                        onChange={(e) => {
                          const v = Number(e.target.value || 0)
                          setBudgetItems((prev) =>
                            prev.map((x, i) =>
                              i === idx ? { ...x, rate: v } : x,
                            ),
                          )
                        }}
                        placeholder="Rate"
                        inputMode="decimal"
                        className="sm:col-span-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs"
                      />
                      <div className="sm:col-span-1 flex items-center gap-2">
                        <input
                          value={String(it.hours ?? '')}
                          onChange={(e) => {
                            const v = Number(e.target.value || 0)
                            setBudgetItems((prev) =>
                              prev.map((x, i) =>
                                i === idx ? { ...x, hours: v } : x,
                              ),
                            )
                          }}
                          placeholder="Hours"
                          inputMode="decimal"
                          className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            setBudgetItems((prev) =>
                              prev.filter((_, i) => i !== idx),
                            )
                          }
                          className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                          title="Remove"
                        >
                          ×
                        </button>
                      </div>
                      <input
                        value={it.notes || ''}
                        onChange={(e) => {
                          const v = e.target.value
                          setBudgetItems((prev) =>
                            prev.map((x, i) =>
                              i === idx ? { ...x, notes: v } : x,
                            ),
                          )
                        }}
                        placeholder="Notes"
                        className="sm:col-span-6 rounded border border-gray-300 bg-white px-2 py-1 text-xs"
                      />
                    </div>
                  ))
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Assumptions & notes
                </label>
                <textarea
                  value={budgetNotes}
                  onChange={(e) => setBudgetNotes(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={generateBudget}
                  disabled={generatingBudget}
                  className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                >
                  {generatingBudget ? 'Generating…' : 'Generate budget XLSX'}
                </button>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-semibold text-gray-900">
                  Generated versions
                </div>
                {budgetVersions.length === 0 ? (
                  <div className="text-sm text-gray-600">
                    No budget versions yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {budgetVersions.slice(0, 10).map((v) => (
                      <div
                        key={v._id}
                        className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {v.createdAt || v._id}
                          </div>
                        </div>
                        <button
                          onClick={() => downloadBudget(v)}
                          className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                        >
                          Download
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardBody>
            </CardBody>
          </Card>
          ) : null}

          {activeTab === 'docs' ? (
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-900">
                Supporting documents
              </div>
              <div className="text-xs text-gray-600">
                Upload insurance/certifications and any client requirements.
              </div>
            </CardHeader>
            <CardBody className="space-y-4">
              <div className="space-y-2">
                {REQUIRED_SUPPORTING.map((req) => {
                  const existing = supportingDocs.find(
                    (d) => String(d.kind || '') === req.kind,
                  )
                  const status = existing ? 'Uploaded' : 'Missing'
                  const tone = existing
                    ? 'text-green-800 bg-green-50 border-green-200'
                    : 'text-amber-800 bg-amber-50 border-amber-200'
                  return (
                    <div
                      key={req.kind}
                      className="flex items-center justify-between gap-2 rounded border border-gray-200 bg-white px-3 py-2"
                    >
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-900">
                          {req.label}
                        </div>
                        <div
                          className={`mt-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] ${tone}`}
                        >
                          {status}
                        </div>
                      </div>
                      <button
                        onClick={() => uploadSupportingDoc(req.kind, true)}
                        disabled={uploadingSupport === req.kind}
                        className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100 disabled:opacity-50"
                      >
                        {uploadingSupport === req.kind
                          ? 'Uploading…'
                          : 'Upload'}
                      </button>
                    </div>
                  )
                })}
              </div>

              {supportingDocs.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-sm font-semibold text-gray-900">
                    All uploaded
                  </div>
                  <div className="space-y-2">
                    {supportingDocs.slice(0, 20).map((d) => (
                      <div
                        key={d._id}
                        className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {d.fileName}
                          </div>
                          <div className="text-xs text-gray-600">
                            {d.kind} • {d.required ? 'required' : 'optional'}
                          </div>
                        </div>
                        <div className="text-xs text-gray-500">
                          {d.uploadedAt
                            ? String(d.uploadedAt).slice(0, 10)
                            : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardBody>
          </Card>
          ) : null}
        </div>
      ) : null}

      {caseObj && (activeTab === 'package' || activeTab === 'esign') ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {activeTab === 'package' ? (
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-900">
                Client package
              </div>
              <div className="text-xs text-gray-600">
                Select artifacts and publish a client portal link.
              </div>
            </CardHeader>
            <CardBody className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Package name
                </label>
                <input
                  value={packageName}
                  onChange={(e) => setPackageName(e.target.value)}
                  className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-gray-900">
                    Include files
                  </div>
                  {availableFilesForPackage.length ? (
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const next: Record<string, boolean> = {}
                          availableFilesForPackage.forEach((f) => {
                            next[f.id] = true
                          })
                          setPackageSelected(next)
                        }}
                        className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                      >
                        Select all
                      </button>
                      <button
                        type="button"
                        onClick={() => setPackageSelected({})}
                        className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                      >
                        Clear
                      </button>
                    </div>
                  ) : null}
                </div>
                {availableFilesForPackage.length === 0 ? (
                  <div className="text-sm text-gray-600">
                    Generate a contract and budget, and/or upload supporting
                    docs.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {availableFilesForPackage.map((f) => (
                      <label
                        key={f.id}
                        className="flex items-center justify-between gap-2 rounded border border-gray-200 bg-white px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900">
                            {f.label}
                          </div>
                          <div className="text-xs text-gray-600 truncate">
                            {f.kind}
                          </div>
                        </div>
                        <input
                          type="checkbox"
                          checked={Boolean(packageSelected[f.id])}
                          onChange={(e) =>
                            setPackageSelected((prev) => ({
                              ...prev,
                              [f.id]: e.target.checked,
                            }))
                          }
                        />
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <button
                onClick={createAndPublishPackage}
                className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700"
                disabled={availableFilesForPackage.length === 0}
              >
                Create + publish package
              </button>

              {portalLink ? (
                <div className="rounded border border-green-200 bg-green-50 px-3 py-2">
                  <div className="text-sm font-semibold text-green-900">
                    Portal link
                  </div>
                  <div className="mt-1 text-sm">
                    <a
                      className="text-green-800 hover:underline"
                      href={portalLink}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {portalLink}
                    </a>
                  </div>
                  <div className="mt-2">
                    <button
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(portalLink)
                        } catch {
                          // ignore
                        }
                      }}
                      className="px-3 py-1.5 text-xs rounded bg-white border border-green-200 hover:bg-green-100"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              ) : null}

              {packages.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-sm font-semibold text-gray-900">
                    Packages (internal)
                  </div>
                  <div className="space-y-2">
                    {packages.slice(0, 10).map((p) => (
                      <div
                        key={p._id}
                        className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {p.name}
                          </div>
                          <div className="text-xs text-gray-600">
                            {p.publishedAt ? 'published' : 'draft'}
                            {p.revokedAt ? ' • revoked' : ''}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {p.publishedAt && !p.revokedAt ? (
                            <button
                              onClick={async () => {
                                try {
                                  const r = await contractingApi.rotatePackage(
                                    caseObj._id,
                                    p._id,
                                    { ttlDays: 7 },
                                  )
                                  setPortalToken(
                                    String((r as any)?.data?.portalToken || ''),
                                  )
                                  await refreshAll(caseObj._id)
                                } catch (e: any) {
                                  setError(
                                    String(
                                      e?.response?.data?.detail ||
                                        e?.message ||
                                        'Failed to rotate link',
                                    ),
                                  )
                                }
                              }}
                              className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                            >
                              Rotate link
                            </button>
                          ) : null}
                          {p.publishedAt && !p.revokedAt ? (
                            <button
                              onClick={async () => {
                                try {
                                  const idem = `zip:${caseObj._id}:${p._id}:${JSON.stringify(
                                    (p as any)?.selectedFiles || [],
                                  )}`
                                  const started =
                                    await contractingApi.createPackageZipJob(
                                      caseObj._id,
                                      p._id,
                                      { idempotencyKey: idem },
                                    )
                                  const jobId = String(
                                    (started as any)?.data?.job?.jobId || '',
                                  )
                                  if (!jobId)
                                    throw new Error('Failed to start zip job')
                                  const start = Date.now()
                                  const maxMs = 5 * 60 * 1000
                                  let delay = 700
                                  while (Date.now() - start < maxMs) {
                                    await new Promise((r) => setTimeout(r, delay))
                                    delay = Math.min(4000, Math.round(delay * 1.4))
                                    const j = await contractingApi
                                      .getJob(jobId)
                                      .catch(() => null)
                                    const st = String(
                                      (j as any)?.data?.job?.status || '',
                                    )
                                    if (st === 'completed') break
                                    if (st === 'failed') {
                                      const msg = String(
                                        (j as any)?.data?.job?.error ||
                                          'Zip generation failed',
                                      )
                                      throw new Error(msg)
                                    }
                                  }
                                  const urlResp =
                                    await contractingApi.presignZipResult(jobId)
                                  const url = String(urlResp?.data?.url || '')
                                  if (url)
                                    window.open(url, '_blank', 'noopener,noreferrer')
                                } catch (e: any) {
                                  setError(
                                    String(
                                      e?.response?.data?.detail ||
                                        e?.message ||
                                        'Failed to generate zip',
                                    ),
                                  )
                                }
                              }}
                              className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                            >
                              ZIP
                            </button>
                          ) : null}
                          <button
                            onClick={async () => {
                              try {
                                await contractingApi.revokePackage(
                                  caseObj._id,
                                  p._id,
                                )
                                await refreshAll(caseObj._id)
                                setPortalToken('')
                              } catch {
                                // ignore
                              }
                            }}
                            className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                          >
                            Revoke
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardBody>
          </Card>
          ) : null}

          {activeTab === 'esign' ? (
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-900">E-sign</div>
              <div className="text-xs text-gray-600">
                Provider stub: create envelopes and track status.
              </div>
            </CardHeader>
            <CardBody className="space-y-4">
              <button
                onClick={async () => {
                  if (!caseObj?._id) return
                  try {
                    await contractingApi.createEnvelope(caseObj._id, {
                      provider: 'stub',
                      recipients: [],
                      files: [],
                    })
                    await refreshAll(caseObj._id)
                  } catch (e: any) {
                    setError(String(e?.message || 'Failed to create envelope'))
                  }
                }}
                className="px-3 py-2 text-sm rounded-md text-white bg-primary-600 hover:bg-primary-700"
              >
                Create envelope
              </button>

              {envelopes.length === 0 ? (
                <div className="text-sm text-gray-600">No envelopes yet.</div>
              ) : (
                <div className="space-y-2">
                  {envelopes.slice(0, 10).map((e) => (
                    <div
                      key={e._id}
                      className="rounded border border-gray-200 bg-gray-50 px-3 py-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900">
                            {e.provider} • {e.status}
                          </div>
                          <div className="text-xs text-gray-600">
                            {e.createdAt || e._id}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={async () => {
                              if (!caseObj?._id) return
                              try {
                                await contractingApi.sendEnvelope(
                                  caseObj._id,
                                  e._id,
                                )
                                await refreshAll(caseObj._id)
                              } catch (err: any) {
                                setError(
                                  String(
                                    err?.message || 'Failed to send envelope',
                                  ),
                                )
                              }
                            }}
                            className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                          >
                            Send
                          </button>
                          <button
                            onClick={async () => {
                              if (!caseObj?._id) return
                              try {
                                await contractingApi.markEnvelopeSigned(
                                  caseObj._id,
                                  e._id,
                                )
                                await refreshAll(caseObj._id)
                              } catch (err: any) {
                                setError(
                                  String(
                                    err?.message || 'Failed to mark signed',
                                  ),
                                )
                              }
                            }}
                            className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-100"
                          >
                            Mark signed
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
