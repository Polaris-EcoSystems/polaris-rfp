'use client'

import Button from '@/components/ui/Button'
import Card, { CardBody } from '@/components/ui/Card'
import PipelineContextBanner from '@/components/ui/PipelineContextBanner'
import StepsPanel from '@/components/ui/StepsPanel'
import {
  rfpApi,
  scraperApi,
  type RFP,
  type ScraperJob,
  type ScraperSource,
  type ScrapedCandidate,
  type ScraperIntakeItem,
  type ScraperSchedule,
} from '@/lib/api'
import {
  ArrowTopRightOnSquareIcon,
  CheckCircleIcon,
  ClockIcon,
  PlayIcon,
  PlusIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useEffect, useState } from 'react'

export default function FinderPage() {
  const [sources, setSources] = useState<ScraperSource[]>([])
  const [sourcesLoading, setSourcesLoading] = useState(true)
  const [showSourceDiagnostics, setShowSourceDiagnostics] = useState(false)
  const [runningJobs, setRunningJobs] = useState<Record<string, boolean>>({})
  const [jobs, setJobs] = useState<ScraperJob[]>([])
  const [candidates, setCandidates] = useState<ScrapedCandidate[]>([])
  const [intake, setIntake] = useState<ScraperIntakeItem[]>([])
  const [schedules, setSchedules] = useState<ScraperSchedule[]>([])
  const [activeTab, setActiveTab] = useState<'sources' | 'schedules' | 'jobs' | 'intake' | 'candidates'>('sources')
  const [urlsText, setUrlsText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  // Opportunity Tracker CSV import
  const [trackerDragOver, setTrackerDragOver] = useState(false)
  const [trackerImporting, setTrackerImporting] = useState(false)
  const [trackerImportError, setTrackerImportError] = useState<string | null>(null)
  const [trackerImportResult, setTrackerImportResult] = useState<{
    created: string[]
    updated: string[]
    stats: { rows: number; created: number; updated: number; errors: number }
    errors: { row: number; error: string; opportunity?: string }[]
  } | null>(null)

  // Custom source quick-run / schedule form
  const [customListingUrl, setCustomListingUrl] = useState('')
  const [customLinkPattern, setCustomLinkPattern] = useState('rfp')

  useEffect(() => {
    loadSources()
    loadSchedules()
    loadIntake()
  }, [])

  const loadSources = async (opts?: { refresh?: boolean; debug?: boolean }) => {
    try {
      setSourcesLoading(true)
      const resp = await scraperApi.listSources(opts)
      setSources(resp.data?.sources || [])
    } catch (e) {
      console.error('Failed to load sources:', e)
    } finally {
      setSourcesLoading(false)
    }
  }

  const loadSchedules = async () => {
      try {
      const resp = await scraperApi.listSchedules({ limit: 100 })
      setSchedules(resp.data?.schedules || [])
      } catch (e) {
      console.error('Failed to load schedules:', e)
    }
  }

  const loadIntake = async () => {
    try {
      const resp = await scraperApi.listIntake({ status: 'pending', limit: 100 })
      setIntake(resp.data?.items || [])
    } catch (e) {
      console.error('Failed to load intake queue:', e)
    }
  }

  const runScraper = async (sourceId: string, searchParams?: Record<string, any>) => {
    try {
      setRunningJobs((prev) => ({ ...prev, [sourceId]: true }))
      await scraperApi.run({ source: sourceId, searchParams })
      // Refresh jobs after a short delay
      setTimeout(() => {
        if (activeTab === 'jobs') {
          loadJobs(sourceId)
        }
      }, 1000)
    } catch (e: any) {
      alert(`Failed to run scraper: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`)
    } finally {
      setRunningJobs((prev) => ({ ...prev, [sourceId]: false }))
    }
  }

  const loadJobs = async (source?: string) => {
    if (!source && sources.length > 0) {
      // Load jobs for the first available source
      source = sources.find((s) => s.available && s.id !== 'custom')?.id
    }
    if (!source) return

    try {
      const resp = await scraperApi.listJobs({ source, limit: 20 })
      setJobs(resp.data?.jobs || [])
    } catch (e) {
      console.error('Failed to load jobs:', e)
    }
  }

  const loadCandidates = async (source?: string, status?: string) => {
    if (!source && sources.length > 0) {
      source = sources.find((s) => s.available && s.id !== 'custom')?.id
    }
    if (!source) return

    try {
      const resp = await scraperApi.listCandidates({ source, status, limit: 50 })
      setCandidates(resp.data?.candidates || [])
    } catch (e) {
      console.error('Failed to load candidates:', e)
    }
  }

  useEffect(() => {
    if (activeTab === 'jobs') {
      loadJobs()
    } else if (activeTab === 'schedules') {
      loadSchedules()
    } else if (activeTab === 'intake') {
      loadIntake()
    } else if (activeTab === 'candidates') {
      loadCandidates()
    }
  }, [activeTab, sources])

  const submit = async () => {
    const urls = urlsText
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)

    if (urls.length === 0) return
    setError(null)
    setIsSubmitting(true)
    try {
      const resp = await rfpApi.analyzeUrls(urls)
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

  const importCandidate = async (candidateId: string) => {
    try {
      const resp = await scraperApi.importCandidate(candidateId)
      if (resp.data?.rfp) {
        alert('Candidate imported successfully!')
        loadIntake()
        loadCandidates()
      }
    } catch (e: any) {
      alert(`Failed to import: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`)
    }
  }

  const skipCandidate = async (candidateId: string) => {
    try {
      await scraperApi.skipCandidate(candidateId)
      loadIntake()
      loadCandidates()
    } catch (e: any) {
      alert(`Failed to skip: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`)
    }
  }

  const createCustomDailySchedule = async () => {
    const listingUrl = customListingUrl.trim()
    if (!listingUrl) {
      alert('Listing URL is required')
      return
    }
    try {
      await scraperApi.createSchedule({
        name: `Custom: ${listingUrl}`,
        source: 'custom',
        frequency: 'daily',
        enabled: true,
        searchParams: {
          listingUrl,
          linkPattern: customLinkPattern.trim() || 'rfp',
          linkPatternIsRegex: false,
          linkSelector: 'a',
          maxCandidates: 50,
        },
      })
      await loadSchedules()
      alert('Daily schedule created')
    } catch (e: any) {
      alert(`Failed to create schedule: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`)
    }
  }

  const runCustomNow = async () => {
    const listingUrl = customListingUrl.trim()
    if (!listingUrl) {
      alert('Listing URL is required')
      return
    }
    await runScraper('custom', {
      listingUrl,
      linkPattern: customLinkPattern.trim() || 'rfp',
      linkPatternIsRegex: false,
      linkSelector: 'a',
      maxCandidates: 50,
    })
    loadIntake()
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-600" />
      case 'running':
        return <ClockIcon className="h-5 w-5 text-blue-600 animate-spin" />
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-600" />
      case 'queued':
        return <ClockIcon className="h-5 w-5 text-gray-400" />
      default:
        return null
    }
  }

  const getStatusBadge = (status: string) => {
    const baseClasses = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium'
    switch (status) {
      case 'completed':
        return <span className={`${baseClasses} bg-green-100 text-green-800`}>Completed</span>
      case 'running':
        return <span className={`${baseClasses} bg-blue-100 text-blue-800`}>Running</span>
      case 'failed':
        return <span className={`${baseClasses} bg-red-100 text-red-800`}>Failed</span>
      case 'queued':
        return <span className={`${baseClasses} bg-gray-100 text-gray-800`}>Queued</span>
      default:
        return <span className={`${baseClasses} bg-gray-100 text-gray-800`}>{status}</span>
    }
  }

  return (
    <div className="space-y-6">
      <PipelineContextBanner
        variant="tool"
        title="RFP Finder Dashboard"
        description="Automated scraping workflows to discover RFPs from various sources. Configure search queries, run scrapers, and review candidates."
        rightSlot={
          <Button as={Link} href="/rfps" variant="ghost" size="sm">
            View RFPs
          </Button>
        }
      />

      <div>
        <h1 className="text-3xl font-bold text-gray-900">RFP Finder</h1>
        <p className="mt-2 text-sm text-gray-600">
          Manage automated scraping workflows to discover and import RFPs.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {[
            { id: 'sources', label: 'Sources' },
            { id: 'schedules', label: 'Schedules' },
            { id: 'jobs', label: 'Recent Jobs' },
            { id: 'intake', label: 'Intake Queue' },
            { id: 'candidates', label: 'Candidates' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`
                whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm
                ${
                  activeTab === tab.id
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }
              `}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Sources Tab */}
      {activeTab === 'sources' && (
        <div className="space-y-6">
          <StepsPanel
            title="How it works"
            tone="blue"
            columns={3}
            steps={[
              { title: 'Configure Sources', description: 'Set up search queries and parameters for each source.' },
              { title: 'Run Scrapers', description: 'Execute daily scraping workflows automatically or manually.' },
              {
                title: 'Review & Import',
                description: 'Review scraped candidates and import promising RFPs.',
              },
            ]}
          />

          <div className="bg-white shadow rounded-lg p-6 space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Import Opportunity Tracker (CSV)
                </h2>
                <p className="mt-1 text-sm text-gray-600">
                  Drag and drop your <span className="font-medium">Opportunity Tracker - Ongoing Grants.csv</span> here to
                  populate the database. Imported items will show up under{' '}
                  <Link href="/rfps" className="text-primary-700 hover:underline">
                    RFPs
                  </Link>{' '}
                  and in each RFP’s <span className="font-medium">Tracker</span> section.
                </p>
              </div>
              <div className="shrink-0">
                <label className="inline-flex">
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    className="hidden"
                    onChange={async (e) => {
                      const f = e.target.files?.[0]
                      if (!f) return
                      setTrackerImportError(null)
                      setTrackerImportResult(null)
                      setTrackerImporting(true)
                      try {
                        const resp = await rfpApi.importOpportunityTracker(f)
                        setTrackerImportResult(resp.data)
                      } catch (err: any) {
                        console.error('Tracker import failed:', err)
                        setTrackerImportError(
                          err?.response?.data?.detail ||
                            err?.message ||
                            'Failed to import CSV',
                        )
                      } finally {
                        setTrackerImporting(false)
                        // allow re-selecting same file
                        e.target.value = ''
                      }
                    }}
                  />
                  <Button disabled={trackerImporting}>
                    {trackerImporting ? 'Importing…' : 'Choose CSV'}
                  </Button>
                </label>
              </div>
            </div>

            <div
              onDragEnter={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setTrackerDragOver(true)
              }}
              onDragOver={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setTrackerDragOver(true)
              }}
              onDragLeave={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setTrackerDragOver(false)
              }}
              onDrop={async (e) => {
                e.preventDefault()
                e.stopPropagation()
                setTrackerDragOver(false)
                const f = e.dataTransfer?.files?.[0]
                if (!f) return
                if (!String(f.name || '').toLowerCase().endsWith('.csv')) {
                  setTrackerImportError('Please drop a .csv file.')
                  return
                }
                setTrackerImportError(null)
                setTrackerImportResult(null)
                setTrackerImporting(true)
                try {
                  const resp = await rfpApi.importOpportunityTracker(f)
                  setTrackerImportResult(resp.data)
                } catch (err: any) {
                  console.error('Tracker import failed:', err)
                  setTrackerImportError(
                    err?.response?.data?.detail || err?.message || 'Failed to import CSV',
                  )
                } finally {
                  setTrackerImporting(false)
                }
              }}
              className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                trackerDragOver
                  ? 'border-primary-400 bg-primary-50'
                  : 'border-gray-300 bg-gray-50'
              }`}
            >
              <div className="text-sm font-medium text-gray-900">
                Drop CSV file here
              </div>
              <div className="mt-1 text-xs text-gray-600">
                We’ll upsert rows (deduped) into RFPs + Tracker fields.
              </div>
            </div>

            {trackerImportError ? (
              <div className="text-sm text-red-700">{trackerImportError}</div>
            ) : null}

            {trackerImportResult ? (
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-gray-900">
                    Import complete
                  </div>
                  <Link
                    href="/rfps"
                    className="text-sm text-primary-700 hover:underline"
                  >
                    View RFPs
                  </Link>
                </div>
                <div className="mt-2 text-sm text-gray-700">
                  Rows: <span className="font-medium">{trackerImportResult.stats.rows}</span> • Created:{' '}
                  <span className="font-medium">{trackerImportResult.stats.created}</span> • Updated:{' '}
                  <span className="font-medium">{trackerImportResult.stats.updated}</span> • Errors:{' '}
                  <span className="font-medium">{trackerImportResult.stats.errors}</span>
                </div>
                {trackerImportResult.errors?.length ? (
                  <div className="mt-3">
                    <div className="text-xs font-semibold text-gray-700">
                      Errors (first {trackerImportResult.errors.length})
                    </div>
                    <ul className="mt-2 space-y-1 text-xs text-red-700">
                      {trackerImportResult.errors.slice(0, 10).map((e) => (
                        <li key={`${e.row}:${e.error}`}>
                          Row {e.row}: {e.opportunity ? `"${e.opportunity}" — ` : ''}
                          {e.error}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="bg-white shadow rounded-lg p-6 space-y-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  RFP Sources
                </h2>
                <p className="mt-1 text-sm text-gray-600">
                  Sources are loaded from the backend scraper registry. Only sources marked “Available” can be run.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-gray-700 select-none">
                  <input
                    type="checkbox"
                    checked={showSourceDiagnostics}
                    onChange={(e) => setShowSourceDiagnostics(e.target.checked)}
                    className="h-4 w-4"
                  />
                  Show diagnostics
                </label>
                <button
                  onClick={() => loadSources({ refresh: true, debug: showSourceDiagnostics })}
                  className="text-sm text-primary-600 hover:text-primary-800"
                >
                  Refresh
                </button>
              </div>
            </div>
            {sourcesLoading ? (
              <div className="flex items-center justify-center h-48">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600" />
              </div>
            ) : (
              <div className="space-y-6">
                <div>
                  <div className="text-xs font-semibold text-gray-700 mb-2">Available</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {sources
                      .filter((s) => s.available)
                      .map((source) => (
                        <Card key={source.id} hover className="">
                          <CardBody>
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                  <h3 className="font-semibold text-gray-900">
                                    {source.name}
                                  </h3>
                                  {source.requiresAuth && (
                                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                                      Auth Required
                                    </span>
                                  )}
                                  {source.kind && (
                                    <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                                      {String(source.kind).toUpperCase()}
                                    </span>
                                  )}
                                </div>
                                <p className="text-sm text-gray-600 mb-3">
                                  {source.description}
                                </p>
                                {showSourceDiagnostics && (source.unavailableReason || source.importError) ? (
                                  <div className="mb-3 text-xs text-gray-600 space-y-1">
                                    {source.unavailableReason ? (
                                      <div>
                                        <span className="font-semibold">Reason:</span>{' '}
                                        <span className="font-mono">{source.unavailableReason}</span>
                                      </div>
                                    ) : null}
                                    {source.importError ? (
                                      <div className="text-red-700">
                                        <span className="font-semibold">Import error:</span>{' '}
                                        <span className="font-mono break-words">{source.importError}</span>
                                      </div>
                                    ) : null}
                                  </div>
                                ) : null}
                                <button
                                  onClick={() => runScraper(source.id)}
                                  disabled={runningJobs[source.id]}
                                  className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  <PlayIcon className="h-4 w-4" />
                                  {runningJobs[source.id] ? 'Running...' : 'Run Scraper'}
                                </button>
                                {Boolean(source.baseUrl) && (
                                  <a
                                    href={source.baseUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="ml-3 text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    Open Site{' '}
                                    <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                                  </a>
                                )}
                              </div>
                            </div>
                          </CardBody>
                        </Card>
                      ))}
                  </div>
                </div>

                <div>
                  <div className="text-xs font-semibold text-gray-700 mb-2">Unavailable</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {sources
                      .filter((s) => !s.available)
                      .map((source) => (
                        <Card key={source.id} hover={false} className="opacity-60">
                          <CardBody>
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                  <h3 className="font-semibold text-gray-900">
                                    {source.name}
                                  </h3>
                                  <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                                    Unavailable
                                  </span>
                                  {source.requiresAuth && (
                                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                                      Auth Required
                                    </span>
                                  )}
                                  {source.kind && (
                                    <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                                      {String(source.kind).toUpperCase()}
                                    </span>
                                  )}
                                </div>
                                <p className="text-sm text-gray-600 mb-3">
                                  {source.description}
                                </p>
                                {showSourceDiagnostics && (source.unavailableReason || source.importError) ? (
                                  <div className="mb-3 text-xs text-gray-600 space-y-1">
                                    {source.unavailableReason ? (
                                      <div>
                                        <span className="font-semibold">Reason:</span>{' '}
                                        <span className="font-mono">{source.unavailableReason}</span>
                                      </div>
                                    ) : null}
                                    {source.importError ? (
                                      <div className="text-red-700">
                                        <span className="font-semibold">Import error:</span>{' '}
                                        <span className="font-mono break-words">{source.importError}</span>
                                      </div>
                                    ) : null}
                                  </div>
                                ) : null}
                                {Boolean(source.baseUrl) && (
                                  <a
                                    href={source.baseUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    Open Site{' '}
                                    <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                                  </a>
                                )}
                              </div>
                            </div>
                          </CardBody>
                        </Card>
                      ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Manual URL Analysis */}
          <div className="bg-white shadow rounded-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Analyze RFP URLs (Manual)
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
      )}

      {/* Schedules Tab */}
      {activeTab === 'schedules' && (
        <div className="space-y-6">
          <div className="bg-white shadow rounded-lg p-6 space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Daily schedules</h2>
              <p className="mt-1 text-sm text-gray-600">
                Schedules are executed by the backend scheduler worker (daily). You can also run any schedule manually.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-gray-700 mb-1">Custom listing URL</label>
                <input
                  value={customListingUrl}
                  onChange={(e) => setCustomListingUrl(e.target.value)}
                  placeholder="https://example.com/opportunities"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Link pattern (substring)</label>
                <input
                  value={customLinkPattern}
                  onChange={(e) => setCustomLinkPattern(e.target.value)}
                  placeholder="rfp"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={runCustomNow}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
              >
                <PlayIcon className="h-4 w-4" />
                Run Custom Now
              </button>
              <button
                onClick={createCustomDailySchedule}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white bg-gray-900 hover:bg-gray-800"
              >
                <PlusIcon className="h-4 w-4" />
                Create Daily Schedule
              </button>
              <button
                onClick={loadSchedules}
                className="text-sm text-primary-600 hover:text-primary-800"
              >
                Refresh
              </button>
            </div>
            </div>

          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-900">Configured schedules</h3>
              <button onClick={loadSchedules} className="text-sm text-primary-600 hover:text-primary-800">
                Refresh
              </button>
            </div>
            <div className="px-6 py-4">
              {schedules.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No schedules yet.</p>
              ) : (
                <div className="space-y-3">
                  {schedules.map((s) => (
                    <div key={s.scheduleId} className="p-4 border border-gray-200 rounded-lg flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <div className="font-medium text-gray-900 truncate">{s.name}</div>
                        <div className="text-xs text-gray-500">
                          Source: {s.source} · Next: {s.nextRunAt ? new Date(s.nextRunAt).toLocaleString() : '—'} · Enabled:{' '}
                          {s.enabled ? 'Yes' : 'No'}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={async () => {
                            await scraperApi.updateSchedule(s.scheduleId, { enabled: !s.enabled })
                            loadSchedules()
                          }}
                          className="px-3 py-1.5 text-sm rounded-md border border-gray-300 hover:bg-gray-50"
                        >
                          {s.enabled ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          onClick={async () => {
                            await scraperApi.runSchedule(s.scheduleId)
                            loadJobs(s.source)
                            loadIntake()
                          }}
                          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                        >
                          <PlayIcon className="h-4 w-4" />
                          Run
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Intake Queue Tab */}
      {activeTab === 'intake' && (
        <div className="space-y-6">
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Intake Queue</h2>
                <p className="mt-1 text-sm text-gray-600">
                  De-duplicated candidates from all sources. Import to create an RFP, or skip to remove from the queue.
                </p>
              </div>
              <button
                onClick={loadIntake}
                className="text-sm text-primary-600 hover:text-primary-800"
              >
                Refresh
              </button>
            </div>
            <div className="px-6 py-4">
              {intake.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No pending intake items.</p>
              ) : (
                <div className="space-y-3">
                  {intake.map((it) => (
                    <div
                      key={it.candidateId}
                      className="flex items-start justify-between p-4 border border-gray-200 rounded-lg"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-medium text-gray-900 truncate">{it.title}</h3>
                          {getStatusBadge(it.status)}
                        </div>
                        <div className="text-xs text-gray-500 mb-2">
                          Source: {it.source || '—'} · Added:{' '}
                          {it.createdAt ? new Date(it.createdAt).toLocaleString() : '—'}
                        </div>
                        {it.detailUrl && (
                          <a
                            href={it.detailUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                          >
                            View Original <ArrowTopRightOnSquareIcon className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                      <div className="ml-4 flex items-center gap-2">
                        <button
                          onClick={() => skipCandidate(it.candidateId)}
                          className="px-3 py-1.5 text-sm rounded-md border border-gray-300 hover:bg-gray-50"
                        >
                          Skip
                        </button>
                        <button
                          onClick={() => importCandidate(it.candidateId)}
                          className="inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                        >
                          Import
                    </button>
                  </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Jobs Tab */}
      {activeTab === 'jobs' && (
        <div className="space-y-6">
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    Recent Scraper Jobs
                  </h2>
                  <p className="mt-1 text-sm text-gray-600">
                    Track the status of scraping jobs across all sources.
                  </p>
                </div>
                <button
                  onClick={() => loadJobs()}
                  className="text-sm text-primary-600 hover:text-primary-800"
                >
                  Refresh
                </button>
              </div>
            </div>
            <div className="px-6 py-4">
              {jobs.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No jobs found. Run a scraper to see jobs here.</p>
              ) : (
                <div className="space-y-3">
                  {jobs.map((job) => (
                    <div
                      key={job.id}
                      className="flex items-center justify-between p-4 border border-gray-200 rounded-lg"
                    >
                      <div className="flex items-center gap-4 flex-1">
                        {getStatusIcon(job.status)}
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-900">{job.source}</span>
                            {getStatusBadge(job.status)}
                          </div>
                          {job.createdAt && (
                            <div className="text-xs text-gray-500 mt-1">
                              Started: {new Date(job.createdAt).toLocaleString()}
                            </div>
                          )}
                          {job.candidatesFound !== undefined && (
                            <div className="text-xs text-gray-600 mt-1">
                              Found {job.candidatesFound} candidates
                              {job.candidatesImported !== undefined &&
                                job.candidatesImported > 0 &&
                                `, imported ${job.candidatesImported}`}
                            </div>
                          )}
                          {job.error && (
                            <div className="text-xs text-red-600 mt-1">{job.error}</div>
                          )}
                        </div>
                      </div>
                      {job.status === 'completed' && (
                        <button
                          onClick={() => {
                            setActiveTab('candidates')
                            loadCandidates(job.source)
                          }}
                          className="text-sm text-primary-600 hover:text-primary-800"
                        >
                          View Candidates →
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Candidates Tab */}
      {activeTab === 'candidates' && (
        <div className="space-y-6">
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">
                    Scraped Candidates
                  </h2>
                  <p className="mt-1 text-sm text-gray-600">
                    Review and import scraped RFP candidates as full RFPs.
                  </p>
                </div>
                <button
                  onClick={() => loadCandidates()}
                  className="text-sm text-primary-600 hover:text-primary-800"
                >
                  Refresh
                </button>
              </div>
            </div>
            <div className="px-6 py-4">
              {candidates.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No candidates found. Run a scraper to see candidates here.</p>
              ) : (
                <div className="space-y-3">
                  {candidates.map((candidate) => (
                    <div
                      key={candidate._id}
                      className="flex items-start justify-between p-4 border border-gray-200 rounded-lg"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="font-medium text-gray-900">{candidate.title}</h3>
                          {getStatusBadge(candidate.status)}
                        </div>
                        <div className="text-xs text-gray-500 mb-2">
                          Source: {candidate.source}
                        </div>
                        {candidate.detailUrl && (
                          <a
                            href={candidate.detailUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                          >
                            View Original <ArrowTopRightOnSquareIcon className="w-3 h-3" />
                          </a>
                        )}
                        {candidate.importedRfpId && (
                          <div className="mt-2">
                            <Link
                              href={`/rfps/${candidate.importedRfpId}`}
                              className="text-xs text-primary-600 hover:text-primary-800"
                            >
                              View Imported RFP →
                            </Link>
                          </div>
                        )}
                      </div>
                      {candidate.status === 'pending' && (
                        <button
                          onClick={() => importCandidate(candidate._id)}
                          className="ml-4 inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                        >
                          Import
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
