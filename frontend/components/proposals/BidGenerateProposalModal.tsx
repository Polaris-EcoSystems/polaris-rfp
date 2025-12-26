import Modal from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import {
  contentApi,
  extractList,
  proposalApi,
  templateApi,
  type Template,
} from '@/lib/api'
import { useEffect, useMemo, useState } from 'react'

type TeamMember = {
  memberId: string
  name?: string
  nameWithCredentials?: string
  position?: string
  isActive?: boolean | null
}

type ProjectReference = {
  _id: string
  organizationName?: string
  timePeriod?: string
  scopeOfWork?: string
  isActive?: boolean | null
  isPublic?: boolean | null
}

type Company = {
  companyId: string
  name?: string
  isActive?: boolean | null
}

export default function BidGenerateProposalModal({
  isOpen,
  onClose,
  rfpId,
  rfpTitle,
  rfpProjectType,
  defaultCompanyId,
  onGenerated,
}: {
  isOpen: boolean
  onClose: () => void
  rfpId: string
  rfpTitle: string
  rfpProjectType?: string
  defaultCompanyId: string | null
  onGenerated: (proposalId: string) => void
}) {
  const toast = useToast()

  const [loading, setLoading] = useState(false)
  const [initializing, setInitializing] = useState(false)
  const [error, setError] = useState('')

  const [templates, setTemplates] = useState<Template[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [team, setTeam] = useState<TeamMember[]>([])
  const [references, setReferences] = useState<ProjectReference[]>([])

  const [templateId, setTemplateId] = useState<string>('')
  const [companyId, setCompanyId] = useState<string>('')
  const [teamQuery, setTeamQuery] = useState('')
  const [refQuery, setRefQuery] = useState('')
  const [teamMemberIds, setTeamMemberIds] = useState<string[]>([])
  const [referenceIds, setReferenceIds] = useState<string[]>([])

  const resetState = () => {
    setLoading(false)
    setInitializing(false)
    setError('')
    setTemplates([])
    setCompanies([])
    setTeam([])
    setReferences([])
    setTemplateId('')
    setCompanyId(defaultCompanyId || '')
    setTeamQuery('')
    setRefQuery('')
    setTeamMemberIds([])
    setReferenceIds([])
  }

  useEffect(() => {
    if (!isOpen) return
    resetState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return

    let cancelled = false
    ;(async () => {
      setInitializing(true)
      setError('')
      try {
        const [tplResp, compResp, teamResp] = await Promise.all([
          templateApi.list(),
          contentApi.getCompanies(),
          contentApi.getTeam(),
        ])

        if (cancelled) return

        const tplList = extractList<Template>(tplResp)
        const compList = extractList<Company>(compResp)
        const teamList = extractList<TeamMember>(teamResp)

        setTemplates(tplList)
        setCompanies(compList)
        setTeam(
          teamList
            .filter((m) => m && m.memberId)
            .filter((m) => m.isActive !== false),
        )

        // Defaults
        const chosenTemplate =
          tplList.find((t) => t.projectType === rfpProjectType) ||
          tplList[0] ||
          null
        setTemplateId(chosenTemplate?.id || 'ai-template')

        const defaultCompany =
          (defaultCompanyId &&
            compList.find((c) => c.companyId === defaultCompanyId)) ||
          compList[0] ||
          null
        setCompanyId(defaultCompany?.companyId || '')
      } catch (e) {
        console.error('Failed to initialize bid proposal modal:', e)
        if (!cancelled) setError('Failed to load templates/companies/team.')
      } finally {
        if (!cancelled) setInitializing(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [isOpen, defaultCompanyId, rfpProjectType])

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    ;(async () => {
      try {
        const resp = await contentApi.getReferences({
          projectType: rfpProjectType || undefined,
          companyId: companyId || undefined,
          count: 200,
        })
        if (cancelled) return
        const refs = extractList<ProjectReference>(resp)
        setReferences(
          refs
            .filter((r) => r && r._id)
            .filter((r) => r.isActive !== false)
            .filter((r) => r.isPublic !== false),
        )
      } catch (e) {
        console.warn('Failed to load references:', e)
        if (!cancelled) setReferences([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isOpen, companyId, rfpProjectType])

  const filteredTeam = useMemo(() => {
    const q = teamQuery.trim().toLowerCase()
    if (!q) return team
    return team.filter((m) => {
      const name = String(m.nameWithCredentials || m.name || '').toLowerCase()
      const pos = String(m.position || '').toLowerCase()
      return name.includes(q) || pos.includes(q)
    })
  }, [team, teamQuery])

  const filteredReferences = useMemo(() => {
    const q = refQuery.trim().toLowerCase()
    if (!q) return references
    return references.filter((r) => {
      const org = String(r.organizationName || '').toLowerCase()
      const scope = String(r.scopeOfWork || '').toLowerCase()
      return org.includes(q) || scope.includes(q)
    })
  }, [references, refQuery])

  const toggleId = (
    id: string,
    current: string[],
    setter: (v: string[]) => void,
  ) => {
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id]
    setter(next)
  }

  const safeTitle = useMemo(() => {
    const base = String(rfpTitle || '').trim() || 'RFP'
    return `Proposal for ${base.slice(0, 60)}`
  }, [rfpTitle])

  const canSubmit = Boolean(rfpId && templateId && safeTitle && !loading)

  const submit = async () => {
    if (!canSubmit) return
    setLoading(true)
    setError('')
    try {
      const resp = await proposalApi.generate({
        rfpId,
        templateId,
        title: safeTitle,
        companyId: companyId || undefined,
        customContent: {
          teamMemberIds,
          referenceIds,
        },
        async: true,
      })
      const proposalId = String(resp?.data?._id || '').trim()
      if (!proposalId) throw new Error('No proposal id returned')
      toast.success('Proposal generation started')
      onGenerated(proposalId)
    } catch (e: any) {
      console.error('Failed to start proposal generation:', e)
      setError(e?.response?.data?.detail || e?.message || 'Failed to start.')
      toast.error('Failed to start proposal generation')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!loading) onClose()
      }}
      title="Generate proposal"
      size="lg"
      footer={
        <>
          <button
            onClick={() => {
              if (!loading) onClose()
            }}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
            disabled={loading}
          >
            Cancel
          </button>
          <button
            onClick={submit}
            className="ml-3 inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
            disabled={!canSubmit || initializing}
          >
            {loading ? 'Starting…' : 'Generate'}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {error ? (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {error}
          </div>
        ) : null}

        {initializing ? (
          <div className="text-sm text-gray-600">Loading options…</div>
        ) : null}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Template
            </label>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
              disabled={loading}
            >
              <option value="ai-template">AI template (auto outline)</option>
              {(templates || []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.sectionCount} sections)
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-900 mb-2">
              Company / branding
            </label>
            <select
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
              disabled={loading}
            >
              <option value="">(none)</option>
              {(companies || []).map((c) => (
                <option key={c.companyId} value={c.companyId}>
                  {c.name || c.companyId}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="border border-gray-200 rounded-lg p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-gray-900">
                Team members
              </div>
              <div className="text-xs text-gray-500">
                Selected: {teamMemberIds.length}
              </div>
            </div>
            <input
              value={teamQuery}
              onChange={(e) => setTeamQuery(e.target.value)}
              placeholder="Search team…"
              className="mt-2 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
              disabled={loading}
            />
            <div className="mt-2 max-h-64 overflow-auto space-y-2">
              {filteredTeam.length === 0 ? (
                <div className="text-sm text-gray-500">
                  No team members found.
                </div>
              ) : (
                filteredTeam.slice(0, 200).map((m) => {
                  const id = String(m.memberId)
                  const selected = teamMemberIds.includes(id)
                  return (
                    <label
                      key={id}
                      className="flex items-start gap-2 text-sm text-gray-900 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() =>
                          toggleId(id, teamMemberIds, setTeamMemberIds)
                        }
                        className="mt-1"
                        disabled={loading}
                      />
                      <span>
                        <span className="font-medium">
                          {m.nameWithCredentials || m.name || id}
                        </span>
                        {m.position ? (
                          <span className="text-gray-500"> — {m.position}</span>
                        ) : null}
                      </span>
                    </label>
                  )
                })
              )}
            </div>
          </div>

          <div className="border border-gray-200 rounded-lg p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-gray-900">
                References
              </div>
              <div className="text-xs text-gray-500">
                Selected: {referenceIds.length}
              </div>
            </div>
            <input
              value={refQuery}
              onChange={(e) => setRefQuery(e.target.value)}
              placeholder="Search references…"
              className="mt-2 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
              disabled={loading}
            />
            <div className="mt-2 max-h-64 overflow-auto space-y-2">
              {filteredReferences.length === 0 ? (
                <div className="text-sm text-gray-500">
                  No references found.
                </div>
              ) : (
                filteredReferences.slice(0, 200).map((r) => {
                  const id = String(r._id)
                  const selected = referenceIds.includes(id)
                  return (
                    <label
                      key={id}
                      className="flex items-start gap-2 text-sm text-gray-900 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() =>
                          toggleId(id, referenceIds, setReferenceIds)
                        }
                        className="mt-1"
                        disabled={loading}
                      />
                      <span>
                        <span className="font-medium">
                          {r.organizationName || id}
                        </span>
                        {r.timePeriod ? (
                          <span className="text-gray-500">
                            {' '}
                            ({r.timePeriod})
                          </span>
                        ) : null}
                        {r.scopeOfWork ? (
                          <div className="text-xs text-gray-600 line-clamp-2">
                            {r.scopeOfWork}
                          </div>
                        ) : null}
                      </span>
                    </label>
                  )
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}

