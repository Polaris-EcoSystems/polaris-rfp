'use client'

import type { Proposal, RFP } from '@/lib/api'
import { extractList, proposalApi, rfpApi } from '@/lib/api'
import {
  ArrowRightIcon,
  CheckCircleIcon,
  ClockIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
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

const STAGES: { id: PipelineStage; label: string }[] = [
  { id: 'BidDecision', label: 'Bid decision' },
  { id: 'ProposalDraft', label: 'Draft' },
  { id: 'ReviewRebuttal', label: 'Review / rebuttal' },
  { id: 'Rework', label: 'Rework' },
  { id: 'ReadyToSubmit', label: 'Ready to submit' },
  { id: 'Submitted', label: 'Submitted' },
  { id: 'NoBid', label: 'No-bid' },
  { id: 'Disqualified', label: 'Disqualified' },
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Pipeline</h1>
          <p className="text-sm text-gray-600">
            A single view across bid decisions and proposal progress.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by title or client…"
            className="w-full sm:w-80 border border-gray-300 rounded-md px-3 py-2 bg-white text-sm"
          />
          <Link
            href="/rfps/upload"
            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
          >
            Upload RFP
          </Link>
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
              <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-900">
                  {s.label}
                </div>
                <div className="text-xs text-gray-500">
                  {byStage[s.id].length}
                </div>
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
                            className="inline-flex items-center gap-1 text-xs font-medium text-primary-700 hover:text-primary-900"
                          >
                            {action.label}{' '}
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
