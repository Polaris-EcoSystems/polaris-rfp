'use client'

import { rfpApi } from '@/lib/api'
import Link from 'next/link'
import { useState } from 'react'

export default function FinderPage() {
  const [urlsText, setUrlsText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    const urls = urlsText
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)

    if (urls.length === 0) return
    setError(null)
    setIsSubmitting(true)
    try {
      const resp = await (rfpApi as any).analyzeUrls(urls)
      setResults(resp.data?.results || [])
      setUrlsText('')
    } catch (e: any) {
      setError(
        e?.response?.data?.error || e?.message || 'Failed to analyze URLs',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Finder</h1>
        <p className="mt-2 text-sm text-gray-600">
          Paste multiple RFP URLs (one per line) to analyze and save them.
        </p>
      </div>

      <div className="bg-white shadow rounded-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Analyze RFP URLs
        </h2>
        <textarea
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
          rows={8}
          className="w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
          placeholder="https://example.com/rfp.pdf\nhttps://procurement.site.gov/opportunity/123"
        />
        <div className="flex items-center justify-end">
          <button
            onClick={submit}
            disabled={isSubmitting || urlsText.trim().length === 0}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
          >
            {isSubmitting ? 'Analyzing…' : 'Analyze URLs'}
          </button>
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
      </div>

      {results.length > 0 && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-5 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Results</h2>
          </div>
          <div className="px-6 py-4 space-y-3">
            {results.map((r, idx) => (
              <div
                key={idx}
                className={`p-3 rounded-md border ${
                  r.ok
                    ? 'border-green-200 bg-green-50'
                    : 'border-red-200 bg-red-50'
                }`}
              >
                <div className="text-xs text-gray-600 break-all">{r.url}</div>
                {r.ok ? (
                  <div className="mt-1 text-sm text-gray-900">
                    Saved: <span className="font-semibold">{r.rfp?.title}</span>
                    {r.rfp?._id && (
                      <div className="mt-1">
                        <Link
                          href={`/rfps/${r.rfp._id}`}
                          className="text-xs text-primary-600 hover:text-primary-800"
                        >
                          View RFP →
                        </Link>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="mt-1 text-sm text-red-700">{r.error}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
