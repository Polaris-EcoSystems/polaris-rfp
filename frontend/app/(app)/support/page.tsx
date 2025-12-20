'use client'

import api, { aiJobsApi, proxyUrl } from '@/lib/api'
import { useEffect, useMemo, useState } from 'react'

type Job = {
  jobId?: string
  jobType?: string
  status?: string
  createdAt?: string
  updatedAt?: string
  startedAt?: string
  finishedAt?: string
  error?: string
  payload?: any
  result?: any
}

export default function SupportPage() {
  const [lastRequestId, setLastRequestId] = useState<string>('')
  const [lastRequestIdAt, setLastRequestIdAt] = useState<number | null>(null)

  const [jobId, setJobId] = useState<string>('')
  const [job, setJob] = useState<Job | null>(null)
  const [rfpJob, setRfpJob] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    try {
      const rid = window.localStorage.getItem('polaris:lastRequestId') || ''
      const atRaw = window.localStorage.getItem('polaris:lastRequestIdAt') || ''
      setLastRequestId(rid)
      setLastRequestIdAt(atRaw ? Number(atRaw) : null)
    } catch {
      // ignore
    }
  }, [])

  const lastAtText = useMemo(() => {
    if (!lastRequestIdAt || !Number.isFinite(lastRequestIdAt)) return ''
    try {
      return new Date(lastRequestIdAt).toLocaleString()
    } catch {
      return ''
    }
  }, [lastRequestIdAt])

  const copy = async (text: string) => {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // ignore
    }
  }

  const lookupAiJob = async () => {
    const id = jobId.trim()
    if (!id) return
    setLoading(true)
    setError('')
    try {
      const resp = await aiJobsApi.get(id)
      setJob(resp.data?.job ?? null)
    } catch (e: any) {
      setJob(null)
      setError(
        e?.response?.data?.detail ||
          e?.response?.data?.error ||
          e?.message ||
          'Failed to fetch AI job',
      )
    } finally {
      setLoading(false)
    }
  }

  const lookupRfpUploadJob = async () => {
    const id = jobId.trim()
    if (!id) return
    setLoading(true)
    setError('')
    try {
      const resp = await api.get(
        proxyUrl(`/api/rfp/upload/jobs/${encodeURIComponent(id)}`),
      )
      setRfpJob(resp.data?.job ?? resp.data ?? null)
    } catch (e: any) {
      setRfpJob(null)
      setError(
        e?.response?.data?.detail ||
          e?.response?.data?.error ||
          e?.message ||
          'Failed to fetch RFP upload job',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900">Support</h1>
      <p className="mt-2 text-sm text-gray-600">
        If you contact support, include the reference ID shown below. It helps
        us find the corresponding server logs quickly.
      </p>

      <div className="mt-4 rounded-lg border bg-white p-4">
        <div className="text-sm font-medium text-gray-900">
          Last incident reference
        </div>
        <div className="mt-2 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-mono text-sm break-all">
              {lastRequestId || (
                <span className="text-gray-500">
                  No reference captured yet.
                </span>
              )}
            </div>
            {lastAtText ? (
              <div className="mt-1 text-xs text-gray-500">
                Captured: {lastAtText}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            className="text-sm underline disabled:opacity-50"
            disabled={!lastRequestId}
            onClick={() => void copy(lastRequestId)}
          >
            Copy
          </button>
        </div>
      </div>

      <div className="mt-6 rounded-lg border bg-white p-4">
        <div className="text-sm font-medium text-gray-900">Job lookup</div>
        <p className="mt-1 text-xs text-gray-600">
          Use this to check background job status (e.g. AI section generation,
          RFP upload analysis).
        </p>

        <div className="mt-3 flex flex-col sm:flex-row gap-2">
          <input
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            placeholder="Enter job id…"
            className="flex-1 rounded-md border px-3 py-2 text-sm"
          />
          <button
            type="button"
            className="rounded-md bg-gray-900 text-white px-3 py-2 text-sm disabled:opacity-60"
            disabled={loading || !jobId.trim()}
            onClick={() => void lookupAiJob()}
          >
            Lookup AI job
          </button>
          <button
            type="button"
            className="rounded-md bg-gray-200 text-gray-900 px-3 py-2 text-sm disabled:opacity-60"
            disabled={loading || !jobId.trim()}
            onClick={() => void lookupRfpUploadJob()}
          >
            Lookup RFP upload job
          </button>
        </div>

        {error ? (
          <div className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-3">
            {error}
          </div>
        ) : null}

        {job ? (
          <pre className="mt-3 text-xs bg-gray-50 border rounded-md p-3 overflow-auto">
            {JSON.stringify(job, null, 2)}
          </pre>
        ) : null}

        {rfpJob ? (
          <pre className="mt-3 text-xs bg-gray-50 border rounded-md p-3 overflow-auto">
            {JSON.stringify(rfpJob, null, 2)}
          </pre>
        ) : null}
      </div>
    </div>
  )
}
