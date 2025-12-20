'use client'

import type { Proposal, RFP, WorkflowTask } from '@/lib/api'
import { extractList, proposalApi, rfpApi, tasksApi } from '@/lib/api'
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
import { useTranslations } from 'next-intl'
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

const STAGE_DEFS: {
  id: PipelineStage
  labelKey: string
  helpKey: string
}[] = [
  {
    id: 'BidDecision',
    labelKey: 'pipeline.stages.BidDecision.label',
    helpKey: 'pipeline.stages.BidDecision.help',
  },
  {
    id: 'ProposalDraft',
    labelKey: 'pipeline.stages.ProposalDraft.label',
    helpKey: 'pipeline.stages.ProposalDraft.help',
  },
  {
    id: 'ReviewRebuttal',
    labelKey: 'pipeline.stages.ReviewRebuttal.label',
    helpKey: 'pipeline.stages.ReviewRebuttal.help',
  },
  {
    id: 'Rework',
    labelKey: 'pipeline.stages.Rework.label',
    helpKey: 'pipeline.stages.Rework.help',
  },
  {
    id: 'ReadyToSubmit',
    labelKey: 'pipeline.stages.ReadyToSubmit.label',
    helpKey: 'pipeline.stages.ReadyToSubmit.help',
  },
  {
    id: 'Submitted',
    labelKey: 'pipeline.stages.Submitted.label',
    helpKey: 'pipeline.stages.Submitted.help',
  },
  {
    id: 'NoBid',
    labelKey: 'pipeline.stages.NoBid.label',
    helpKey: 'pipeline.stages.NoBid.help',
  },
  {
    id: 'Disqualified',
    labelKey: 'pipeline.stages.Disqualified.label',
    helpKey: 'pipeline.stages.Disqualified.help',
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

export default function PipelinePage() {
  const t = useTranslations()
  const [rfps, setRfps] = useState<RFP[]>([])
  const [proposals, setProposals] = useState<Proposal[]>([])
  const [tasksByRfp, setTasksByRfp] = useState<Record<string, WorkflowTask[]>>(
    {},
  )
  const [meSub, setMeSub] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const stages = useMemo(
    () =>
      STAGE_DEFS.map((s) => ({
        id: s.id,
        label: t(s.labelKey),
        help: t(s.helpKey),
      })),
    [t],
  )

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [rResp, pResp, meResp] = await Promise.all([
          rfpApi.list(),
          proposalApi.list(),
          fetch('/api/session/me', { method: 'GET' }).catch(() => null),
        ])
        const rList = extractList<RFP>(rResp)
        setRfps(rList)
        setProposals(extractList<Proposal>(pResp))

        // Current user (for "assign to me" UX)
        try {
          const meJson = await meResp?.json?.().catch(() => null)
          const sub = String(meJson?.sub || '').trim()
          if (sub) setMeSub(sub)
        } catch {
          // ignore
        }

        // Best-effort: prefetch tasks for the first N RFPs to keep the pipeline snappy.
        try {
          const ids = rList.map((r) => String(r?._id || '')).filter(Boolean)
          const slice = ids.slice(0, 50)
          const results: Array<[string, WorkflowTask[]]> = await Promise.all(
            slice.map(async (rid): Promise<[string, WorkflowTask[]]> => {
              try {
                const resp = await tasksApi.listForRfp(rid)
                return [rid, extractList<WorkflowTask>(resp)]
              } catch {
                return [rid, [] as WorkflowTask[]]
              }
            }),
          )
          const next: Record<string, WorkflowTask[]> = {}
          results.forEach(([rid, tasks]) => {
            next[rid] = tasks
          })
          setTasksByRfp(next)
        } catch {
          // ignore
        }
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [])

  const openTasks = (rfpId: string): WorkflowTask[] => {
    const tasks = tasksByRfp[String(rfpId || '')] || []
    return tasks
      .filter((x) => String(x?.status || '') === 'open')
      .sort((a, b) => {
        const ad = a?.dueAt
          ? new Date(a.dueAt).getTime()
          : Number.POSITIVE_INFINITY
        const bd = b?.dueAt
          ? new Date(b.dueAt).getTime()
          : Number.POSITIVE_INFINITY
        if (ad !== bd) return ad - bd
        return (
          new Date(String(a?.createdAt || '')).getTime() -
          new Date(String(b?.createdAt || '')).getTime()
        )
      })
  }

  const refreshTasksForRfp = async (rfpId: string) => {
    const rid = String(rfpId || '').trim()
    if (!rid) return
    const resp = await tasksApi.listForRfp(rid)
    const list = extractList<WorkflowTask>(resp)
    setTasksByRfp((prev) => ({ ...prev, [rid]: list }))
  }

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
      Object.fromEntries(stages.map((s) => [s.id, []])) as any
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
  }, [filteredRfps, proposalsByRfp, stages])

  const deadlineMeta = (
    rfp: RFP,
  ): { daysUntil: number | null; tone: 'ok' | 'warn' | 'bad' } => {
    const dueRaw = rfp.submissionDeadline
    if (!dueRaw) return { daysUntil: null, tone: 'warn' }
    const due = new Date(dueRaw)
    if (Number.isNaN(due.getTime())) return { daysUntil: null, tone: 'warn' }
    const daysUntil = Math.ceil(
      (due.getTime() - Date.now()) / (1000 * 60 * 60 * 24),
    )
    if (daysUntil < 0) return { daysUntil, tone: 'bad' }
    if (daysUntil <= 7) return { daysUntil, tone: 'warn' }
    return { daysUntil, tone: 'ok' }
  }

  const dueLabel = (daysUntil: number | null) => {
    const val =
      daysUntil === null
        ? t('pipeline.dueUnknown')
        : t('pipeline.dueDays', { days: daysUntil })
    return `${t('pipeline.due')}: ${val}`
  }

  const nextAction = (
    rfp: RFP,
    proposalsForRfp: Proposal[],
  ): { label: string; href: string } => {
    const decision = String((rfp as any)?.review?.decision || '')
      .trim()
      .toLowerCase()

    if (rfp.isDisqualified)
      return { label: t('pipeline.actions.viewRfp'), href: `/rfps/${rfp._id}` }
    if (decision !== 'bid')
      return {
        label: t('pipeline.actions.reviewRfp'),
        href: `/rfps/${rfp._id}`,
      }
    if (!proposalsForRfp || proposalsForRfp.length === 0)
      return {
        label: t('pipeline.actions.generateProposal'),
        href: `/rfps/${rfp._id}#generate`,
      }

    const p = [...proposalsForRfp].sort(
      (a, b) =>
        new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    )[0]
    return {
      label: t('pipeline.actions.openProposal'),
      href: `/proposals/${p._id}`,
    }
  }

  const nextStepHint = (
    stage: PipelineStage,
    proposalsForRfp: Proposal[],
  ): string => {
    if (stage === 'Disqualified') return t('pipeline.hints.disqualified')
    if (stage === 'NoBid') return t('pipeline.hints.noBid')
    if (stage === 'BidDecision') return t('pipeline.hints.bidDecision')
    if (stage === 'ProposalDraft') {
      if (!proposalsForRfp || proposalsForRfp.length === 0)
        return t('pipeline.hints.proposalDraftFirst')
      return t('pipeline.hints.proposalDraftContinue')
    }
    if (stage === 'ReviewRebuttal') return t('pipeline.hints.reviewRebuttal')
    if (stage === 'Rework') return t('pipeline.hints.rework')
    if (stage === 'ReadyToSubmit') return t('pipeline.hints.readyToSubmit')
    if (stage === 'Submitted') return t('pipeline.hints.submitted')
    return t('pipeline.hints.bidDecision')
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <h1 className="text-3xl font-bold text-gray-900">
              {t('pipeline.title')}
            </h1>
            <p className="mt-1 text-sm text-gray-600">
              {t('pipeline.subtitle')}
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <PlusIcon className="h-4 w-4" aria-hidden="true" />
                {t('pipeline.workflow.intake')}
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <CheckCircleIcon className="h-4 w-4" aria-hidden="true" />
                {t('pipeline.workflow.bidDecision')}
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <DocumentTextIcon className="h-4 w-4" aria-hidden="true" />
                {t('pipeline.workflow.draft')}
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <ExclamationTriangleIcon
                  className="h-4 w-4"
                  aria-hidden="true"
                />
                {t('pipeline.workflow.review')}
              </span>
              <span className="text-gray-300">→</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-gray-700">
                <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
                {t('pipeline.workflow.submit')}
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative w-full sm:w-80">
              <MagnifyingGlassIcon
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
                aria-hidden="true"
              />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('pipeline.searchPlaceholder')}
                aria-label={t('pipeline.searchPlaceholder')}
                className="w-full border border-gray-300 rounded-md pl-9 pr-3 py-2 bg-white text-sm"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href="/rfps/upload"
                className="w-full sm:w-auto inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
              >
                {t('pipeline.uploadRfp')}
              </Link>
              <Link
                href="/finder"
                className="w-full sm:w-auto inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-gray-900 bg-gray-100 hover:bg-gray-200"
              >
                {t('pipeline.finder')}
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stages.map((s) => (
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
                  <div className="text-xs text-gray-500">
                    {t('pipeline.emptyStage')}
                  </div>
                ) : (
                  byStage[s.id].map(({ rfp, proposals }) => {
                    const fit =
                      typeof (rfp as any)?.fitScore === 'number'
                        ? (rfp as any).fitScore
                        : null
                    const due = deadlineMeta(rfp)
                    const action = nextAction(rfp, proposals)
                    const hint = nextStepHint(s.id, proposals)
                    const open = openTasks(rfp._id)

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
                            {dueLabel(due.daysUntil)}
                          </span>
                          {fit !== null ? (
                            <span className="px-2 py-1 rounded-full text-[11px] border border-slate-200 bg-slate-50 text-slate-800">
                              {t('pipeline.fit')} {fit}
                            </span>
                          ) : (
                            <span className="px-2 py-1 rounded-full text-[11px] border border-slate-200 bg-slate-50 text-slate-700">
                              {t('pipeline.fit')} {t('pipeline.fitNone')}
                            </span>
                          )}
                          <span className="px-2 py-1 rounded-full text-[11px] border border-gray-200 bg-gray-50 text-gray-800">
                            {rfp.projectType?.replace('_', ' ') || '—'}
                          </span>
                        </div>

                        <div className="mt-2 text-[11px] text-gray-600 line-clamp-2">
                          <span className="font-semibold text-gray-700">
                            {t('pipeline.next')}
                          </span>{' '}
                          {hint}
                        </div>

                        {/* Workflow tasks */}
                        <div className="mt-2">
                          {open.length > 0 ? (
                            <div className="space-y-1">
                              {open.slice(0, 3).map((task) => (
                                <div
                                  key={task._id}
                                  className="flex items-center justify-between gap-2 rounded border border-gray-200 bg-gray-50 px-2 py-1"
                                >
                                  <div className="min-w-0">
                                    <div className="text-[11px] font-medium text-gray-900 truncate">
                                      {task.title}
                                    </div>
                                    <div className="text-[10px] text-gray-600 truncate">
                                      {task.assigneeDisplayName ||
                                        task.assigneeUserSub ||
                                        'Unassigned'}
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    {meSub &&
                                    String(task.assigneeUserSub || '') !==
                                      meSub ? (
                                      <button
                                        type="button"
                                        onClick={async () => {
                                          try {
                                            await tasksApi.assign(task._id, {
                                              assigneeUserSub: 'me',
                                            })
                                            await refreshTasksForRfp(rfp._id)
                                          } catch {
                                            // ignore
                                          }
                                        }}
                                        className="text-[10px] px-2 py-1 rounded bg-white border border-gray-200 hover:bg-gray-100"
                                      >
                                        Assign me
                                      </button>
                                    ) : null}
                                    <button
                                      type="button"
                                      onClick={async () => {
                                        try {
                                          await tasksApi.complete(task._id)
                                          await refreshTasksForRfp(rfp._id)
                                        } catch {
                                          // ignore
                                        }
                                      }}
                                      className="text-[10px] px-2 py-1 rounded bg-white border border-gray-200 hover:bg-gray-100"
                                    >
                                      Done
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-[11px] text-gray-500">
                                No open tasks
                              </div>
                              <button
                                type="button"
                                onClick={async () => {
                                  try {
                                    await tasksApi.seedForRfp(rfp._id)
                                    await refreshTasksForRfp(rfp._id)
                                  } catch {
                                    // ignore
                                  }
                                }}
                                className="text-[10px] px-2 py-1 rounded bg-white border border-gray-200 hover:bg-gray-100"
                              >
                                Seed tasks
                              </button>
                            </div>
                          )}
                        </div>

                        <div className="mt-2 flex items-center justify-between">
                          <div className="text-[11px] text-gray-500 flex items-center gap-1">
                            <DocumentTextIcon
                              className="h-4 w-4"
                              aria-hidden="true"
                            />
                            <span>
                              {t('pipeline.proposalCount', {
                                count: proposals.length,
                              })}
                            </span>
                            {Array.isArray(rfp.dateWarnings) &&
                            rfp.dateWarnings.length > 0 ? (
                              <span
                                className="inline-flex items-center gap-1 text-amber-700"
                                title={rfp.dateWarnings.slice(0, 6).join('\n')}
                              >
                                <ExclamationTriangleIcon
                                  className="h-4 w-4"
                                  aria-hidden="true"
                                />
                                <span>{rfp.dateWarnings.length}</span>
                              </span>
                            ) : null}
                          </div>
                          <Link
                            href={action.href}
                            className="inline-flex items-center gap-1 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 px-2.5 py-1.5 rounded-md"
                          >
                            {action.label}
                            <ArrowRightIcon
                              className="h-4 w-4"
                              aria-hidden="true"
                            />
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
