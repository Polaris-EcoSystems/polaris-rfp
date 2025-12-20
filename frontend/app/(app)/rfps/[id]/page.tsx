'use client'

import AIPreviewModal from '@/components/AIPreviewModal'
import AttachmentUploadModal from '@/components/AttachmentUploadModal'
import ConfirmDeleteModal from '@/components/ConfirmDeleteModal'
import BidGenerateProposalModal from '@/components/proposals/BidGenerateProposalModal'
import { PipelineBreadcrumbs } from '@/components/ui/PipelineBreadcrumbs'
import { useToast } from '@/components/ui/Toast'
import {
  contentApi,
  extractList,
  proposalApi,
  proxyUrl,
  RFP,
  rfpApi,
  Template,
  templateApi,
} from '@/lib/api'
import {
  BuildingOfficeIcon,
  CalendarDaysIcon,
  ClockIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  PaperClipIcon,
  PlusIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'

// Utility function to trim title properly
const trimTitle = (title: string, maxLength: number = 60): string => {
  if (title.length <= maxLength) return title

  // Find the last space before the max length to avoid cutting words
  const trimmed = title.substring(0, maxLength)
  const lastSpaceIndex = trimmed.lastIndexOf(' ')

  if (lastSpaceIndex > maxLength * 0.7) {
    return trimmed.substring(0, lastSpaceIndex) + '...'
  }

  return trimmed + '...'
}

// Utility function to check if a date has passed
const isDatePassed = (dateString?: string): boolean => {
  if (!dateString) return false
  const date = new Date(dateString)
  return !isNaN(date.getTime()) && date < new Date()
}

export default function RFPDetailPage() {
  const router = useRouter()
  const params = useParams<{ id?: string }>()
  const id = typeof params?.id === 'string' ? params.id : ''

  type PageTab = 'details' | 'pdf'
  const [pageTab, setPageTab] = useState<PageTab>('details')
  const [sourcePdfUrl, setSourcePdfUrl] = useState<string | null>(null)
  const [sourcePdfLoading, setSourcePdfLoading] = useState(false)
  const [sourcePdfError, setSourcePdfError] = useState<string | null>(null)

  const [rfp, setRfp] = useState<RFP | null>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const [rfpProposals, setRfpProposals] = useState<any[]>([])
  const [proposalsLoading, setProposalsLoading] = useState(false)
  const [updatingDecisionId, setUpdatingDecisionId] = useState<string | null>(
    null,
  )
  const [companies, setCompanies] = useState<any[]>([])
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    null,
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [generatingTemplate, setGeneratingTemplate] = useState<string | null>(
    null,
  )
  const [showAIPreviewModal, setShowAIPreviewModal] = useState(false)
  const [generatingAI, setGeneratingAI] = useState(false)
  const [showAttachmentModal, setShowAttachmentModal] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [attachmentToDelete, setAttachmentToDelete] = useState<{
    id: string
    name: string
  } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const toast = useToast()
  const [buyerSelected, setBuyerSelected] = useState<Record<string, boolean>>(
    {},
  )
  const [buyerRemoving, setBuyerRemoving] = useState(false)
  const buyerHeaderCheckboxRef = useRef<HTMLInputElement | null>(null)
  const [reanalyzingAi, setReanalyzingAi] = useState(false)
  const [aiStreaming, setAiStreaming] = useState(false)
  const [aiSummary, setAiSummary] = useState<string>('')
  const [aiSummaryStreaming, setAiSummaryStreaming] = useState(false)
  type SectionAiSummary = { text: string; topic: string; updatedAt?: string }
  const [sectionAiSummaries, setSectionAiSummaries] = useState<
    Partial<Record<string, SectionAiSummary>>
  >({})
  const [sectionAiLoading, setSectionAiLoading] = useState<
    Partial<Record<string, boolean>>
  >({})
  const [sectionAiError, setSectionAiError] = useState<
    Partial<Record<string, string>>
  >({})
  type AiBucket = 'meta' | 'dates' | 'lists'
  type AiBucketStatus = 'idle' | 'running' | 'done' | 'error'
  const [aiRefreshStatus, setAiRefreshStatus] = useState<
    Record<AiBucket, AiBucketStatus>
  >({ meta: 'idle', dates: 'idle', lists: 'idle' })
  const aiRefreshEsRef = useRef<EventSource | null>(null)
  const aiSummaryEsRef = useRef<EventSource | null>(null)

  useEffect(() => {
    return () => {
      try {
        aiRefreshEsRef.current?.close()
      } catch {}
      try {
        aiSummaryEsRef.current?.close()
      } catch {}
      aiRefreshEsRef.current = null
      aiSummaryEsRef.current = null
    }
  }, [])

  useEffect(() => {
    // Seed section summaries from persisted RFP record (best-effort).
    if (!rfp?._id) return
    try {
      const raw = (rfp as any)?.aiSectionSummaries
      if (!raw || typeof raw !== 'object') return
      const next: Record<string, SectionAiSummary> = {}
      Object.entries(raw as Record<string, any>).forEach(([k, v]) => {
        if (!k) return
        if (!v || typeof v !== 'object') return
        const text = String((v as any).text || '').trim()
        if (!text) return
        next[k] = {
          text,
          topic: String((v as any).topic || k),
          updatedAt: String((v as any).updatedAt || '').trim() || undefined,
        }
      })
      if (Object.keys(next).length === 0) return
      setSectionAiSummaries((prev) => ({ ...next, ...prev }))
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rfp?._id])

  const isBucketRunning = (b: AiBucket) =>
    aiStreaming && aiRefreshStatus[b] === 'running'

  useEffect(() => {
    if (pageTab !== 'pdf') return
    if (!rfp?._id) return

    let cancelled = false

    const fallbackFromAttachments = (): string | null => {
      const atts = Array.isArray((rfp as any)?.attachments)
        ? ((rfp as any).attachments as any[])
        : []
      const pdf = atts.find((a) => {
        const mt = String(a?.mimeType || '').toLowerCase()
        const ft = String(a?.fileType || '').toLowerCase()
        const name = String(a?.originalName || a?.fileName || '').toLowerCase()
        return mt === 'application/pdf' || ft === 'pdf' || name.endsWith('.pdf')
      })
      const attId = String(pdf?._id || pdf?.id || '').trim()
      if (!attId) return null
      return proxyUrl(
        `/api/rfp/${encodeURIComponent(
          rfp._id,
        )}/attachments/${encodeURIComponent(attId)}`,
      )
    }

    ;(async () => {
      setSourcePdfLoading(true)
      setSourcePdfError(null)

      try {
        const resp = await rfpApi.presignSourcePdf(rfp._id)
        const url = String(resp?.data?.url || '').trim()
        if (!url) throw new Error('No URL returned')
        if (cancelled) return
        setSourcePdfUrl(url)
      } catch (e) {
        console.warn('Failed to presign source PDF:', e)
        const fallback = fallbackFromAttachments()
        if (cancelled) return
        if (fallback) {
          setSourcePdfUrl(fallback)
          setSourcePdfError(null)
        } else {
          setSourcePdfUrl(null)
          setSourcePdfError('No original PDF is available for this RFP.')
        }
      } finally {
        if (!cancelled) setSourcePdfLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [pageTab, rfp])

  // --- Bid / no-bid review state ---
  type BidDecision = '' | 'bid' | 'no_bid' | 'maybe'
  const [bidDecision, setBidDecision] = useState<BidDecision>('')
  const [bidNotes, setBidNotes] = useState<string>('')
  const [bidReasons, setBidReasons] = useState<string[]>([])
  const [bidBlockersList, setBidBlockersList] = useState<
    { id: string; text: string; status: 'open' | 'resolved' | 'waived' }[]
  >([])
  const [newBlockerText, setNewBlockerText] = useState<string>('')
  const [bidSaving, setBidSaving] = useState(false)
  const [showBidGenerateModal, setShowBidGenerateModal] = useState(false)
  const lastSavedBidDecisionRef = useRef<BidDecision>('')

  type ReqStatus = 'unknown' | 'ok' | 'risk' | 'gap'
  type ReqAssessment = {
    text: string
    status: ReqStatus
    notes: string
    mappedSections: string[]
  }
  const [reqAssessments, setReqAssessments] = useState<
    Record<string, ReqAssessment>
  >({})
  const [reqSaving, setReqSaving] = useState(false)
  const [seedTemplateId, setSeedTemplateId] = useState<string>('')
  const [seedingReqs, setSeedingReqs] = useState(false)

  const decisionLabel = (d: BidDecision): string => {
    if (d === 'bid') return 'Bid'
    if (d === 'no_bid') return 'No-bid'
    if (d === 'maybe') return 'Maybe'
    return 'Unreviewed'
  }

  const decisionPill = (d: BidDecision): string => {
    if (d === 'bid') return 'bg-green-100 text-green-800'
    if (d === 'no_bid') return 'bg-red-100 text-red-800'
    if (d === 'maybe') return 'bg-amber-100 text-amber-900'
    return 'bg-gray-100 text-gray-800'
  }

  type ChecklistItem = {
    id: string
    label: string
    done: boolean
    hint?: string
  }

  const checklist = useMemo<ChecklistItem[]>(() => {
    if (!rfp) return []

    const decision = String((rfp as any)?.review?.decision || '')
      .trim()
      .toLowerCase()
    const hasDecision =
      decision === 'bid' || decision === 'no_bid' || decision === 'maybe'

    const storedReqs = Array.isArray((rfp as any)?.review?.requirements)
      ? (rfp as any).review.requirements
      : []
    const hasAnyReqAssessment = storedReqs.length > 0
    const mappedComplete =
      storedReqs.length > 0 &&
      storedReqs.every(
        (r: any) =>
          String(r?.text || '').trim() &&
          Array.isArray(r?.mappedSections) &&
          r.mappedSections.filter((x: any) => String(x || '').trim()).length >
            0,
      )

    const hasProposal = Array.isArray(rfpProposals) && rfpProposals.length > 0

    return [
      {
        id: 'decision',
        label: 'Bid/no-bid decision recorded',
        done: hasDecision,
        hint: 'Use the Bid / No-bid review panel.',
      },
      {
        id: 'requirements',
        label: 'Requirements assessed',
        done: hasAnyReqAssessment,
        hint: 'Set OK/Risk/Gap and add notes.',
      },
      {
        id: 'mapping',
        label: 'Requirements mapped to proposal sections',
        done: mappedComplete,
        hint: 'Fill “Proposal sections” for each requirement (Auto-seed helps).',
      },
      {
        id: 'proposal',
        label: 'Proposal created',
        done: hasProposal,
        hint: 'Generate from a template once this is a bid.',
      },
    ]
  }, [rfp, rfpProposals])

  const checklistDone = useMemo(
    () => checklist.filter((x) => x.done).length,
    [checklist],
  )

  useEffect(() => {
    if (!rfp) return
    const r = (rfp as any)?.review || {}
    const d = String(r?.decision || '')
      .trim()
      .toLowerCase() as BidDecision
    setBidDecision(d === 'bid' || d === 'no_bid' || d === 'maybe' ? d : '')
    lastSavedBidDecisionRef.current =
      d === 'bid' || d === 'no_bid' || d === 'maybe' ? d : ''
    setBidNotes(String(r?.notes || ''))
    setBidReasons(Array.isArray(r?.reasons) ? r.reasons.slice(0, 50) : [])
    const bl = Array.isArray(r?.blockers) ? r.blockers : []
    const cleaned = bl
      .filter((x: any) => x && typeof x === 'object')
      .map((x: any, idx: number) => {
        const id = String(x.id || `b${idx}`).slice(0, 80)
        const text = String(x.text || '').trim()
        const statusRaw = String(x.status || 'open').toLowerCase()
        const status =
          statusRaw === 'resolved' || statusRaw === 'waived'
            ? statusRaw
            : 'open'
        return { id, text, status }
      })
      .filter((x: any) => x.text)
      .slice(0, 100)
    setBidBlockersList(cleaned)

    // Initialize requirement assessments from stored review, merged with current keyRequirements.
    const storedReqs = Array.isArray(r?.requirements) ? r.requirements : []
    const storedByText: Record<string, any> = {}
    storedReqs.forEach((x: any) => {
      const t = String(x?.text || '').trim()
      if (!t) return
      storedByText[t] = x
    })
    const baseReqs = Array.isArray(rfp.keyRequirements)
      ? rfp.keyRequirements
      : []
    const next: Record<string, ReqAssessment> = {}
    baseReqs.forEach((raw) => {
      const text = String(raw || '').trim()
      if (!text) return
      const s = storedByText[text] || {}
      const st = String(s?.status || 'unknown').toLowerCase() as ReqStatus
      const status: ReqStatus =
        st === 'ok' || st === 'risk' || st === 'gap' ? st : 'unknown'
      const notes = String(s?.notes || '')
      const mappedSections = Array.isArray(s?.mappedSections)
        ? s.mappedSections
            .map((m: any) => String(m || '').trim())
            .filter(Boolean)
        : []
      next[text] = { text, status, notes, mappedSections }
    })
    setReqAssessments(next)
  }, [rfp])

  const bidDirty = useMemo(() => {
    if (!rfp) return false
    const r = (rfp as any)?.review || {}
    const d0 = String(r?.decision || '')
      .trim()
      .toLowerCase()
    const n0 = String(r?.notes || '')
    const rs0 = Array.isArray(r?.reasons) ? r.reasons : []
    const rs0Norm = rs0
      .map((x: any) => String(x || ''))
      .filter(Boolean)
      .sort()
    const rsNorm = bidReasons
      .map((x) => String(x || ''))
      .filter(Boolean)
      .sort()
    const bl0 = Array.isArray(r?.blockers) ? r.blockers : []
    const bl0Norm = bl0
      .filter((x: any) => x && typeof x === 'object')
      .map(
        (x: any) =>
          `${String(x.text || '').trim()}::${String(x.status || 'open')}`,
      )
      .filter(Boolean)
      .sort()
    const blNorm = bidBlockersList
      .map(
        (x) => `${String(x.text || '').trim()}::${String(x.status || 'open')}`,
      )
      .filter(Boolean)
      .sort()
    return (
      d0 !== bidDecision ||
      n0 !== bidNotes ||
      JSON.stringify(rs0Norm) !== JSON.stringify(rsNorm) ||
      JSON.stringify(bl0Norm) !== JSON.stringify(blNorm)
    )
  }, [rfp, bidDecision, bidNotes, bidReasons, bidBlockersList])

  const bidBlockers = useMemo(() => {
    const out: string[] = []
    if (!rfp) return out
    if (rfp.isDisqualified)
      out.push('One or more critical deadlines have passed.')
    if (!rfp.submissionDeadline) out.push('Submission deadline is missing.')
    if (!rfp.budgetRange) out.push('Budget range is not specified.')
    if (Array.isArray(rfp.dateWarnings) && rfp.dateWarnings.length > 0) {
      rfp.dateWarnings.slice(0, 4).forEach((w) => out.push(String(w)))
    }
    return out.slice(0, 8)
  }, [rfp])

  const toggleBidReason = (reason: string) => {
    const r = String(reason || '').trim()
    if (!r) return
    setBidReasons((prev) =>
      prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r],
    )
  }

  const initBlockersFromDetected = () => {
    const detected = bidBlockers
    if (!detected || detected.length === 0) return
    const ts = Date.now()
    setBidBlockersList(
      detected.slice(0, 20).map((t, i) => ({
        id: `b_${ts}_${i}`,
        text: String(t),
        status: 'open' as const,
      })),
    )
  }

  const addBlocker = () => {
    const t = String(newBlockerText || '').trim()
    if (!t) return
    setBidBlockersList((prev) => [
      ...prev,
      { id: `b_${Date.now()}`, text: t, status: 'open' },
    ])
    setNewBlockerText('')
  }

  const setReq = (text: string, patch: Partial<ReqAssessment>) => {
    const t = String(text || '').trim()
    if (!t) return
    setReqAssessments((prev) => {
      const cur =
        prev[t] ||
        ({
          text: t,
          status: 'unknown',
          notes: '',
          mappedSections: [],
        } as ReqAssessment)
      return { ...prev, [t]: { ...cur, ...patch, text: t } }
    })
  }

  const saveRequirements = async () => {
    if (!rfp) return
    setReqSaving(true)
    try {
      const requirements = Object.values(reqAssessments).map((r) => ({
        text: r.text,
        status: r.status,
        notes: r.notes,
        mappedSections: r.mappedSections,
      }))
      const resp = await rfpApi.updateReview(rfp._id, { requirements })
      setRfp(resp.data)
      toast.success('Saved requirements')
    } catch (e: any) {
      console.error('Failed to save requirements:', e)
      toast.error('Failed to save requirements')
    } finally {
      setReqSaving(false)
    }
  }

  const copyComplianceMatrix = async () => {
    const rows = Object.values(reqAssessments)
    if (rows.length === 0) {
      toast.error('No requirements to export')
      return
    }
    const statusLabel = (s: ReqStatus) => {
      if (s === 'ok') return 'OK'
      if (s === 'risk') return 'RISK'
      if (s === 'gap') return 'GAP'
      return 'UNKNOWN'
    }
    const escapeCell = (v: string) =>
      String(v || '')
        .replace(/\|/g, '\\|')
        .trim()
    const md = [
      `## Compliance matrix`,
      ``,
      `| Requirement | Assessment | Notes | Proposal sections |`,
      `|---|---|---|---|`,
      ...rows.map((r) => {
        const sections = (r.mappedSections || []).join(', ')
        return `| ${escapeCell(r.text)} | ${statusLabel(
          r.status,
        )} | ${escapeCell(r.notes)} | ${escapeCell(sections)} |`
      }),
      ``,
    ].join('\n')

    try {
      await navigator.clipboard.writeText(md)
      toast.success('Copied compliance matrix')
    } catch (e) {
      console.error('clipboard copy failed', e)
      toast.error('Copy failed')
    }
  }

  const downloadComplianceCsv = () => {
    const rows = Object.values(reqAssessments)
    if (rows.length === 0) {
      toast.error('No requirements to export')
      return
    }

    const statusLabel = (s: ReqStatus) => {
      if (s === 'ok') return 'OK'
      if (s === 'risk') return 'RISK'
      if (s === 'gap') return 'GAP'
      return 'UNKNOWN'
    }

    const csvEscape = (v: string) => {
      const s = String(v ?? '')
      // Double quotes escape for CSV
      const out = s.replace(/"/g, '""')
      return `"${out}"`
    }

    const lines = [
      ['Requirement', 'Assessment', 'Notes', 'Proposal sections']
        .map(csvEscape)
        .join(','),
      ...rows.map((r) =>
        [
          csvEscape(r.text),
          csvEscape(statusLabel(r.status)),
          csvEscape(r.notes || ''),
          csvEscape((r.mappedSections || []).join(', ')),
        ].join(','),
      ),
    ]
    const csv = lines.join('\n')

    try {
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const safeId = String(rfp?._id || 'rfp').replace(/[^a-zA-Z0-9_-]/g, '')
      a.download = `compliance-matrix-${safeId}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('csv download failed', e)
      toast.error('Download failed')
    }
  }

  const autoseedMappedSections = async () => {
    if (!rfp) return
    setSeedingReqs(true)
    try {
      if (!templates || templates.length === 0) {
        await ensureTemplatesLoaded()
      }

      const chosenId =
        seedTemplateId ||
        templates.find((t) => t.projectType === rfp.projectType)?.id ||
        templates[0]?.id ||
        ''
      if (!chosenId) {
        toast.error('No templates available to seed from')
        return
      }
      setSeedTemplateId(chosenId)

      const tResp = await templateApi.get(chosenId)
      const tpl = tResp?.data ?? tResp
      const secsIn = (tpl as any)?.sections
      const sectionTitles: string[] = Array.isArray(secsIn)
        ? secsIn
            .map((s: any) =>
              String(
                s?.title || s?.name || s?.sectionTitle || s?.id || '',
              ).trim(),
            )
            .filter(Boolean)
            .slice(0, 80)
        : []

      if (sectionTitles.length === 0) {
        toast.error('Template has no sections to seed from')
        return
      }

      // Simple keyword overlap matcher to pick 1-2 likely sections.
      const tokens = (s: string) =>
        String(s || '')
          .toLowerCase()
          .replace(/[^a-z0-9\s]/g, ' ')
          .split(/\s+/)
          .map((x) => x.trim())
          .filter((x) => x.length >= 4)

      const seedFallback = (() => {
        const want = ['Approach', 'Technical Approach', 'Scope', 'Work Plan']
        for (const w of want) {
          const hit = sectionTitles.find(
            (t) => t.toLowerCase() === w.toLowerCase(),
          )
          if (hit) return hit
        }
        return sectionTitles[0]
      })()

      setReqAssessments((prev) => {
        const next = { ...prev }
        Object.values(next).forEach((r) => {
          if (!r || !r.text) return
          // Only seed when empty to avoid clobbering human work.
          if (Array.isArray(r.mappedSections) && r.mappedSections.length > 0) {
            return
          }
          const reqToks = new Set(tokens(r.text))
          const scored = sectionTitles
            .map((title) => {
              const sToks = tokens(title)
              let score = 0
              sToks.forEach((t) => {
                if (reqToks.has(t)) score += 1
              })
              // Small bonus for obvious keywords
              const lowTitle = title.toLowerCase()
              const lowReq = r.text.toLowerCase()
              if (lowReq.includes('timeline') && lowTitle.includes('schedule'))
                score += 1
              if (lowReq.includes('schedule') && lowTitle.includes('schedule'))
                score += 1
              if (lowReq.includes('budget') && lowTitle.includes('cost'))
                score += 1
              if (lowReq.includes('pricing') && lowTitle.includes('cost'))
                score += 1
              return { title, score }
            })
            .sort((a, b) => b.score - a.score)
          const picked = scored
            .filter((x) => x.score > 0)
            .slice(0, 2)
            .map((x) => x.title)
          next[r.text] = {
            ...r,
            mappedSections: picked.length > 0 ? picked : [seedFallback],
          }
        })
        return next
      })

      toast.success('Seeded mapped sections')
    } catch (e) {
      console.error('autoseed failed', e)
      toast.error('Auto-seed failed')
    } finally {
      setSeedingReqs(false)
    }
  }

  const saveBidReview = async () => {
    if (!rfp) return
    const prevSavedDecision = lastSavedBidDecisionRef.current
    setBidSaving(true)
    try {
      const resp = await rfpApi.updateReview(rfp._id, {
        decision: bidDecision,
        notes: bidNotes,
        reasons: bidReasons,
        blockers: bidBlockersList,
      })
      setRfp(resp.data)
      toast.success('Saved review')

      // If the user just committed a Bid decision, automatically prompt to generate a proposal.
      if (prevSavedDecision !== 'bid' && bidDecision === 'bid') {
        setShowBidGenerateModal(true)
      }
    } catch (e: any) {
      console.error('Failed to save review:', e)
      toast.error('Failed to save review')
    } finally {
      setBidSaving(false)
    }
  }

  // --- Single-page layout: collapsible sections + TOC (includes non-collapsible anchors) ---
  type CollapsibleSectionId =
    | 'suitability'
    | 'overview'
    | 'requirements'
    | 'deliverables'
    | 'attachments'
    | 'buyers'
    | 'generate'
    | 'proposals'
    | 'raw'

  type TocSectionId = 'bid-review' | CollapsibleSectionId

  const collapsibleSectionDefs: {
    id: CollapsibleSectionId
    label: string
    defaultOpen: boolean
  }[] = useMemo(
    () => [
      { id: 'suitability', label: 'Suitability', defaultOpen: true },
      { id: 'overview', label: 'Overview', defaultOpen: true },
      { id: 'requirements', label: 'Key requirements', defaultOpen: true },
      {
        id: 'deliverables',
        label: 'Deliverables & criteria',
        defaultOpen: false,
      },
      { id: 'attachments', label: 'Attachments', defaultOpen: false },
      { id: 'buyers', label: 'Buyers', defaultOpen: false },
      { id: 'generate', label: 'Generate proposal', defaultOpen: false },
      { id: 'proposals', label: 'Proposals', defaultOpen: false },
      { id: 'raw', label: 'Raw / extracted text', defaultOpen: false },
    ],
    [],
  )

  const tocSectionDefs: { id: TocSectionId; label: string }[] = useMemo(() => {
    return [
      { id: 'bid-review', label: 'Bid / No-bid review' },
      ...collapsibleSectionDefs.map((s) => ({ id: s.id, label: s.label })),
    ]
  }, [collapsibleSectionDefs])

  const [openSections, setOpenSections] = useState<
    Record<CollapsibleSectionId, boolean>
  >(
    () =>
      Object.fromEntries(
        collapsibleSectionDefs.map((s) => [s.id, s.defaultOpen]),
      ) as Record<CollapsibleSectionId, boolean>,
  )
  const [activeSection, setActiveSection] = useState<TocSectionId>('overview')

  const [templatesLoading, setTemplatesLoading] = useState(false)
  const [companiesLoading, setCompaniesLoading] = useState(false)
  const [supportingError, setSupportingError] = useState<string>('')

  const ensureTemplatesLoaded = async () => {
    if (templatesLoading) return
    if (templates.length > 0) return
    setTemplatesLoading(true)
    try {
      const templatesResponse = await templateApi.list()
      setTemplates(extractList<Template>(templatesResponse))
    } catch (e) {
      console.error('Error loading templates:', e)
      setSupportingError('Failed to load templates')
      setTemplates([])
    } finally {
      setTemplatesLoading(false)
    }
  }

  const ensureCompaniesLoaded = async () => {
    if (companiesLoading) return
    if (companies.length > 0) return
    setCompaniesLoading(true)
    try {
      const companiesResponse = await contentApi.getCompanies()
      const companiesData = extractList<any>(companiesResponse)
      setCompanies(companiesData)
      if (!selectedCompanyId) {
        const polaris = companiesData.find((c) =>
          String(c?.name || '')
            .toLowerCase()
            .includes('polaris'),
        )
        const defaultCompany = polaris || companiesData[0]
        setSelectedCompanyId(defaultCompany?.companyId || null)
      }
    } catch (e) {
      console.error('Error loading companies:', e)
      setSupportingError('Failed to load companies')
      setCompanies([])
      if (!selectedCompanyId) setSelectedCompanyId(null)
    } finally {
      setCompaniesLoading(false)
    }
  }

  const ensureProposalsLoaded = async (rfpId: string) => {
    if (!rfpId) return
    if (proposalsLoading) return
    if (rfpProposals.length > 0) return
    setProposalsLoading(true)
    try {
      const p = await rfpApi.getProposals(rfpId)
      setRfpProposals(extractList<any>(p))
    } catch (e) {
      console.error('Error loading proposals:', e)
      setRfpProposals([])
    } finally {
      setProposalsLoading(false)
    }
  }

  const sectionTopic = (sid: CollapsibleSectionId): string => {
    switch (sid) {
      case 'suitability':
        return 'Suitability / fit / risks / red flags'
      case 'overview':
        return 'High-level overview: scope, budget, key dates, project type'
      case 'requirements':
        return 'Key requirements and compliance obligations'
      case 'deliverables':
        return 'Deliverables, evaluation criteria, critical information, and questions'
      case 'attachments':
        return 'Submission instructions, required forms, and attachments'
      case 'buyers':
        return 'Stakeholders, buyer roles, contacts, and org context'
      case 'generate':
        return 'Suggested proposal outline and themes implied by the RFP'
      case 'proposals':
        return 'Proposal response format and required proposal sections'
      case 'raw':
        return 'What the extracted text contains (brief)'
      default:
        return String(sid)
    }
  }

  const ensureSectionAiSummaryLoaded = async (
    sid: CollapsibleSectionId,
    force: boolean,
  ) => {
    if (!rfp?._id) return
    const hasRaw = Boolean(String((rfp as any)?.rawText || '').trim())
    if (!hasRaw) return

    const key = String(sid)
    if (!force && String(sectionAiSummaries?.[key]?.text || '').trim()) return
    if (sectionAiLoading?.[key]) return

    setSectionAiLoading((prev) => ({ ...prev, [key]: true }))
    setSectionAiError((prev) => ({ ...prev, [key]: '' }))
    try {
      const resp = await rfpApi.aiSectionSummary(rfp._id, {
        sectionId: key,
        topic: sectionTopic(sid),
        force,
      })
      const summary = String((resp as any)?.data?.summary || '').trim()
      const topic = String(
        (resp as any)?.data?.topic || sectionTopic(sid),
      ).trim()
      const updatedAt = String((resp as any)?.data?.updatedAt || '').trim()
      if (!summary) throw new Error('Empty AI summary')
      setSectionAiSummaries((prev) => ({
        ...prev,
        [key]: { text: summary, topic, updatedAt: updatedAt || undefined },
      }))
    } catch (e: any) {
      const msg =
        String(
          e?.response?.data?.detail ||
            e?.message ||
            'Failed to generate AI summary',
        ) || 'Failed to generate AI summary'
      setSectionAiError((prev) => ({ ...prev, [key]: msg }))
    } finally {
      setSectionAiLoading((prev) => ({ ...prev, [key]: false }))
    }
  }

  const setSectionOpen = (sid: CollapsibleSectionId, nextOpen: boolean) => {
    setOpenSections((prev) => ({ ...prev, [sid]: nextOpen }))
    if (!nextOpen) return
    // Progressive loads
    if (sid === 'generate') {
      void ensureTemplatesLoaded()
      void ensureCompaniesLoaded()
    }
    if (sid === 'proposals') {
      void ensureProposalsLoaded(id)
    }
    // Lazy-load AI summary when a section is opened.
    void ensureSectionAiSummaryLoaded(sid, false)
  }

  const setAllSectionsOpen = (open: boolean) => {
    setOpenSections(
      Object.fromEntries(
        collapsibleSectionDefs.map((s) => [s.id, Boolean(open)]),
      ) as Record<CollapsibleSectionId, boolean>,
    )
    if (open) {
      void ensureTemplatesLoaded()
      void ensureCompaniesLoaded()
      void ensureProposalsLoaded(id)
      collapsibleSectionDefs.forEach((s) => {
        void ensureSectionAiSummaryLoaded(s.id, false)
      })
    }
  }

  const openSectionsStorageKey = useMemo(() => {
    const rid = String(id || '').trim()
    return rid ? `polaris.rfpDetail.openSections.v1:${rid}` : ''
  }, [id])

  useEffect(() => {
    // Restore section open/close state per-RFP.
    if (!openSectionsStorageKey) return
    try {
      const raw = window.localStorage.getItem(openSectionsStorageKey)
      if (!raw) return
      const parsed = JSON.parse(raw)
      if (!parsed || typeof parsed !== 'object') return
      const next: Record<CollapsibleSectionId, boolean> = {} as Record<
        CollapsibleSectionId,
        boolean
      >
      collapsibleSectionDefs.forEach((s) => {
        const v = (parsed as any)[s.id]
        next[s.id] = typeof v === 'boolean' ? v : s.defaultOpen
      })
      setOpenSections(next)
    } catch (_e) {
      // ignore
    }
  }, [openSectionsStorageKey, collapsibleSectionDefs])

  useEffect(() => {
    // Persist section open/close state per-RFP.
    if (!openSectionsStorageKey) return
    try {
      window.localStorage.setItem(
        openSectionsStorageKey,
        JSON.stringify(openSections),
      )
    } catch (_e) {
      // ignore
    }
  }, [openSections, openSectionsStorageKey])

  useEffect(() => {
    // Track which section is currently in view for the sticky TOC highlight.
    const els: HTMLElement[] = []
    tocSectionDefs.forEach((s) => {
      const el = document.getElementById(s.id)
      if (el) els.push(el)
    })
    if (els.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort(
            (a, b) =>
              (a.boundingClientRect.top || 0) - (b.boundingClientRect.top || 0),
          )
        const top = visible[0]
        if (top?.target?.id) setActiveSection(top.target.id as TocSectionId)
      },
      {
        root: null,
        // Make the active section switch as the user scrolls past headings.
        rootMargin: '-20% 0px -70% 0px',
        threshold: [0, 0.1, 0.25],
      },
    )

    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [tocSectionDefs, rfp?._id])

  useEffect(() => {
    // For checklist accuracy, preload proposals when this is a bid.
    const decision = String((rfp as any)?.review?.decision || '')
      .trim()
      .toLowerCase()
    if (decision === 'bid' && id) {
      void ensureProposalsLoaded(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, rfp?._id])

  useEffect(() => {
    // Auto-generate summaries for sections that are open by default (best-effort).
    if (!rfp?._id) return
    const open = openSections || ({} as Record<CollapsibleSectionId, boolean>)
    ;(Object.keys(open) as CollapsibleSectionId[]).forEach((sid) => {
      if (open[sid]) void ensureSectionAiSummaryLoaded(sid, false)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rfp?._id])

  const scrollToSection = (sid: TocSectionId) => {
    // Make TOC clicks feel immediate even if the intersection observer is laggy.
    setActiveSection(sid)

    // If it's a collapsible section, open it first, then scroll after layout settles.
    if (sid !== 'bid-review') setSectionOpen(sid, true)

    const targetId = String(sid)
    const maxAttempts = 8

    const tryScroll = (attempt: number) => {
      const el = document.getElementById(targetId)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        return
      }
      if (attempt >= maxAttempts) return
      requestAnimationFrame(() => tryScroll(attempt + 1))
    }

    // Defer to next frame so React state + layout have time to update.
    requestAnimationFrame(() => requestAnimationFrame(() => tryScroll(0)))
  }

  const nextStep: null | { label: string; onClick: () => void } = (() => {
    if (!rfp) return null

    const decision = String((rfp as any)?.review?.decision || '')
      .trim()
      .toLowerCase() as BidDecision

    if (!decision) {
      return {
        label: 'Make bid decision',
        onClick: () =>
          document
            .getElementById('bid-review')
            ?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      }
    }

    if (decision === 'no_bid') {
      return {
        label: 'Back to pipeline',
        onClick: () => (window.location.href = '/pipeline'),
      }
    }

    if (!Array.isArray(rfpProposals) || rfpProposals.length === 0) {
      return {
        label: 'Generate a proposal',
        onClick: () => scrollToSection('generate'),
      }
    }

    const p = [...rfpProposals].sort(
      (a: any, b: any) =>
        new Date(b?.updatedAt || 0).getTime() -
        new Date(a?.updatedAt || 0).getTime(),
    )[0]
    const pid = String(p?._id || '').trim()
    if (!pid) return null
    return {
      label: 'Open latest proposal',
      onClick: () => (window.location.href = `/proposals/${pid}`),
    }
  })()

  const SectionAiSummaryCard = ({ sid }: { sid: CollapsibleSectionId }) => {
    const key = String(sid)
    const s = sectionAiSummaries?.[key]
    const loading = Boolean(sectionAiLoading?.[key])
    const err = String(sectionAiError?.[key] || '').trim()

    return (
      <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-600">
              AI summary
            </div>
            <div className="mt-1 text-xs text-gray-500">
              Topic: <span className="font-semibold">{sectionTopic(sid)}</span>
              {s?.updatedAt ? (
                <>
                  {' '}
                  • Updated:{' '}
                  <span className="font-semibold">{s.updatedAt}</span>
                </>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void ensureSectionAiSummaryLoaded(sid, false)}
              disabled={loading}
              className="inline-flex items-center justify-center px-3 py-2 text-xs font-semibold rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50 disabled:opacity-50"
            >
              {s?.text ? 'Refresh' : 'Generate'}
            </button>
            <button
              type="button"
              onClick={() => void ensureSectionAiSummaryLoaded(sid, true)}
              disabled={loading}
              className="inline-flex items-center justify-center px-3 py-2 text-xs font-semibold rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50 disabled:opacity-50"
            >
              Regenerate
            </button>
          </div>
        </div>

        <div className="mt-3">
          {loading ? (
            <div className="text-sm text-gray-600">Generating…</div>
          ) : err ? (
            <div className="text-sm text-red-700">{err}</div>
          ) : s?.text ? (
            <div className="text-sm text-gray-800 whitespace-pre-wrap">
              {s.text}
            </div>
          ) : (
            <div className="text-sm text-gray-600">
              No summary yet. Click “Generate”.
            </div>
          )}
        </div>
      </div>
    )
  }

  const Section = ({
    sid,
    title,
    children,
    rightMeta,
  }: {
    sid: CollapsibleSectionId
    title: string
    children: ReactNode
    rightMeta?: ReactNode
  }) => {
    const isOpen = Boolean(openSections[sid])
    return (
      <section id={sid} className="scroll-mt-32 lg:scroll-mt-24">
        <div className="group rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="px-5 py-4 flex items-start justify-between gap-3">
            <button
              type="button"
              onClick={() => setSectionOpen(sid, !isOpen)}
              className="flex-1 text-left"
            >
              <div className="text-sm font-semibold text-gray-900">{title}</div>
              <div className="mt-1 text-xs text-gray-500">
                {isOpen ? 'Hide' : 'Show'}
              </div>
            </button>
            {rightMeta ? (
              <div className="text-xs text-gray-600 pt-0.5">{rightMeta}</div>
            ) : null}
          </div>
          {isOpen ? <div className="px-5 pb-5 pt-0">{children}</div> : null}
        </div>
      </section>
    )
  }

  const buyerToken = (p: any): string => {
    return (
      String(p?.profileUrl || '').trim() || String(p?.profileId || '').trim()
    )
  }

  const buyerSelectedList = useMemo(() => {
    return Object.keys(buyerSelected).filter((k) => buyerSelected[k])
  }, [buyerSelected])

  const visibleSavedBuyers = useMemo(() => {
    const saved = (rfp as any)?.buyerProfiles
    if (!Array.isArray(saved)) return []
    return saved.slice(0, 25)
  }, [rfp])

  const visibleSavedTokens = useMemo(() => {
    return visibleSavedBuyers.map((p: any) => buyerToken(p)).filter(Boolean)
  }, [visibleSavedBuyers])

  const selectedVisibleSavedCount = useMemo(() => {
    let n = 0
    visibleSavedTokens.forEach((tok) => {
      if (buyerSelected[tok]) n += 1
    })
    return n
  }, [visibleSavedTokens, buyerSelected])

  useEffect(() => {
    const el = buyerHeaderCheckboxRef.current
    if (!el) return
    const total = visibleSavedTokens.length
    if (total === 0) {
      el.indeterminate = false
      el.checked = false
      return
    }
    el.indeterminate =
      selectedVisibleSavedCount > 0 && selectedVisibleSavedCount < total
    el.checked =
      selectedVisibleSavedCount > 0 && selectedVisibleSavedCount === total
  }, [visibleSavedTokens.length, selectedVisibleSavedCount])

  const loadRFP = async (rfpId: string) => {
    try {
      // Load the RFP first; everything else should be progressive/on-demand.
      const rfpResponse = await rfpApi.get(rfpId)
      setRfp(rfpResponse.data)
      setError('')
    } catch (error) {
      console.error('Error loading RFP:', error)
      const status = (error as any)?.response?.status
      if (status === 404) setError('RFP not found')
      else setError('Failed to load RFP details')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      void loadRFP(id)
    }
  }, [id])

  useEffect(() => {
    // Clear selection when switching RFPs or when buyer list changes significantly.
    setBuyerSelected({})
  }, [rfp?._id])

  const handleAttachmentUpload = async (files: FileList | null) => {
    if (!rfp || !files) return

    const formData = new FormData()
    Array.from(files).forEach((file) => {
      formData.append('files', file)
    })

    try {
      await rfpApi.uploadAttachments(rfp._id, formData)
      toast.success('Attachments uploaded successfully')
      // Reload RFP data to show newly uploaded attachments
      await loadRFP(rfp._id)
    } catch (error) {
      console.error('Error uploading attachments:', error)
      const message =
        (error && (error as any).message) ||
        'Failed to upload attachments. Please try again.'
      toast.error(message)
    }
  }

  const handleDeleteAttachment = async (
    attachmentId: string,
    fileName: string,
  ) => {
    setAttachmentToDelete({ id: attachmentId, name: fileName })
    setDeleteModalOpen(true)
  }

  const confirmDeleteAttachment = async () => {
    if (!rfp || !attachmentToDelete) return

    setIsDeleting(true)
    try {
      await rfpApi.deleteAttachment(rfp._id, attachmentToDelete.id)
      toast.success('Attachment deleted successfully')
      // Reload RFP data to update attachments list
      await loadRFP(rfp._id)
      setDeleteModalOpen(false)
      setAttachmentToDelete(null)
    } catch (error) {
      console.error('Error deleting attachment:', error)
      const message =
        (error && (error as any).message) ||
        'Failed to delete attachment. Please try again.'
      toast.error(message)
    } finally {
      setIsDeleting(false)
    }
  }

  const removeSelectedBuyers = async () => {
    if (!rfp) return
    if (buyerSelectedList.length === 0) return
    setBuyerRemoving(true)
    try {
      const resp = await rfpApi.removeBuyerProfiles(rfp._id, {
        selected: buyerSelectedList,
      })
      setRfp(resp.data?.rfp || rfp)
      setBuyerSelected({})
      toast.success(`Removed ${resp.data?.removed ?? 0} saved buyers`)
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || e?.message || 'Failed to remove buyers',
      )
    } finally {
      setBuyerRemoving(false)
    }
  }

  const clearAllBuyers = async () => {
    if (!rfp) return
    const ok = window.confirm('Clear all saved buyer profiles for this RFP?')
    if (!ok) return
    setBuyerRemoving(true)
    try {
      const resp = await rfpApi.removeBuyerProfiles(rfp._id, { clear: true })
      setRfp(resp.data?.rfp || rfp)
      setBuyerSelected({})
      toast.success(`Cleared ${resp.data?.removed ?? 0} saved buyers`)
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || e?.message || 'Failed to clear buyers',
      )
    } finally {
      setBuyerRemoving(false)
    }
  }

  const copySavedBuyers = async () => {
    if (!rfp) return
    const saved = (rfp as any)?.buyerProfiles
    if (!Array.isArray(saved) || saved.length === 0) return
    const lines = saved.slice(0, 50).map((p: any) => {
      const name = String(p?.name || '').trim() || 'Unknown'
      const title = String(p?.title || '').trim()
      const url = String(p?.profileUrl || '').trim()
      const score = String(p?.buyerScore ?? '').trim()
      return [
        `${name}${title ? ` — ${title}` : ''}`,
        score ? `(score: ${score})` : '',
        url ? url : '',
      ]
        .filter(Boolean)
        .join(' ')
    })
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      toast.success('Copied saved buyer profiles to clipboard')
    } catch {
      toast.error('Could not copy to clipboard')
    }
  }

  const generateProposal = async (templateId: string) => {
    if (!rfp) return

    setGeneratingTemplate(templateId)
    try {
      const response = await proposalApi.generate({
        rfpId: rfp._id,
        templateId,
        title: `Proposal for ${trimTitle(rfp.title, 40)}`,
        companyId: selectedCompanyId || undefined,
        customContent: {},
      })

      // Navigate to the generated proposal
      router.push(`/proposals/${response.data._id}`)
    } catch (error) {
      console.error('Error generating proposal:', error)
      alert('Failed to generate proposal. Please try again.')
    } finally {
      setGeneratingTemplate(null)
    }
  }

  const handleAIGenerate = async () => {
    if (!rfp) return

    setGeneratingAI(true)
    try {
      const response = await proposalApi.generate({
        rfpId: rfp._id,
        templateId: 'ai-template', // Use a special identifier for AI generation
        title: `AI Proposal for ${trimTitle(rfp.title, 35)}`,
        companyId: selectedCompanyId || undefined,
        customContent: {},
      })

      // Navigate to the generated proposal
      router.push(`/proposals/${response.data._id}`)
    } catch (error) {
      console.error('Error generating AI proposal:', error)
      alert('Failed to generate AI proposal. Please try again.')
    } finally {
      setGeneratingAI(false)
      setShowAIPreviewModal(false)
    }
  }

  const rerunAiAnalysis = async () => {
    if (!rfp?._id) return
    setReanalyzingAi(true)
    try {
      const resp = await rfpApi.reanalyze(rfp._id)
      setRfp(resp.data)
      toast.success('Re-analyzed RFP')
    } catch (e) {
      console.error('Failed to re-analyze RFP:', e)
      toast.error('Failed to re-analyze RFP')
    } finally {
      setReanalyzingAi(false)
    }
  }

  const streamAiRefresh = async () => {
    if (!rfp?._id) return
    if (aiStreaming) return
    setAiStreaming(true)
    setAiRefreshStatus({ meta: 'running', dates: 'running', lists: 'running' })
    try {
      const url = rfpApi.aiRefreshStreamUrl(rfp._id)
      try {
        aiRefreshEsRef.current?.close()
      } catch {}
      const es = new EventSource(url)
      aiRefreshEsRef.current = es

      es.addEventListener('meta', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          if (payload?.updates)
            setRfp((prev) => (prev ? { ...prev, ...payload.updates } : prev))
          setAiRefreshStatus((prev) => ({ ...prev, meta: 'done' }))
        } catch {}
      })
      es.addEventListener('dates', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          if (payload?.updates)
            setRfp((prev) => (prev ? { ...prev, ...payload.updates } : prev))
          setAiRefreshStatus((prev) => ({ ...prev, dates: 'done' }))
        } catch {}
      })
      es.addEventListener('lists', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          if (payload?.updates)
            setRfp((prev) => (prev ? { ...prev, ...payload.updates } : prev))
          setAiRefreshStatus((prev) => ({ ...prev, lists: 'done' }))
        } catch {}
      })
      es.addEventListener('error', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          const msg = String(payload?.error || 'AI refresh failed')
          toast.error(msg)
          const bucket = String(payload?.bucket || '').trim() as AiBucket
          if (bucket === 'meta' || bucket === 'dates' || bucket === 'lists') {
            setAiRefreshStatus((prev) => ({ ...prev, [bucket]: 'error' }))
          } else {
            setAiRefreshStatus({
              meta: 'error',
              dates: 'error',
              lists: 'error',
            })
          }
        } catch {
          toast.error('AI refresh failed')
          setAiRefreshStatus({ meta: 'error', dates: 'error', lists: 'error' })
        } finally {
          es.close()
          setAiStreaming(false)
          aiRefreshEsRef.current = null
        }
      })
      es.addEventListener('done', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          if (payload?.rfp) setRfp(payload.rfp)
          toast.success('AI refresh complete')
        } catch {
          toast.success('AI refresh complete')
        } finally {
          es.close()
          setAiStreaming(false)
          setAiRefreshStatus({ meta: 'done', dates: 'done', lists: 'done' })
          aiRefreshEsRef.current = null
        }
      })
    } catch (e) {
      console.error('SSE failed', e)
      toast.error('Failed to start AI refresh stream')
      setAiStreaming(false)
      setAiRefreshStatus({ meta: 'error', dates: 'error', lists: 'error' })
      aiRefreshEsRef.current = null
    }
  }

  const streamAiSummary = async () => {
    if (!rfp?._id) return
    if (aiSummaryStreaming) return
    setAiSummary('')
    setAiSummaryStreaming(true)
    try {
      const url = rfpApi.aiSummaryStreamUrl(rfp._id)
      try {
        aiSummaryEsRef.current?.close()
      } catch {}
      const es = new EventSource(url)
      aiSummaryEsRef.current = es

      es.addEventListener('delta', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          const t = String(payload?.text || '')
          if (t) setAiSummary((prev) => prev + t)
        } catch {}
      })
      es.addEventListener('error', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          toast.error(String(payload?.error || 'AI summary failed'))
        } catch {
          toast.error('AI summary failed')
        } finally {
          es.close()
          setAiSummaryStreaming(false)
          aiSummaryEsRef.current = null
        }
      })
      es.addEventListener('done', (ev: any) => {
        try {
          const payload = JSON.parse(ev.data || '{}')
          if (typeof payload?.aiSummary === 'string')
            setAiSummary(payload.aiSummary)
          toast.success('AI summary complete')
        } catch {
          toast.success('AI summary complete')
        } finally {
          es.close()
          setAiSummaryStreaming(false)
          aiSummaryEsRef.current = null
        }
      })
    } catch (e) {
      console.error('SSE failed', e)
      toast.error('Failed to start AI summary stream')
      setAiSummaryStreaming(false)
      aiSummaryEsRef.current = null
    }
  }

  const setProposalDecision = async (
    proposalId: string,
    next: '' | 'shortlist' | 'reject',
  ) => {
    setUpdatingDecisionId(proposalId)
    try {
      const resp = await proposalApi.updateReview(proposalId, {
        decision: next || null,
      })
      const updated = resp.data
      setRfpProposals((prev) =>
        prev.map((p) => (p._id === proposalId ? updated : p)),
      )
    } catch (e) {
      console.error('Failed to update proposal decision:', e)
      alert('Failed to update decision. Please try again.')
    } finally {
      setUpdatingDecisionId(null)
    }
  }

  // Clarification questions are rendered inline; keep UX simple.

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (error || !rfp) {
    return (
      <div className="text-center py-12">
        <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
        <h3 className="mt-2 text-sm font-medium text-gray-900">
          RFP not found
        </h3>
        <p className="mt-1 text-sm text-gray-500">
          {error || 'The RFP you are looking for does not exist.'}
        </p>
        <div className="mt-6">
          <button
            onClick={() => router.back()}
            className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
          >
            Go Back
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <PipelineBreadcrumbs
          items={[
            { label: 'Pipeline', href: '/pipeline' },
            { label: 'RFPs', href: '/rfps' },
            { label: rfp.title || 'RFP' },
          ]}
        />
        <div className="flex items-center gap-2">
          {nextStep ? (
            <button
              type="button"
              onClick={nextStep.onClick}
              className="lg:hidden inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg text-white bg-primary-600 hover:bg-primary-700"
            >
              {nextStep.label}
            </button>
          ) : null}
          <Link
            href={`/linkedin-finder?rfpId=${encodeURIComponent(rfp._id)}`}
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg text-white bg-slate-900 hover:bg-slate-800"
          >
            <UserGroupIcon className="h-5 w-5 mr-2" />
            Run Buyer Profiles
          </Link>
        </div>
      </div>
      {/* Page tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setPageTab('details')}
            className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
              pageTab === 'details'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            type="button"
          >
            <DocumentTextIcon className="h-5 w-5 inline mr-2" />
            Details
          </button>
          <button
            onClick={() => setPageTab('pdf')}
            className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
              pageTab === 'pdf'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            type="button"
          >
            <PaperClipIcon className="h-5 w-5 inline mr-2" />
            Original PDF
          </button>
        </nav>
      </div>

      {pageTab === 'pdf' ? (
        <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-gray-200">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
              <PaperClipIcon className="h-5 w-5 text-gray-500" />
              Original PDF
            </div>
            {sourcePdfUrl ? (
              <a
                href={sourcePdfUrl}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-semibold text-primary-600 hover:text-primary-700"
              >
                Open in new tab
              </a>
            ) : null}
          </div>
          <div className="h-[75vh] bg-white">
            {sourcePdfLoading ? (
              <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
              </div>
            ) : sourcePdfError ? (
              <div className="p-6 text-sm text-gray-700">
                <div className="font-semibold text-gray-900">
                  PDF unavailable
                </div>
                <div className="mt-1">{sourcePdfError}</div>
                <div className="mt-3 text-xs text-gray-500">
                  Tip: if you upload the RFP as an attachment, the viewer will
                  fall back to that file.
                </div>
              </div>
            ) : sourcePdfUrl ? (
              <iframe
                src={`${sourcePdfUrl}#view=FitH&toolbar=1&navpanes=0`}
                className="w-full h-full bg-white block"
                title="Original RFP PDF"
                style={{
                  backgroundColor: 'white',
                  border: 'none',
                  outline: 'none',
                }}
              />
            ) : (
              <div className="p-6 text-sm text-gray-700">
                No original PDF is available for this RFP.
              </div>
            )}
          </div>
        </div>
      ) : null}

      {pageTab === 'details' ? (
        <>
          {/* Disqualified Banner */}
          {rfp.isDisqualified && (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-4">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 h-2.5 w-2.5 rounded-full bg-red-500" />
                <div className="text-sm text-red-800">
                  <span className="font-semibold">Disqualified:</span> One or
                  more critical deadlines for this RFP have passed.
                </div>
              </div>
            </div>
          )}

          {/* Hero */}
          <div className="rounded-2xl border border-gray-200 bg-white/80 backdrop-blur shadow-sm">
            <div className="p-5 sm:p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-xl bg-primary-50 p-2 ring-1 ring-primary-100">
                      <DocumentTextIcon className="h-6 w-6 text-primary-700" />
                    </div>
                    <div className="min-w-0">
                      {isBucketRunning('meta') ? (
                        <div className="animate-pulse">
                          <div className="h-7 sm:h-8 w-72 max-w-full bg-gray-200 rounded-lg" />
                        </div>
                      ) : (
                        <h1
                          className="text-xl sm:text-2xl font-bold tracking-tight text-gray-900"
                          title={rfp.title}
                        >
                          {rfp.title || 'RFP'}
                        </h1>
                      )}
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-gray-600">
                        <span className="inline-flex items-center gap-1.5">
                          <BuildingOfficeIcon className="h-4 w-4 text-gray-400" />
                          {isBucketRunning('meta') ? (
                            <span className="animate-pulse inline-block h-4 w-36 bg-gray-200 rounded" />
                          ) : (
                            <span className="font-medium text-gray-900">
                              {rfp.clientName || 'Unknown client'}
                            </span>
                          )}
                        </span>
                        <span className="text-gray-300">•</span>
                        {isBucketRunning('meta') ? (
                          <span className="animate-pulse inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-transparent ring-1 ring-gray-200">
                            Loading type…
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 ring-1 ring-blue-100">
                            {String(rfp.projectType || '').replace(/_/g, ' ') ||
                              'Unknown type'}
                          </span>
                        )}
                        <span className="text-gray-300">•</span>
                        <span className="inline-flex items-center gap-1.5">
                          <span className="text-gray-500">ID</span>
                          <span className="font-mono text-xs text-gray-900">
                            {rfp._id}
                          </span>
                        </span>
                        {aiStreaming ? (
                          <>
                            <span className="text-gray-300">•</span>
                            <span className="inline-flex items-center gap-2 text-xs font-semibold text-gray-600">
                              <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                              Refreshing…
                            </span>
                          </>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-xl border border-gray-200 bg-white p-4">
                      <div className="flex items-center gap-2">
                        <CurrencyDollarIcon className="h-5 w-5 text-emerald-600" />
                        <div>
                          <div className="text-xs font-semibold text-gray-500">
                            Budget range
                          </div>
                          <div className="text-sm font-semibold text-gray-900">
                            {isBucketRunning('meta') ? (
                              <span className="animate-pulse inline-block h-4 w-24 bg-gray-200 rounded" />
                            ) : (
                              rfp.budgetRange || 'Not specified'
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-xl border border-gray-200 bg-white p-4">
                      <div className="flex items-center gap-2">
                        <CalendarDaysIcon className="h-5 w-5 text-rose-600" />
                        <div>
                          <div className="text-xs font-semibold text-gray-500">
                            Submission deadline
                          </div>
                          <div className="text-sm font-semibold text-gray-900">
                            {isBucketRunning('dates') ? (
                              <span className="animate-pulse inline-block h-4 w-24 bg-gray-200 rounded" />
                            ) : rfp.submissionDeadline ? (
                              new Date(
                                rfp.submissionDeadline,
                              ).toLocaleDateString('en-US')
                            ) : (
                              'Not specified'
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-xl border border-gray-200 bg-white p-4">
                      <div className="flex items-center gap-2">
                        <ClockIcon className="h-5 w-5 text-amber-600" />
                        <div>
                          <div className="text-xs font-semibold text-gray-500">
                            Timeline
                          </div>
                          <div className="text-sm font-semibold text-gray-900">
                            {isBucketRunning('lists') ? (
                              <span className="animate-pulse inline-block h-4 w-24 bg-gray-200 rounded" />
                            ) : Array.isArray(rfp.timeline) ? (
                              rfp.timeline[0] || 'TBD'
                            ) : (
                              (rfp.timeline as any) || 'TBD'
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-xl border border-gray-200 bg-white p-4">
                      <div className="flex items-center gap-2">
                        <DocumentTextIcon className="h-5 w-5 text-primary-600" />
                        <div>
                          <div className="text-xs font-semibold text-gray-500">
                            Fit score
                          </div>
                          <div className="text-sm font-semibold text-gray-900">
                            {aiStreaming ? (
                              <span className="animate-pulse inline-block h-4 w-10 bg-gray-200 rounded" />
                            ) : typeof (rfp as any)?.fitScore === 'number' ? (
                              String((rfp as any).fitScore)
                            ) : (
                              '—'
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row lg:flex-col gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => scrollToSection('bid-review')}
                    className="inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg border border-gray-300 bg-white text-gray-900 hover:bg-gray-50"
                  >
                    Make bid decision
                  </button>
                  <button
                    type="button"
                    onClick={() => scrollToSection('requirements')}
                    className="inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg border border-gray-300 bg-white text-gray-900 hover:bg-gray-50"
                  >
                    Review requirements
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Mobile jump bar (offset for global header) */}
          <div className="lg:hidden sticky top-16 z-30 -mx-4 sm:-mx-6 bg-white/90 backdrop-blur border-y border-gray-200 px-4 sm:px-6 py-3">
            <div className="flex items-center gap-2">
              <select
                value={activeSection}
                onChange={(e) =>
                  scrollToSection(e.target.value as TocSectionId)
                }
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 bg-white text-sm"
                aria-label="Jump to section"
              >
                {tocSectionDefs.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setAllSectionsOpen(true)}
                className="inline-flex items-center justify-center px-3 py-2 text-sm font-semibold rounded-lg border border-gray-300 text-gray-900 bg-white hover:bg-gray-50"
              >
                Open
              </button>
              <button
                type="button"
                onClick={() => setAllSectionsOpen(false)}
                className="inline-flex items-center justify-center px-3 py-2 text-sm font-semibold rounded-lg border border-gray-300 text-gray-900 bg-white hover:bg-gray-50"
              >
                Close
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="lg:grid lg:grid-cols-12 lg:gap-8 items-start">
            {/* Sticky TOC */}
            <aside className="hidden lg:block lg:col-span-3 lg:order-1">
              <div className="sticky top-24 space-y-3">
                <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
                  <div className="px-4 py-4 border-b border-gray-100">
                    <div className="text-sm font-semibold text-gray-900">
                      On this page
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      Review suitability, then take action
                    </div>
                  </div>
                  <div className="px-3 py-3 border-b border-gray-100 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setAllSectionsOpen(true)}
                      className="flex-1 inline-flex items-center justify-center px-3 py-2 text-xs font-semibold rounded-lg border border-gray-300 text-gray-900 bg-white hover:bg-gray-50"
                    >
                      Open all
                    </button>
                    <button
                      type="button"
                      onClick={() => setAllSectionsOpen(false)}
                      className="flex-1 inline-flex items-center justify-center px-3 py-2 text-xs font-semibold rounded-lg border border-gray-300 text-gray-900 bg-white hover:bg-gray-50"
                    >
                      Collapse all
                    </button>
                  </div>
                  <nav className="px-2 py-2 max-h-[calc(100vh-16rem)] overflow-auto custom-scrollbar">
                    {tocSectionDefs.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => scrollToSection(s.id)}
                        className={`w-full text-left px-3 py-2 rounded-xl text-sm transition-colors ${
                          activeSection === s.id
                            ? 'bg-primary-50 text-primary-700 font-semibold'
                            : 'text-gray-700 hover:bg-gray-50'
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </nav>
                </div>
                {supportingError ? (
                  <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-xl p-3">
                    {supportingError}
                  </div>
                ) : null}
              </div>
            </aside>

            {/* Right rail: Next steps */}
            <aside className="lg:col-span-3 lg:order-3 order-1 space-y-4">
              <div className="lg:sticky lg:top-24 space-y-4">
                <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        Next steps
                      </div>
                      <div className="mt-1 text-xs text-gray-600">
                        {checklistDone}/{checklist.length} checklist items
                        complete
                      </div>
                    </div>
                    {nextStep ? (
                      <button
                        type="button"
                        onClick={nextStep.onClick}
                        className="inline-flex items-center justify-center px-3 py-2 text-xs font-semibold rounded-lg text-white bg-primary-600 hover:bg-primary-700"
                      >
                        {nextStep.label}
                      </button>
                    ) : null}
                  </div>
                  <div className="px-5 py-4">
                    {checklist.length === 0 ? (
                      <div className="text-sm text-gray-500">No checklist.</div>
                    ) : (
                      <ul className="space-y-2">
                        {checklist.map((it) => (
                          <li
                            key={it.id}
                            className="flex items-start justify-between gap-3 rounded-xl border border-gray-200 bg-white p-3"
                          >
                            <div className="min-w-0">
                              <div className="text-sm font-semibold text-gray-900">
                                {it.label}
                              </div>
                              {it.hint ? (
                                <div className="mt-0.5 text-xs text-gray-600 line-clamp-2">
                                  {it.hint}
                                </div>
                              ) : null}
                            </div>
                            <span
                              className={`shrink-0 px-2 py-1 rounded-full text-xs font-semibold ${
                                it.done
                                  ? 'bg-green-100 text-green-800'
                                  : 'bg-gray-100 text-gray-700'
                              }`}
                            >
                              {it.done ? 'Done' : 'Pending'}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
                  <div className="px-5 py-4 border-b border-gray-100">
                    <div className="text-sm font-semibold text-gray-900">
                      AI
                    </div>
                    <div className="mt-1 text-xs text-gray-600">
                      Generate/refresh machine-generated artifacts
                    </div>
                  </div>
                  <div className="px-5 py-4 space-y-2">
                    <button
                      type="button"
                      onClick={() => setShowAIPreviewModal(true)}
                      className="w-full inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg text-white bg-primary-600 hover:bg-primary-700"
                    >
                      Preview AI template
                    </button>
                    <button
                      type="button"
                      onClick={rerunAiAnalysis}
                      disabled={reanalyzingAi}
                      className="w-full inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg border border-gray-300 bg-white text-gray-900 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {reanalyzingAi ? 'Re-analyzing…' : 'Re-run AI extraction'}
                    </button>
                    <button
                      type="button"
                      onClick={streamAiRefresh}
                      disabled={aiStreaming}
                      className="w-full inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg border border-gray-300 bg-white text-gray-900 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {aiStreaming
                        ? 'Streaming refresh…'
                        : 'Stream AI refresh (SSE)'}
                    </button>
                    {aiStreaming ? (
                      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
                        <div className="text-xs font-semibold text-gray-700">
                          Refresh progress
                        </div>
                        <div className="mt-2 space-y-1 text-xs text-gray-700">
                          {(['meta', 'dates', 'lists'] as AiBucket[]).map(
                            (k) => {
                              const st = aiRefreshStatus[k]
                              const dot =
                                st === 'done'
                                  ? 'bg-green-500'
                                  : st === 'error'
                                  ? 'bg-red-500'
                                  : st === 'running'
                                  ? 'bg-blue-500'
                                  : 'bg-gray-300'
                              const label =
                                k === 'meta'
                                  ? 'Metadata'
                                  : k === 'dates'
                                  ? 'Dates'
                                  : 'Requirements/lists'
                              return (
                                <div
                                  key={k}
                                  className="flex items-center justify-between gap-2"
                                >
                                  <div className="flex items-center gap-2">
                                    <span
                                      className={`h-2 w-2 rounded-full ${dot}`}
                                    />
                                    <span>{label}</span>
                                  </div>
                                  <span className="font-semibold text-gray-600">
                                    {st === 'running'
                                      ? 'Running…'
                                      : st === 'done'
                                      ? 'Done'
                                      : st === 'error'
                                      ? 'Error'
                                      : 'Idle'}
                                  </span>
                                </div>
                              )
                            },
                          )}
                        </div>
                      </div>
                    ) : null}
                    <button
                      type="button"
                      onClick={streamAiSummary}
                      disabled={aiSummaryStreaming}
                      className="w-full inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg border border-gray-300 bg-white text-gray-900 hover:bg-gray-50 disabled:opacity-50"
                    >
                      {aiSummaryStreaming
                        ? 'Streaming summary…'
                        : 'Stream AI summary'}
                    </button>
                    {aiSummary ? (
                      <div className="mt-2 rounded-xl border border-gray-200 bg-gray-50 p-3">
                        <div className="text-xs font-semibold text-gray-700 mb-1">
                          AI summary
                        </div>
                        <pre className="whitespace-pre-wrap text-xs text-gray-800 max-h-64 overflow-auto custom-scrollbar">
                          {aiSummary}
                        </pre>
                      </div>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => scrollToSection('generate')}
                      className="w-full inline-flex items-center justify-center px-4 py-2 text-sm font-semibold rounded-lg border border-gray-300 bg-white text-gray-900 hover:bg-gray-50"
                    >
                      Go to proposal generation
                    </button>
                  </div>
                </div>
              </div>
            </aside>

            {/* Main column */}
            <main className="lg:col-span-6 lg:order-2 order-2 space-y-6">
              {/* Bid / no-bid panel */}
              <div
                id="bid-review"
                className="rounded-2xl border border-gray-200 bg-white shadow-sm scroll-mt-32 lg:scroll-mt-24"
              >
                <div className="px-5 py-4 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold text-gray-900">
                      Bid / No-bid review
                    </div>
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold ${decisionPill(
                        bidDecision,
                      )}`}
                    >
                      {decisionLabel(bidDecision)}
                    </span>
                    {(rfp as any)?.review?.updatedAt ? (
                      <span className="text-xs text-gray-500">
                        Updated{' '}
                        {String((rfp as any).review.updatedAt).slice(0, 10)}
                      </span>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <select
                      value={bidDecision}
                      onChange={(e) =>
                        setBidDecision(e.target.value as BidDecision)
                      }
                      className="border border-gray-300 rounded-md px-3 py-2 bg-white text-sm"
                      aria-label="Bid decision"
                    >
                      <option value="">Unreviewed</option>
                      <option value="bid">Bid</option>
                      <option value="maybe">Maybe</option>
                      <option value="no_bid">No-bid</option>
                    </select>
                    <button
                      type="button"
                      onClick={saveBidReview}
                      disabled={!bidDirty || bidSaving}
                      className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                    >
                      {bidSaving ? 'Saving…' : bidDirty ? 'Save' : 'Saved'}
                    </button>
                  </div>
                </div>

                <div className="px-5 py-4">
                  {bidBlockers.length > 0 ? (
                    <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-4">
                      <div className="text-sm font-semibold text-amber-900">
                        Potential blockers
                      </div>
                      <ul className="mt-2 text-sm text-amber-800 list-disc pl-5 space-y-1">
                        {bidBlockers.map((b, idx) => (
                          <li key={idx}>{b}</li>
                        ))}
                      </ul>
                      {bidBlockersList.length === 0 ? (
                        <div className="mt-3">
                          <button
                            type="button"
                            onClick={initBlockersFromDetected}
                            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md border border-amber-300 text-amber-900 bg-white hover:bg-amber-50"
                          >
                            Initialize checklist from these
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="mb-4 text-sm text-gray-600">
                      No obvious blockers detected from deadlines/budget.
                    </div>
                  )}

                  <div className="mb-4">
                    <div className="text-sm font-semibold text-gray-900">
                      Blockers checklist
                    </div>
                    <div className="mt-2 space-y-2">
                      {bidBlockersList.length === 0 ? (
                        <div className="text-sm text-gray-500">
                          No blockers tracked yet.
                        </div>
                      ) : (
                        bidBlockersList.map((b) => (
                          <div
                            key={b.id}
                            className="flex items-start gap-2 rounded-lg border border-gray-200 bg-white p-3"
                          >
                            <select
                              value={b.status}
                              onChange={(e) => {
                                const v = e.target.value as
                                  | 'open'
                                  | 'resolved'
                                  | 'waived'
                                setBidBlockersList((prev) =>
                                  prev.map((x) =>
                                    x.id === b.id ? { ...x, status: v } : x,
                                  ),
                                )
                              }}
                              className="border border-gray-300 rounded-md px-2 py-1 text-sm bg-white"
                              aria-label="Blocker status"
                            >
                              <option value="open">Open</option>
                              <option value="resolved">Resolved</option>
                              <option value="waived">Waived</option>
                            </select>
                            <input
                              value={b.text}
                              onChange={(e) => {
                                const v = e.target.value
                                setBidBlockersList((prev) =>
                                  prev.map((x) =>
                                    x.id === b.id ? { ...x, text: v } : x,
                                  ),
                                )
                              }}
                              className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm"
                              placeholder="Blocker description"
                            />
                            <button
                              type="button"
                              onClick={() =>
                                setBidBlockersList((prev) =>
                                  prev.filter((x) => x.id !== b.id),
                                )
                              }
                              className="inline-flex items-center justify-center px-2 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                              title="Remove blocker"
                            >
                              <XMarkIcon className="h-4 w-4" />
                            </button>
                          </div>
                        ))
                      )}

                      <div className="flex items-center gap-2">
                        <input
                          value={newBlockerText}
                          onChange={(e) => setNewBlockerText(e.target.value)}
                          className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm"
                          placeholder="Add a blocker…"
                        />
                        <button
                          type="button"
                          onClick={addBlocker}
                          className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="text-sm font-semibold text-gray-900">
                    Reasons (quick tags)
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {[
                      'Strong fit',
                      'Strategic client',
                      'Budget too low',
                      'Timeline too tight',
                      'Outside scope',
                      'Missing info',
                      'Competitive / price-sensitive',
                    ].map((r) => {
                      const on = bidReasons.includes(r)
                      return (
                        <button
                          key={r}
                          type="button"
                          onClick={() => toggleBidReason(r)}
                          className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
                            on
                              ? 'bg-primary-50 border-primary-200 text-primary-800'
                              : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                          }`}
                        >
                          {r}
                        </button>
                      )
                    })}
                  </div>

                  <div className="mt-4">
                    <label className="block text-sm font-semibold text-gray-900">
                      Notes
                    </label>
                    <textarea
                      value={bidNotes}
                      onChange={(e) => setBidNotes(e.target.value)}
                      rows={4}
                      className="mt-2 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                      placeholder="What matters for suitability? Key risks? Who needs to be involved? What would make this a 'yes'?"
                    />
                  </div>
                </div>
              </div>

              <Section
                sid="suitability"
                title="Suitability"
                rightMeta={
                  typeof (rfp as any)?.fitScore === 'number'
                    ? `Fit ${(rfp as any).fitScore}`
                    : undefined
                }
              >
                <SectionAiSummaryCard sid="suitability" />
                {Array.isArray(rfp.dateWarnings) &&
                  rfp.dateWarnings.length > 0 && (
                    <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-4">
                      <div className="text-sm font-semibold text-amber-900">
                        Timing / sanity warnings
                      </div>
                      <ul className="mt-2 text-sm text-amber-800 list-disc pl-5 space-y-1">
                        {rfp.dateWarnings.slice(0, 10).map((w, idx) => (
                          <li key={idx}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                {typeof (rfp as any)?.fitScore === 'number' && (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-semibold text-slate-900">
                        Buyer Profiles fit score
                      </div>
                      <div className="text-sm font-semibold text-slate-900">
                        {(rfp as any).fitScore}
                      </div>
                    </div>
                    {Array.isArray((rfp as any)?.fitReasons) &&
                      (rfp as any).fitReasons.length > 0 && (
                        <ul className="mt-2 text-sm text-slate-700 list-disc pl-5 space-y-1">
                          {(rfp as any).fitReasons
                            .slice(0, 12)
                            .map((w: any, idx: any) => (
                              <li key={idx}>{w}</li>
                            ))}
                        </ul>
                      )}
                  </div>
                )}

                {(rfp as any)?.rawText ? (
                  <div className="mt-4 text-xs text-gray-500">
                    Extracted text length:{' '}
                    <span className="font-semibold">
                      {String((rfp as any).rawText || '').length}
                    </span>
                    {typeof (rfp as any)?._analysis?.usedAi === 'boolean' ? (
                      <>
                        {' '}
                        • AI:{' '}
                        <span className="font-semibold">
                          {(rfp as any)?._analysis?.usedAi ? 'on' : 'off'}
                        </span>
                      </>
                    ) : null}
                    {(rfp as any)?._analysis?.model ? (
                      <>
                        {' '}
                        • Model:{' '}
                        <span className="font-semibold">
                          {(rfp as any)?._analysis?.model}
                        </span>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </Section>

              <Section sid="overview" title="Overview">
                <SectionAiSummaryCard sid="overview" />
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
                    <div className="p-4">
                      <div className="flex items-center">
                        <CurrencyDollarIcon className="h-5 w-5 text-green-500" />
                        <div className="ml-3">
                          <div className="text-xs text-gray-500">
                            Budget Range
                          </div>
                          <div className="text-sm font-semibold text-gray-900">
                            {rfp.budgetRange || 'Not specified'}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
                    <div className="p-4">
                      <div className="flex items-center">
                        <CalendarDaysIcon className="h-5 w-5 text-red-500" />
                        <div className="ml-3">
                          <div className="text-xs text-gray-500">
                            Submission deadline
                          </div>
                          <div className="text-sm font-semibold text-gray-900">
                            {rfp.submissionDeadline
                              ? new Date(
                                  rfp.submissionDeadline,
                                ).toLocaleDateString('en-US')
                              : 'Not specified'}
                          </div>
                          {rfp.submissionDeadline &&
                            isDatePassed(rfp.submissionDeadline) && (
                              <div className="text-xs font-medium text-red-600 mt-1">
                                Deadline passed
                              </div>
                            )}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
                    <div className="p-4">
                      <div className="flex items-center">
                        <ClockIcon className="h-5 w-5 text-yellow-500" />
                        <div className="ml-3">
                          <div className="text-xs text-gray-500">Timeline</div>
                          <div className="text-sm font-semibold text-gray-900">
                            {rfp.timeline || 'To be determined'}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
                    <div className="p-4">
                      <div className="flex items-center">
                        <DocumentTextIcon className="h-5 w-5 text-primary-500" />
                        <div className="ml-3">
                          <div className="text-xs text-gray-500">
                            Questions deadline
                          </div>
                          <div className="text-sm font-semibold text-gray-900">
                            {rfp.questionsDeadline
                              ? new Date(
                                  rfp.questionsDeadline,
                                ).toLocaleDateString('en-US')
                              : 'Not specified'}
                          </div>
                          {rfp.questionsDeadline &&
                            isDatePassed(rfp.questionsDeadline) && (
                              <div className="text-xs font-medium text-red-600 mt-1">
                                Deadline passed
                              </div>
                            )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </Section>

              <Section
                sid="requirements"
                title="Key requirements"
                rightMeta={
                  Array.isArray(rfp.keyRequirements)
                    ? `${rfp.keyRequirements.length} items`
                    : undefined
                }
              >
                <SectionAiSummaryCard sid="requirements" />
                {rfp.keyRequirements && rfp.keyRequirements.length > 0 ? (
                  <div>
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
                      <div className="text-sm text-gray-600">
                        Assess each requirement for suitability, then copy a
                        compliance matrix for proposal work.
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={copyComplianceMatrix}
                          className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                        >
                          Copy compliance matrix
                        </button>
                        <button
                          type="button"
                          onClick={downloadComplianceCsv}
                          className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                        >
                          Download CSV
                        </button>
                        <button
                          type="button"
                          onClick={saveRequirements}
                          disabled={reqSaving}
                          className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                        >
                          {reqSaving ? 'Saving…' : 'Save'}
                        </button>
                      </div>
                    </div>

                    <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
                      <div className="text-sm font-semibold text-gray-900">
                        Auto-seed mapped proposal sections
                      </div>
                      <div className="mt-2 text-sm text-gray-600">
                        Picks 1–2 likely proposal sections per requirement using
                        a template’s section titles (only fills empty mappings).
                      </div>
                      <div className="mt-3 flex flex-col sm:flex-row sm:items-center gap-2">
                        <select
                          value={seedTemplateId}
                          onChange={(e) => setSeedTemplateId(e.target.value)}
                          className="flex-1 border border-gray-300 rounded-md px-3 py-2 bg-white text-sm"
                        >
                          <option value="">
                            {templates?.length
                              ? 'Choose template (optional)'
                              : 'Templates not loaded yet'}
                          </option>
                          {(templates || []).map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name} ({t.projectType})
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={autoseedMappedSections}
                          disabled={seedingReqs}
                          className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                        >
                          {seedingReqs ? 'Seeding…' : 'Auto-seed'}
                        </button>
                        {!templates?.length ? (
                          <button
                            type="button"
                            onClick={() => void ensureTemplatesLoaded()}
                            className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                          >
                            Load templates
                          </button>
                        ) : null}
                      </div>
                    </div>

                    <div className="space-y-3">
                      {rfp.keyRequirements.slice(0, 40).map((req, idx) => {
                        const text = String(req || '').trim()
                        const a = reqAssessments[text] || {
                          text,
                          status: 'unknown' as ReqStatus,
                          notes: '',
                          mappedSections: [],
                        }
                        return (
                          <div
                            key={`${idx}-${text}`}
                            className="rounded-lg border border-gray-200 bg-white p-4"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex items-start gap-3">
                                <div className="mt-2 h-2 w-2 rounded-full bg-primary-600" />
                                <div className="text-sm font-semibold text-gray-900">
                                  {text}
                                </div>
                              </div>
                              <select
                                value={a.status}
                                onChange={(e) =>
                                  setReq(text, {
                                    status: e.target.value as ReqStatus,
                                  })
                                }
                                className="border border-gray-300 rounded-md px-2 py-1 text-sm bg-white"
                                aria-label="Requirement assessment"
                              >
                                <option value="unknown">Unknown</option>
                                <option value="ok">OK</option>
                                <option value="risk">Risk</option>
                                <option value="gap">Gap</option>
                              </select>
                            </div>

                            <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                              <div>
                                <label className="block text-xs font-semibold text-gray-700">
                                  Notes
                                </label>
                                <textarea
                                  value={a.notes}
                                  onChange={(e) =>
                                    setReq(text, { notes: e.target.value })
                                  }
                                  rows={3}
                                  className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                                  placeholder="Why OK/risk/gap? What’s needed?"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-semibold text-gray-700">
                                  Proposal sections (comma-separated)
                                </label>
                                <input
                                  value={(a.mappedSections || []).join(', ')}
                                  onChange={(e) =>
                                    setReq(text, {
                                      mappedSections: String(
                                        e.target.value || '',
                                      )
                                        .split(',')
                                        .map((x) => x.trim())
                                        .filter(Boolean)
                                        .slice(0, 20),
                                    })
                                  }
                                  className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                                  placeholder="e.g. Approach, Experience, Timeline"
                                />
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-gray-500">
                    No specific requirements identified.
                  </div>
                )}
              </Section>

              <Section sid="deliverables" title="Deliverables & criteria">
                <SectionAiSummaryCard sid="deliverables" />
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      Expected deliverables
                    </div>
                    <div className="mt-2">
                      {rfp.deliverables && rfp.deliverables.length > 0 ? (
                        <ul className="space-y-2">
                          {rfp.deliverables
                            .slice(0, 12)
                            .map((deliverable, idx) => (
                              <li key={idx} className="flex items-start gap-3">
                                <div className="mt-2 h-2 w-2 rounded-full bg-green-600" />
                                <div className="text-sm text-gray-800">
                                  {deliverable}
                                </div>
                              </li>
                            ))}
                        </ul>
                      ) : (
                        <div className="text-sm text-gray-500">
                          No specific deliverables identified.
                        </div>
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      Evaluation criteria
                    </div>
                    <div className="mt-2">
                      {(rfp as any).evaluationCriteria &&
                      (rfp as any).evaluationCriteria.length > 0 ? (
                        <ul className="space-y-2">
                          {(rfp as any).evaluationCriteria
                            .slice(0, 12)
                            .map((criteria: any, idx: number) => (
                              <li key={idx} className="flex items-start gap-3">
                                <div className="mt-2 h-2 w-2 rounded-full bg-yellow-600" />
                                <div className="text-sm text-gray-800">
                                  {typeof criteria === 'string'
                                    ? criteria
                                    : criteria?.criteria ||
                                      'Evaluation criterion'}
                                </div>
                              </li>
                            ))}
                        </ul>
                      ) : (
                        <div className="text-sm text-gray-500">
                          No evaluation criteria specified.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="lg:col-span-2">
                    <div className="text-sm font-semibold text-gray-900">
                      Critical information
                    </div>
                    <div className="mt-2">
                      {rfp.criticalInformation &&
                      rfp.criticalInformation.length > 0 ? (
                        <ul className="space-y-2">
                          {rfp.criticalInformation
                            .slice(0, 12)
                            .map((info, idx) => (
                              <li key={idx} className="flex items-start gap-3">
                                <div className="mt-2 h-2 w-2 rounded-full bg-red-600" />
                                <div className="text-sm text-gray-800">
                                  {info}
                                </div>
                              </li>
                            ))}
                        </ul>
                      ) : (
                        <div className="text-sm text-gray-500">
                          No critical information identified.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="lg:col-span-2">
                    <div className="text-sm font-semibold text-gray-900">
                      Clarification questions
                    </div>
                    <div className="mt-2">
                      {rfp.clarificationQuestions &&
                      rfp.clarificationQuestions.length > 0 ? (
                        <div className="space-y-2">
                          {rfp.clarificationQuestions
                            .slice(0, 25)
                            .map((question, index) => (
                              <div
                                key={index}
                                className="flex items-start py-3 px-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                              >
                                <span className="flex-shrink-0 inline-flex items-center justify-center h-6 w-6 rounded-full bg-primary-100 text-primary-600 text-xs font-medium mr-3 mt-0.5">
                                  {index + 1}
                                </span>
                                <p className="text-sm text-gray-700 leading-relaxed flex-1">
                                  {question}
                                </p>
                              </div>
                            ))}
                        </div>
                      ) : (
                        <div className="text-sm text-gray-500">
                          No clarification questions identified.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </Section>

              <Section
                sid="attachments"
                title="Attachments"
                rightMeta={
                  Array.isArray((rfp as any)?.attachments)
                    ? `${(rfp as any).attachments.length} files`
                    : undefined
                }
              >
                <SectionAiSummaryCard sid="attachments" />
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm text-gray-600">
                    Upload and manage files related to this RFP.
                  </div>
                  <button
                    onClick={() => setShowAttachmentModal(true)}
                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700"
                  >
                    <PaperClipIcon className="h-5 w-5 mr-2" />
                    Add attachments
                  </button>
                </div>

                <div className="mt-4">
                  {rfp?.attachments?.length ? (
                    <ul role="list" className="divide-y divide-gray-200">
                      {rfp.attachments.map((file) => (
                        <li
                          key={file.fileName}
                          className="py-4 flex items-center justify-between"
                        >
                          <div className="flex items-center space-x-3">
                            <PaperClipIcon className="h-5 w-5 text-gray-400" />
                            <div>
                              <p className="text-sm font-medium text-gray-900">
                                {file.originalName}
                              </p>
                              <p className="text-xs text-gray-500">
                                {(file.fileSize / 1024).toFixed(1)} KB •{' '}
                                {file.fileType.toUpperCase()}
                              </p>
                            </div>
                          </div>
                          <button
                            onClick={() =>
                              handleDeleteAttachment(
                                file._id,
                                file.originalName,
                              )
                            }
                            className="inline-flex items-center p-1.5 text-red-600 hover:text-red-800 hover:bg-red-50 rounded-md transition-colors"
                            title="Delete attachment"
                          >
                            <XMarkIcon className="h-5 w-5" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-gray-500">
                      No attachments uploaded yet.
                    </p>
                  )}
                </div>
              </Section>

              <Section
                sid="buyers"
                title="Buyers"
                rightMeta={
                  Array.isArray((rfp as any)?.buyerProfiles)
                    ? `${(rfp as any).buyerProfiles.length} saved`
                    : undefined
                }
              >
                <SectionAiSummaryCard sid="buyers" />
                {Array.isArray((rfp as any)?.buyerProfiles) &&
                (rfp as any).buyerProfiles.length > 0 ? (
                  <div>
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-sm font-semibold text-gray-900">
                          Saved buyer profiles
                        </div>
                        <div className="mt-1 text-xs text-gray-600">
                          Selected:{' '}
                          <span className="font-semibold">
                            {buyerSelectedList.length}
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={copySavedBuyers}
                          className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                        >
                          Copy
                        </button>
                        <button
                          type="button"
                          onClick={removeSelectedBuyers}
                          disabled={
                            buyerRemoving || buyerSelectedList.length === 0
                          }
                          className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                        >
                          {buyerRemoving ? 'Working…' : 'Remove selected'}
                        </button>
                        <button
                          type="button"
                          onClick={clearAllBuyers}
                          disabled={buyerRemoving}
                          className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-red-300 text-red-700 bg-white hover:bg-red-50 disabled:opacity-50"
                        >
                          Clear all
                        </button>
                        <Link
                          href={`/linkedin-finder?rfpId=${encodeURIComponent(
                            rfp._id,
                          )}`}
                          className="text-xs text-primary-600 hover:text-primary-800"
                        >
                          Update via Buyer Profiles →
                        </Link>
                      </div>
                    </div>
                    <div className="mt-3 overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead>
                          <tr className="text-left text-xs uppercase tracking-wider text-gray-500">
                            <th className="py-2 pr-4">
                              <input
                                ref={buyerHeaderCheckboxRef}
                                type="checkbox"
                                onChange={() => {
                                  const total = visibleSavedTokens.length
                                  if (total === 0) return
                                  if (selectedVisibleSavedCount === total) {
                                    setBuyerSelected((prev) => {
                                      const next = { ...prev }
                                      visibleSavedTokens.forEach((tok) => {
                                        delete next[tok]
                                      })
                                      return next
                                    })
                                  } else {
                                    const next: Record<string, boolean> = {}
                                    visibleSavedTokens.forEach((tok) => {
                                      next[tok] = true
                                    })
                                    setBuyerSelected((prev) => ({
                                      ...prev,
                                      ...next,
                                    }))
                                  }
                                }}
                              />
                            </th>
                            <th className="py-2 pr-4">Score</th>
                            <th className="py-2 pr-4">Name</th>
                            <th className="py-2 pr-4">Title</th>
                            <th className="py-2 pr-4">Profile</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                          {(rfp as any).buyerProfiles
                            .slice(0, 25)
                            .map((p: any) => (
                              <tr
                                key={p?.profileId || p?.profileUrl}
                                className="align-top"
                              >
                                <td className="py-3 pr-4">
                                  <input
                                    type="checkbox"
                                    checked={Boolean(
                                      buyerSelected[buyerToken(p)] || false,
                                    )}
                                    onChange={() => {
                                      const tok = buyerToken(p)
                                      if (!tok) return
                                      setBuyerSelected((prev) => ({
                                        ...prev,
                                        [tok]: !prev[tok],
                                      }))
                                    }}
                                  />
                                </td>
                                <td className="py-3 pr-4 font-semibold text-gray-900">
                                  {p?.buyerScore ?? 0}
                                </td>
                                <td className="py-3 pr-4 text-gray-900">
                                  <div>{p?.name || '—'}</div>
                                  {p?.ai?.personaSummary && (
                                    <div className="mt-1 text-xs text-gray-700 max-w-xl">
                                      {p.ai.personaSummary}
                                    </div>
                                  )}
                                </td>
                                <td className="py-3 pr-4 text-gray-900">
                                  {p?.title || '—'}
                                </td>
                                <td className="py-3 pr-4">
                                  {p?.profileUrl ? (
                                    <a
                                      href={p.profileUrl}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="text-primary-600 hover:text-primary-800"
                                    >
                                      Open →
                                    </a>
                                  ) : (
                                    '—'
                                  )}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="text-sm text-gray-500">
                    No saved buyer profiles yet.
                  </div>
                )}
              </Section>

              <Section sid="generate" title="Generate proposal">
                <SectionAiSummaryCard sid="generate" />
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="border border-gray-200 rounded-lg p-4 hover:border-primary-300 transition-colors">
                    <div className="flex items-center mb-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-purple-100 to-pink-100 rounded-lg flex items-center justify-center mr-3">
                        <PlusIcon className="h-5 w-5 text-purple-600" />
                      </div>
                      <div>
                        <h4 className="font-medium text-gray-900">
                          AI Template
                        </h4>
                        <p className="text-sm text-gray-500">
                          Generate a first-pass proposal
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => setShowAIPreviewModal(true)}
                      className="w-full inline-flex items-center justify-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                    >
                      Preview
                    </button>
                  </div>
                </div>

                <div className="mt-6">
                  <div className="text-sm font-semibold text-gray-900">
                    Templates
                  </div>
                  <div className="mt-2">
                    {companies.length > 0 && (
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-900 mb-2">
                          Proposal Company / Branding
                        </label>
                        <select
                          value={selectedCompanyId || ''}
                          onChange={(e) =>
                            setSelectedCompanyId(e.target.value || null)
                          }
                          className="w-full sm:w-96 border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
                        >
                          {companies.map((c) => (
                            <option key={c.companyId} value={c.companyId}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                        <p className="mt-1 text-xs text-gray-500">
                          Controls Title/Cover Letter/Experience content and
                          exports.
                        </p>
                      </div>
                    )}

                    {templatesLoading || companiesLoading ? (
                      <p className="text-sm text-gray-500">
                        Loading templates/companies…
                      </p>
                    ) : templates.length > 0 ? (
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {templates.map((template) => (
                          <div
                            key={template.id}
                            className="border border-gray-200 rounded-lg p-4 hover:border-primary-300 transition-colors"
                          >
                            <h4 className="font-medium text-gray-900">
                              {template.name}
                            </h4>
                            <p className="text-sm text-gray-500 mt-1">
                              {template.sectionCount} sections
                            </p>
                            <p className="text-xs text-gray-400 mt-2">
                              {template.projectType.replace('_', ' ')}
                            </p>
                            <button
                              onClick={() => generateProposal(template.id)}
                              disabled={generatingTemplate !== null}
                              className="mt-3 w-full inline-flex items-center justify-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {generatingTemplate === template.id ? (
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                              ) : (
                                <>
                                  <PlusIcon className="h-4 w-4 mr-1" />
                                  Generate
                                </>
                              )}
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm text-gray-500">
                          No templates loaded yet.
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            void ensureTemplatesLoaded()
                            void ensureCompaniesLoaded()
                          }}
                          className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                        >
                          Load templates
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </Section>

              <Section sid="proposals" title="Proposals">
                <SectionAiSummaryCard sid="proposals" />
                {proposalsLoading ? (
                  <p className="text-sm text-gray-500">Loading proposals…</p>
                ) : rfpProposals.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    No proposals yet for this RFP.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                            Proposal
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                            Score
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                            Status
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                            Updated
                          </th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                            Decision
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {[...rfpProposals]
                          .sort((a, b) => {
                            const as = a?.review?.score
                            const bs = b?.review?.score
                            const an = typeof as === 'number' ? as : -1
                            const bn = typeof bs === 'number' ? bs : -1
                            if (bn !== an) return bn - an
                            return (
                              new Date(b.updatedAt).getTime() -
                              new Date(a.updatedAt).getTime()
                            )
                          })
                          .map((p) => (
                            <tr key={p._id} className="hover:bg-gray-50">
                              <td className="px-4 py-3 text-sm text-gray-900">
                                <Link
                                  href={`/proposals/${p._id}`}
                                  className="text-primary-600 hover:text-primary-800 font-medium"
                                >
                                  {p.title}
                                </Link>
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-900">
                                {typeof p?.review?.score === 'number'
                                  ? p.review.score
                                  : '—'}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-900">
                                {p.status}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-600">
                                {p.updatedAt
                                  ? new Date(p.updatedAt).toLocaleDateString(
                                      'en-US',
                                    )
                                  : '—'}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-900">
                                <div className="flex items-center space-x-2">
                                  <button
                                    onClick={() =>
                                      setProposalDecision(
                                        p._id,
                                        p?.review?.decision === 'shortlist'
                                          ? ''
                                          : 'shortlist',
                                      )
                                    }
                                    disabled={updatingDecisionId === p._id}
                                    className={`px-2 py-1 text-xs font-medium rounded ${
                                      p?.review?.decision === 'shortlist'
                                        ? 'bg-green-100 text-green-800'
                                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                    } disabled:opacity-50`}
                                    title="Toggle shortlist"
                                  >
                                    Shortlist
                                  </button>
                                  <button
                                    onClick={() =>
                                      setProposalDecision(
                                        p._id,
                                        p?.review?.decision === 'reject'
                                          ? ''
                                          : 'reject',
                                      )
                                    }
                                    disabled={updatingDecisionId === p._id}
                                    className={`px-2 py-1 text-xs font-medium rounded ${
                                      p?.review?.decision === 'reject'
                                        ? 'bg-red-100 text-red-800'
                                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                    } disabled:opacity-50`}
                                    title="Toggle reject"
                                  >
                                    Reject
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <Section sid="raw" title="Raw / extracted text">
                <SectionAiSummaryCard sid="raw" />
                <div className="text-xs text-gray-600">
                  This is what the system extracted from the PDF / AI workflow.
                </div>
                <div className="mt-3">
                  <pre className="whitespace-pre-wrap text-xs bg-gray-50 border border-gray-200 rounded-lg p-3 max-h-[420px] overflow-auto">
                    {String((rfp as any)?.rawText || '').slice(0, 200000) ||
                      '(No raw text available)'}
                  </pre>
                </div>
                {(rfp as any)?._analysis ? (
                  <div className="mt-3 text-xs text-gray-500">
                    <div className="font-semibold text-gray-700">
                      Analysis meta
                    </div>
                    <pre className="mt-1 whitespace-pre-wrap bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-auto">
                      {JSON.stringify((rfp as any)._analysis, null, 2)}
                    </pre>
                  </div>
                ) : null}
              </Section>
            </main>
          </div>
        </>
      ) : null}

      {/* AI Preview Modal */}
      <BidGenerateProposalModal
        isOpen={showBidGenerateModal}
        onClose={() => setShowBidGenerateModal(false)}
        rfpId={rfp._id}
        rfpTitle={String(rfp.title || '')}
        rfpProjectType={String((rfp as any)?.projectType || '')}
        defaultCompanyId={selectedCompanyId}
        onGenerated={(proposalId) => {
          setShowBidGenerateModal(false)
          router.push(`/proposals/${proposalId}`)
        }}
      />

      <AIPreviewModal
        isOpen={showAIPreviewModal}
        onClose={() => setShowAIPreviewModal(false)}
        onGenerate={handleAIGenerate}
        isLoading={generatingAI}
        rfpId={rfp._id}
      />

      {/* Attachment Upload Modal */}
      <AttachmentUploadModal
        isOpen={showAttachmentModal}
        onClose={() => setShowAttachmentModal(false)}
        onUpload={handleAttachmentUpload}
        rfpId={rfp._id}
      />

      {/* Confirm Delete Modal */}
      <ConfirmDeleteModal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false)
          setAttachmentToDelete(null)
        }}
        onConfirm={confirmDeleteAttachment}
        title="Delete Attachment"
        message={`Are you sure you want to delete "${attachmentToDelete?.name}"? This action cannot be undone.`}
        isDeleting={isDeleting}
      />
    </div>
  )
}
