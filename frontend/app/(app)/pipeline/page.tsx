'use client'

import type { Proposal, RFP } from '@/lib/api'
import { extractList, proposalApi, rfpApi } from '@/lib/api'
import {
  ArrowRightIcon,
  CheckCircleIcon,
  ClockIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

type PipelineStage =
  | 'BidDecision'
  | 'ProposalDraft'
  | 'ReviewRebuttal'
  | 'Rework'
  | 'ReadyToSubmit'
  | 'Submitted'
  | 'NoBid'
  | 'Disqualified'

const STAGES: { id: PipelineStage; label: string; help: string }[] = [
  {
    id: 'BidDecision',
    label: 'Bid decision',
    help: 'Decide bid/no-bid and capture blockers.',
  },
  {
    id: 'ProposalDraft',
    label: 'Draft',
    help: 'Generate a proposal and fill missing sections.',
  },
  {
    id: 'ReviewRebuttal',
    label: 'Review / rebuttal',
    help: 'Run compliance review and plan fixes.',
  },
  {
    id: 'Rework',
    label: 'Rework',
    help: 'Address review items and update the draft.',
  },
  {
    id: 'ReadyToSubmit',
    label: 'Ready to submit',
    help: 'Finalize checklist and prepare exports.',
  },
  {
    id: 'Submitted',
    label: 'Submitted',
    help: 'Record outcome and keep artifacts.',
  },
  {
    id: 'NoBid',
    label: 'No-bid',
    help: 'Archive with decision notes for later learning.',
  },
  {
    id: 'Disqualified',
    label: 'Disqualified',
    help: 'Past due or invalid—keep for history.',
  },
]

function getStage(rfp: RFP, proposals: Proposal[]): PipelineStage {
  if (rfp.isDisqualified) return 'Disqualified'
  const decision = String((rfp as any)?.review?.decision || '')
    .trim()
    .toLowerCase()

  if (decision === 'no_bid') return 'NoBid'
  if (decision !== 'bid') return 'BidDecision'

  if (!proposals || proposals.length === 0) return 'ProposalDraft'

  // Choose the most recently updated proposal as the driver for stage.
  const p = [...proposals].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  )[0]
  const status = String(p?.status || '')
    .trim()
    .toLowerCase()

  if (status === 'submitted') return 'Submitted'
  if (status === 'ready_to_submit') return 'ReadyToSubmit'
  if (status === 'rework' || status === 'needs_changes') return 'Rework'
  if (status === 'in_review') return 'ReviewRebuttal'
  return 'ProposalDraft'
}

function deadlineMeta(rfp: RFP): {
  label: string
  tone: 'ok' | 'warn' | 'bad'
} {
  const dueRaw = rfp.submissionDeadline
  if (!dueRaw) return { label: 'Due: —', tone: 'warn' }
  const due = new Date(dueRaw)
  if (Number.isNaN(due.getTime())) return { label: 'Due: —', tone: 'warn' }
  const days = Math.ceil((due.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
  if (days < 0) return { label: `Due: ${days}d`, tone: 'bad' }
  if (days <= 7) return { label: `Due: ${days}d`, tone: 'warn' }
  return { label: `Due: ${days}d`, tone: 'ok' }
}

function nextAction(
  rfp: RFP,
  proposals: Proposal[],
): { label: string; href: string } {
  const decision = String((rfp as any)?.review?.decision || '')
    .trim()
    .toLowerCase()

  if (rfp.isDisqualified) return { label: 'View RFP', href: `/rfps/${rfp._id}` }
  if (decision !== 'bid')
    return { label: 'Review RFP', href: `/rfps/${rfp._id}` }
  if (!proposals || proposals.length === 0)
    return { label: 'Generate proposal', href: `/rfps/${rfp._id}#generate` }

  const p = [...proposals].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  )[0]
  return { label: 'Open proposal', href: `/proposals/${p._id}` }
}

function nextStepHint(
  stage: PipelineStage,
  rfp: RFP,
  proposals: Proposal[],
): string {
  if (stage === 'Disqualified')
    return 'Review deadlines and archive for history.'
  if (stage === 'NoBid') return 'Capture no-bid reason(s) for future learning.'
  if (stage === 'BidDecision') return 'Decide bid/no-bid and note blockers.'
  if (stage === 'ProposalDraft') {
    if (!proposals || proposals.length === 0) return 'Generate the first draft.'
    return 'Fill missing sections; get to “in review”.'
  }
  if (stage === 'ReviewRebuttal')
    return 'Review requirements; add rebuttals/actions.'
  if (stage === 'Rework') return 'Resolve review items and update draft.'
  if (stage === 'ReadyToSubmit') return 'Finalize checklist and export.'
  if (stage === 'Submitted') return 'Record outcome and attach final artifacts.'
  // fallback (shouldn’t happen)
  return `Continue: ${rfp.title || 'RFP'}`
}

export default function PipelinePage() {
  const [rfps, setRfps] = useState<RFP[]>([])
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [rResp, pResp] = await Promise.all([
          rfpApi.list(),
          proposalApi.list(),
        ])
        setRfps(extractList<RFP>(rResp))
        setProposals(extractList<Proposal>(pResp))
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  const proposalsByRfp = useMemo(() => {
    const out: Record<string, Proposal[]> = {}
    proposals.forEach((p) => {
      const rid = String(p.rfpId || '').trim()
      if (!rid) return
      out[rid] = out[rid] || []
      out[rid].push(p)
    })
    return out
  }, [proposals])

  const filteredRfps = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rfps
    return rfps.filter((r) => {
      const t = String(r.title || '').toLowerCase()
      const c = String(r.clientName || '').toLowerCase()
      return t.includes(q) || c.includes(q)
    })
  }, [rfps, search])

  const byStage = useMemo(() => {
    const out: Record<PipelineStage, { rfp: RFP; proposals: Proposal[] }[]> =
      Object.fromEntries(STAGES.map((s) => [s.id, []])) as any
    filteredRfps.forEach((rfp) => {
      const ps = proposalsByRfp[rfp._id] || []
      const stage = getStage(rfp, ps)
      out[stage].push({ rfp, proposals: ps })
    })
    // Sort within stage by soonest deadline (then newest)
    ;(Object.keys(out) as PipelineStage[]).forEach((k) => {
      out[k].sort((a, b) => {
        const ad = a.rfp.submissionDeadline
          ? new Date(a.rfp.submissionDeadline).getTime()
          : Number.POSITIVE_INFINITY
        const bd = b.rfp.submissionDeadline
          ? new Date(b.rfp.submissionDeadline).getTime()
          : Number.POSITIVE_INFINITY
        if (ad !== bd) return ad - bd
        return (
          new Date(b.rfp.createdAt).getTime() -
          new Date(a.rfp.createdAt).getTime()
        )
      })
    })
    return out
  }, [filteredRfps, proposalsByRfp])

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold text-gray-900">Pipeline</h1>
            <p className="mt-1 text-sm text-gray-600">
              Your primary workflow: intake → bid decision → draft → review →
              submit.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <PlusIcon className="h-4 w-4" />
                Intake
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <CheckCircleIcon className="h-4 w-4" />
                Bid decision
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <DocumentTextIcon className="h-4 w-4" />
                Draft
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <ExclamationTriangleIcon className="h-4 w-4" />
                Review
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <ArrowRightIcon className="h-4 w-4" />
                Submit
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-80">
              <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by title or client…"
                className="w-full border border-gray-300 rounded-md pl-9 pr-3 py-2 bg-white text-sm"
              />
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="/rfps/upload"
                className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
              >
                Upload RFP
              </Link>
              <Link
                href="/finder"
                className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-gray-900 bg-gray-100 hover:bg-gray-200"
              >
                Finder
              </Link>
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600" />
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-4">
          {STAGES.map((s) => (
            <div
              key={s.id}
              className="rounded-xl border border-gray-200 bg-white shadow-sm"
            >
              <div className="px-4 py-3 border-b border-gray-100">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-gray-900">
                    {s.label}
                  </div>
                  <div className="text-xs text-gray-500">
                    {byStage[s.id].length}
                  </div>
                </div>
                <div className="mt-1 text-[11px] text-gray-500">{s.help}</div>
              </div>
              <div className="p-3 space-y-3 max-h-[72vh] overflow-auto">
                {byStage[s.id].length === 0 ? (
                  <div className="text-xs text-gray-500">No items.</div>
                ) : (
                  byStage[s.id].map(({ rfp, proposals }) => {
                    const fit =
                      typeof (rfp as any)?.fitScore === 'number'
                        ? (rfp as any).fitScore
                        : null
                    const due = deadlineMeta(rfp)
                    const action = nextAction(rfp, proposals)
                    const hint = nextStepHint(s.id, rfp, proposals)

                    const dueTone =
                      due.tone === 'bad'
                        ? 'text-red-700 bg-red-50 border-red-200'
                        : due.tone === 'warn'
                        ? 'text-amber-800 bg-amber-50 border-amber-200'
                        : 'text-green-800 bg-green-50 border-green-200'

                    return (
                      <div
                        key={rfp._id}
                        className="rounded-lg border border-gray-200 bg-white p-3 hover:shadow-md transition-shadow"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <Link
                            href={`/rfps/${rfp._id}`}
                            className="text-sm font-semibold text-gray-900 hover:text-primary-700 line-clamp-2"
                            title={rfp.title}
                          >
                            {rfp.title}
                          </Link>
                          {rfp.isDisqualified ? (
                            <XCircleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
                          ) : String(
                              (rfp as any)?.review?.decision || '',
                            ).toLowerCase() === 'bid' ? (
                            <CheckCircleIcon className="h-5 w-5 text-green-600 flex-shrink-0" />
                          ) : (
                            <ClockIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
                          )}
                        </div>

                        <div className="mt-1 text-xs text-gray-600">
                          <span className="font-medium">{rfp.clientName}</span>
                        </div>

                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span
                            className={`px-2 py-1 rounded-full text-[11px] border ${dueTone}`}
                          >
                            {due.label}
                          </span>
                          {fit !== null ? (
                            <span className="px-2 py-1 rounded-full text-[11px] border border-slate-200 bg-slate-50 text-slate-800">
                              Fit {fit}
                            </span>
                          ) : (
                            <span className="px-2 py-1 rounded-full text-[11px] border border-slate-200 bg-slate-50 text-slate-700">
                              Fit —
                            </span>
                          )}
                          <span className="px-2 py-1 rounded-full text-[11px] border border-gray-200 bg-gray-50 text-gray-800">
                            {rfp.projectType?.replace('_', ' ') || '—'}
                          </span>
                        </div>

                        <div className="mt-2 text-[11px] text-gray-600 line-clamp-2">
                          <span className="font-semibold text-gray-700">
                            Next:
                          </span>{' '}
                          {hint}
                        </div>

                        <div className="mt-2 flex items-center justify-between">
                          <div className="text-[11px] text-gray-500 flex items-center gap-1">
                            <DocumentTextIcon className="h-4 w-4" />
                            <span>
                              {proposals.length} proposal
                              {proposals.length === 1 ? '' : 's'}
                            </span>
                            {Array.isArray(rfp.dateWarnings) &&
                            rfp.dateWarnings.length > 0 ? (
                              <span
                                className="inline-flex items-center gap-1 text-amber-700"
                                title={rfp.dateWarnings.slice(0, 6).join('\n')}
                              >
                                <ExclamationTriangleIcon className="h-4 w-4" />
                                <span>{rfp.dateWarnings.length}</span>
                              </span>
                            ) : null}
                          </div>
                          <Link
                            href={action.href}
                            className="inline-flex items-center gap-1 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 px-2.5 py-1.5 rounded-md"
                          >
                            {action.label}
                            <ArrowRightIcon className="h-4 w-4" />
                          </Link>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

