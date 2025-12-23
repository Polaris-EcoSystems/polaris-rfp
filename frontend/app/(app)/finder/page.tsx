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
  const [googleQueries, setGoogleQueries] = useState<string[]>([])
  const [newQuery, setNewQuery] = useState('')
  const [runningJobs, setRunningJobs] = useState<Record<string, boolean>>({})
  const [jobs, setJobs] = useState<ScraperJob[]>([])
  const [candidates, setCandidates] = useState<ScrapedCandidate[]>([])
  const [activeTab, setActiveTab] = useState<'sources' | 'queries' | 'jobs' | 'candidates'>('sources')
  const [urlsText, setUrlsText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [results, setResults] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadSources()
    loadGoogleQueries()
  }, [])

  const loadSources = async () => {
    try {
      setSourcesLoading(true)
      const resp = await scraperApi.listSources()
      setSources(resp.data?.sources || [])
    } catch (e) {
      console.error('Failed to load sources:', e)
    } finally {
      setSourcesLoading(false)
    }
  }

  const loadGoogleQueries = () => {
    // Load from localStorage
    const stored = localStorage.getItem('google-rfp-queries')
    if (stored) {
      try {
        setGoogleQueries(JSON.parse(stored))
      } catch (e) {
        console.error('Failed to parse stored queries:', e)
      }
    }
  }

  const saveGoogleQueries = (queries: string[]) => {
    setGoogleQueries(queries)
    localStorage.setItem('google-rfp-queries', JSON.stringify(queries))
  }

  const addQuery = () => {
    if (!newQuery.trim()) return
    const updated = [...googleQueries, newQuery.trim()]
    saveGoogleQueries(updated)
    setNewQuery('')
  }

  const removeQuery = (index: number) => {
    const updated = googleQueries.filter((_, i) => i !== index)
    saveGoogleQueries(updated)
  }

  const handleCsvImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      // Parse CSV - looking for tribe names in the "Tribe" column
      const lines = text.split('\n')
      const headers = lines[0]?.split(',') || []
      const tribeIndex = headers.findIndex((h) =>
        h.toLowerCase().includes('tribe'),
      )

      if (tribeIndex === -1) {
        alert('Could not find "Tribe" column in CSV')
        return
      }

      const tribeNames = new Set<string>()
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i]
        if (!line.trim()) continue
        const values = line.split(',')
        const tribeName = values[tribeIndex]?.trim().replace(/^"|"$/g, '')
        if (tribeName) {
          tribeNames.add(tribeName)
        }
      }

      // Add queries like "TribeName RFP"
      const newQueries = Array.from(tribeNames)
        .map((name) => `${name} RFP`)
        .filter((q) => !googleQueries.includes(q))

      if (newQueries.length === 0) {
        alert('No new tribe names found in CSV')
        return
      }

      const updated = [...googleQueries, ...newQueries]
      saveGoogleQueries(updated)
      alert(`Added ${newQueries.length} search queries from CSV`)
    }
    reader.readAsText(file)
    // Reset input
    event.target.value = ''
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

  const runGoogleSearches = async () => {
    if (googleQueries.length === 0) {
      alert('Please add at least one search query')
      return
    }

    // For now, we'll run them sequentially
    // In the future, this should trigger a job that runs all queries
    for (const query of googleQueries) {
      await runScraper('google', { query, timeFilter: 'week' })
      // Small delay between requests
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  }

  const loadJobs = async (source?: string) => {
    if (!source && sources.length > 0) {
      // Load jobs for the first available source
      source = sources.find((s) => s.available)?.id
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
      source = sources.find((s) => s.available)?.id
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
        loadCandidates()
      }
    } catch (e: any) {
      alert(`Failed to import: ${e?.response?.data?.detail || e?.message || 'Unknown error'}`)
    }
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
            { id: 'queries', label: 'Google Queries' },
            { id: 'jobs', label: 'Recent Jobs' },
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
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  RFP Sources
                </h2>
                <p className="mt-1 text-sm text-gray-600">
                  Available scraping sources. Click "Run" to execute a scrape job.
                </p>
              </div>
            </div>
            {sourcesLoading ? (
              <div className="flex items-center justify-center h-48">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600" />
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {sources.map((source) => (
                  <Card
                    key={source.id}
                    hover={source.available}
                    className={source.available ? '' : 'opacity-60'}
                  >
                    <CardBody>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-semibold text-gray-900">
                              {source.name}
                            </h3>
                            {!source.available && (
                              <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                                Coming Soon
                              </span>
                            )}
                            {source.requiresAuth && (
                              <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                                Auth Required
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 mb-3">
                            {source.description}
                          </p>
                          {source.available && (
                            <button
                              onClick={() => runScraper(source.id)}
                              disabled={runningJobs[source.id]}
                              className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <PlayIcon className="h-4 w-4" />
                              {runningJobs[source.id] ? 'Running...' : 'Run Scraper'}
                            </button>
                          )}
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
                        </div>
                      </div>
                    </CardBody>
                  </Card>
                ))}
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

      {/* Google Queries Tab */}
      {activeTab === 'queries' && (
        <div className="space-y-6">
          <div className="bg-white shadow rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Google Search Queries
                </h2>
                <p className="mt-1 text-sm text-gray-600">
                  Manage search terms for daily Google scraping. Each query will be searched with a "last week" filter.
                </p>
              </div>
              <button
                onClick={runGoogleSearches}
                disabled={googleQueries.length === 0}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <PlayIcon className="h-4 w-4" />
                Run All Searches
              </button>
            </div>

            {/* CSV Import */}
            <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Import Tribal Directory CSV
              </label>
              <p className="text-xs text-gray-600 mb-3">
                Upload a CSV file with a "Tribe" column to automatically generate search queries (e.g., "TribeName RFP").
              </p>
              <input
                type="file"
                accept=".csv"
                onChange={handleCsvImport}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100"
              />
            </div>

            {/* Add Query */}
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={newQuery}
                onChange={(e) => setNewQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addQuery()
                  }
                }}
                placeholder="e.g., 'solar RFP', 'tribal energy procurement'"
                className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm"
              />
              <button
                onClick={addQuery}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
              >
                <PlusIcon className="h-4 w-4" />
                Add
              </button>
            </div>

            {/* Query List */}
            <div className="space-y-2">
              {googleQueries.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No search queries configured yet.</p>
              ) : (
                googleQueries.map((query, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-md border border-gray-200"
                  >
                    <span className="text-sm text-gray-900 font-medium">{query}</span>
                    <button
                      onClick={() => removeQuery(index)}
                      className="text-red-600 hover:text-red-800"
                    >
                      <XCircleIcon className="h-5 w-5" />
                    </button>
                  </div>
                ))
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
