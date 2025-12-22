'use client'

import Button from '@/components/ui/Button'
import Card, { CardBody } from '@/components/ui/Card'
import PipelineContextBanner from '@/components/ui/PipelineContextBanner'
import StepsPanel from '@/components/ui/StepsPanel'
import { rfpApi } from '@/lib/api'
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline'
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
      <PipelineContextBanner
        variant="tool"
        title="This is a supporting mini-workflow."
        description="Use it to pull in new RFPs and feed high-signal items into Pipeline."
        rightSlot={
          <Button as={Link} href="/rfps" variant="ghost" size="sm">
            View RFPs
          </Button>
        }
      />
      <div>
        <h1 className="text-3xl font-bold text-gray-900">RFP Finder</h1>
        <p className="mt-2 text-sm text-gray-600">
          Paste multiple RFP URLs (one per line) to analyze and save them.
        </p>
      </div>

      <StepsPanel
        title="How it works"
        tone="blue"
        columns={3}
        steps={[
          { title: 'Paste URLs', description: 'Add one RFP link per line.' },
          { title: 'Analyze', description: 'We extract + save each RFP.' },
          {
            title: 'Review in Pipeline',
            description: 'Triage and move work forward.',
          },
        ]}
      />

      <div className="bg-white shadow rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Saxon's Search Spaces
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Quick access to common RFP sources
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* LinkedIn */}
          <Card hover className="cursor-pointer">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 mb-1">LinkedIn</h3>
                  <p className="text-sm text-gray-600 mb-3">
                    Search for "solar RFP", "tribal RFP", etc. within your
                    network
                  </p>
                  <a
                    href="https://www.linkedin.com/search/results/content/?keywords=solar%20RFP"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Search{' '}
                    <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* Google */}
          <Card hover className="cursor-pointer">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 mb-1">Google</h3>
                  <p className="text-sm text-gray-600 mb-3">
                    Search with "last week" filter: "web development RFP",
                    "solar procurement", etc.
                  </p>
                  <a
                    href="https://www.google.com/search?q=web+development+RFP&tbs=qdr:w"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Search{' '}
                    <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* Bidnet Direct */}
          <Card hover className="cursor-pointer">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 mb-1">
                    Bidnet Direct
                  </h3>
                  <p className="text-sm text-gray-600 mb-3">
                    Supplier solicitations and RFP search
                  </p>
                  <a
                    href="https://www.bidnetdirect.com/private/supplier/solicitations/search"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Site <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* American Planning Association */}
          <Card hover className="cursor-pointer">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 mb-1">
                    American Planning Association
                  </h3>
                  <p className="text-sm text-gray-600 mb-3">
                    Daily RFP/RFQ listings for planning consultants
                  </p>
                  <a
                    href="https://www.planning.org/consultants/rfp/search/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Search{' '}
                    <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* F6S */}
          <Card hover className="cursor-pointer">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 mb-1">F6S</h3>
                  <p className="text-sm text-gray-600 mb-3">
                    Programs and opportunities for startups
                  </p>
                  <a
                    href="https://www.f6s.com/programs"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Site <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* OpenGov Procurement */}
          <Card hover className="cursor-pointer">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 mb-1">
                    OpenGov Procurement
                  </h3>
                  <p className="text-sm text-gray-600 mb-3">
                    Government procurement opportunities
                  </p>
                  <a
                    href="https://procurement.opengov.com/login"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Site <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* TechWerx */}
          <Card hover className="cursor-pointer border-amber-200">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-gray-900">TechWerx</h3>
                    <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                      Rare
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-3">
                    Technology opportunities (alerts recommended)
                  </p>
                  <a
                    href="https://www.techwerx.org/opportunities"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Site <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* EnergyWerx */}
          <Card hover className="cursor-pointer border-amber-200">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-gray-900">EnergyWerx</h3>
                    <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                      Rare
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-3">
                    Energy sector opportunities (alerts recommended)
                  </p>
                  <a
                    href="https://www.energywerx.org/opportunities"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Site <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>

          {/* HeroX */}
          <Card hover className="cursor-pointer border-amber-200">
            <CardBody>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-gray-900">HeroX</h3>
                    <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">
                      Rare
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-3">
                    Innovation challenges and opportunities
                  </p>
                  <a
                    href="https://www.herox.com/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary-600 hover:text-primary-800 inline-flex items-center gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open Site <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </CardBody>
          </Card>
        </div>
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
