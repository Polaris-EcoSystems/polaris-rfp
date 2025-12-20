/* eslint-disable @next/next/no-img-element */
'use client'

import { useEffect, useMemo, useState } from 'react'

import api, { proxyUrl } from '@/lib/api'

type AuditEventsResp = {
  ok: boolean
  since: string
  count: number
  data: Array<any>
}

type AuditChangePropsResp = {
  ok: boolean
  data: Array<any>
}

export default function NorthStarPage() {
  const [events, setEvents] = useState<AuditEventsResp | null>(null)
  const [cps, setCps] = useState<AuditChangePropsResp | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const eventsByType = useMemo(() => {
    const out: Record<string, number> = {}
    for (const e of events?.data ?? []) {
      const t = String(e?.type ?? 'event')
      out[t] = (out[t] ?? 0) + 1
    }
    return Object.entries(out)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
  }, [events])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setErr(null)
        const [ev, cp] = await Promise.all([
          api.get(
            proxyUrl('/api/northstar/audit/events/recent?hours=24&limit=200'),
          ),
          api.get(
            proxyUrl('/api/northstar/audit/change-proposals/recent?limit=50'),
          ),
        ])
        if (cancelled) return
        setEvents(ev.data)
        setCps(cp.data)
      } catch (e: any) {
        if (cancelled) return
        setErr(e?.message ?? 'Failed to load North Star audit data')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">North Star</h1>
          <p className="text-sm text-muted-foreground">
            Audit view: last 24h events, recent change proposals.
          </p>
        </div>
      </div>

      {err ? (
        <div className="mt-6 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {err}
        </div>
      ) : null}

      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="rounded border p-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-medium">Agent events (24h)</h2>
            <div className="text-xs text-muted-foreground">
              {events?.count ?? '…'} total
            </div>
          </div>
          <div className="mt-3 text-xs text-muted-foreground">
            since: {events?.since ?? '…'}
          </div>
          <ul className="mt-4 space-y-1 text-sm">
            {eventsByType.length ? (
              eventsByType.map(([t, n]) => (
                <li key={t} className="flex justify-between">
                  <span className="font-mono">{t}</span>
                  <span className="text-muted-foreground">{n}</span>
                </li>
              ))
            ) : (
              <li className="text-muted-foreground">
                No recent events (or index not yet populated).
              </li>
            )}
          </ul>
        </div>

        <div className="rounded border p-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-medium">Change proposals</h2>
            <div className="text-xs text-muted-foreground">
              {cps?.data?.length ?? '…'}
            </div>
          </div>
          <ul className="mt-4 space-y-2 text-sm">
            {(cps?.data ?? []).slice(0, 12).map((cp: any) => {
              const id = String(cp?.proposalId ?? cp?._id ?? '')
              const title = String(cp?.title ?? 'Change proposal')
              const status = String(cp?.status ?? '')
              const pr = String(cp?.prUrl ?? '')
              return (
                <li key={id} className="rounded bg-muted/20 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate font-medium">{title}</div>
                    <div className="shrink-0 rounded bg-muted px-2 py-0.5 text-xs">
                      {status}
                    </div>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <div className="font-mono text-xs text-muted-foreground">
                      {id}
                    </div>
                    {pr ? (
                      <a
                        className="text-xs underline"
                        href={pr}
                        target="_blank"
                        rel="noreferrer"
                      >
                        PR
                      </a>
                    ) : null}
                  </div>
                </li>
              )
            })}
            {!cps?.data?.length ? (
              <li className="text-muted-foreground">
                No change proposals found.
              </li>
            ) : null}
          </ul>
        </div>
      </div>
    </div>
  )
}
