'use client'

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
import { useEffect, useMemo, useRef, useState } from 'react'
import AIPreviewModal from '@/components/AIPreviewModal'
import AttachmentUploadModal from '@/components/AttachmentUploadModal'
import ConfirmDeleteModal from '@/components/ConfirmDeleteModal'
import { useToast } from '@/components/ui/Toast'
import {
  contentApi,
  extractList,
  proposalApi,
  RFP,
  rfpApi,
  Template,
  templateApi,
} from '@/lib/api'

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
  const [expandedQuestions, setExpandedQuestions] = useState<number[]>([])
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

  useEffect(() => {
    if (id) {
      loadRFP(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  useEffect(() => {
    // Clear selection when switching RFPs or when buyer list changes significantly.
    setBuyerSelected({})
  }, [rfp?._id])

  const loadRFP = async (rfpId: string) => {
    try {
      const [rfpResponse, templatesResponse, companiesResponse] =
        await Promise.all([
          rfpApi.get(rfpId),
          templateApi.list(),
          contentApi.getCompanies(),
        ])
      setRfp(rfpResponse.data)
      const templatesData = extractList<Template>(templatesResponse)
      setTemplates(templatesData)

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

      setProposalsLoading(true)
      try {
        const p = await rfpApi.getProposals(rfpId)
        setRfpProposals(extractList<any>(p))
      } finally {
        setProposalsLoading(false)
      }
    } catch (error) {
      console.error('Error loading RFP:', error)
      setError('Failed to load RFP details')
    } finally {
      setLoading(false)
    }
  }

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

  const toggleQuestion = (index: number) => {
    setExpandedQuestions((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index],
    )
  }

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
    <div>
      {/* Disqualified Banner */}
      {rfp.isDisqualified && (
        <div className="bg-red-50 border-l-4 border-red-400 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400"
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">
                <span className="font-medium">Disqualified:</span> One or more
                critical deadlines for this RFP have passed.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="bg-white shadow">
        <div className="px-4 sm:px-6 lg:max-w-6xl lg:mx-auto lg:px-8">
          <div className="py-6 md:flex md:items-center md:justify-between lg:border-t lg:border-gray-200">
            <div className="flex-1 min-w-0">
              <div className="flex items-center">
                <DocumentTextIcon className="h-8 w-8 text-gray-400 mr-3" />
                <div>
                  <h1
                    className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate"
                    title={rfp.title}
                  >
                    {trimTitle(rfp.title, 80)}
                  </h1>
                  <div className="mt-1 flex items-center text-sm text-gray-500">
                    <BuildingOfficeIcon className="h-4 w-4 mr-1" />
                    {rfp.clientName}
                    <span className="mx-2">•</span>
                    <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                      {rfp.projectType.replace('_', ' ')}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-4 flex md:mt-0 md:ml-4">
              <Link
                href={`/linkedin-finder?rfpId=${encodeURIComponent(rfp._id)}`}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
              >
                <UserGroupIcon className="h-5 w-5 mr-2" />
                Run LinkedIn Finder
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mt-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          {Array.isArray(rfp.dateWarnings) && rfp.dateWarnings.length > 0 && (
            <div className="mb-6 bg-amber-50 border border-amber-200 rounded-lg p-4">
              <div className="text-sm font-semibold text-amber-900">
                Timing / sanity warnings
              </div>
              <ul className="mt-2 text-sm text-amber-800 list-disc pl-5 space-y-1">
                {rfp.dateWarnings.slice(0, 8).map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {typeof (rfp as any)?.fitScore === 'number' && (
            <div className="mb-6 bg-slate-50 border border-slate-200 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-slate-900">
                  Finder fit score
                </div>
                <div className="text-sm font-semibold text-slate-900">
                  {(rfp as any).fitScore}
                </div>
              </div>
              {Array.isArray((rfp as any)?.fitReasons) &&
                (rfp as any).fitReasons.length > 0 && (
                  <ul className="mt-2 text-sm text-slate-700 list-disc pl-5 space-y-1">
                    {(rfp as any).fitReasons
                      .slice(0, 8)
                      .map((w: any, idx: any) => (
                        <li key={idx}>{w}</li>
                      ))}
                  </ul>
                )}
            </div>
          )}

          {Array.isArray((rfp as any)?.buyerProfiles) &&
            (rfp as any).buyerProfiles.length > 0 && (
              <div className="mb-6 bg-white border border-gray-200 rounded-lg p-4">
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
                  <div className="flex items-center gap-2">
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
                      disabled={buyerRemoving || buyerSelectedList.length === 0}
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
                      Update via LinkedIn Finder →
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
                      {(rfp as any).buyerProfiles.slice(0, 25).map((p: any) => (
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
            )}

          {/* Overview Cards */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <CurrencyDollarIcon className="h-6 w-6 text-green-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Budget Range
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {rfp.budgetRange || 'Not specified'}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <CalendarDaysIcon className="h-6 w-6 text-red-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Submission Deadline
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {rfp.submissionDeadline
                          ? new Date(rfp.submissionDeadline).toLocaleDateString(
                              'en-US',
                            )
                          : 'Not specified'}
                      </dd>
                      {rfp.submissionDeadline &&
                        isDatePassed(rfp.submissionDeadline) && (
                          <dd className="text-xs font-medium text-red-600 mt-1">
                            ⚠️ Deadline passed
                          </dd>
                        )}
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <ClockIcon className="h-6 w-6 text-yellow-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Timeline
                      </dt>
                      <dd className="text-sm font-medium text-gray-900">
                        {rfp.timeline || 'To be determined'}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <DocumentTextIcon className="h-6 w-6 text-primary-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Bid Meeting Date
                      </dt>
                      <dd className="text-sm font-medium text-gray-900">
                        {rfp.bidMeetingDate
                          ? new Date(rfp.bidMeetingDate).toLocaleDateString(
                              'en-US',
                            )
                          : 'Not specified'}
                      </dd>
                      {rfp.bidMeetingDate &&
                        isDatePassed(rfp.bidMeetingDate) && (
                          <dd className="text-xs font-medium text-red-600 mt-1">
                            ⚠️ Date passed
                          </dd>
                        )}
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <DocumentTextIcon className="h-6 w-6 text-primary-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Bid Registration Date
                      </dt>
                      <dd className="text-sm font-medium text-gray-900">
                        {rfp.bidRegistrationDate
                          ? new Date(
                              rfp.bidRegistrationDate,
                            ).toLocaleDateString('en-US')
                          : 'Not specified'}
                      </dd>
                      {rfp.bidRegistrationDate &&
                        isDatePassed(rfp.bidRegistrationDate) && (
                          <dd className="text-xs font-medium text-red-600 mt-1">
                            ⚠️ Date passed
                          </dd>
                        )}
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <DocumentTextIcon className="h-6 w-6 text-primary-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Questions Deadline
                      </dt>
                      <dd className="text-sm font-medium text-gray-900">
                        {rfp.questionsDeadline
                          ? new Date(rfp.questionsDeadline).toLocaleDateString(
                              'en-US',
                            )
                          : 'Not specified'}
                      </dd>
                      {rfp.questionsDeadline &&
                        isDatePassed(rfp.questionsDeadline) && (
                          <dd className="text-xs font-medium text-red-600 mt-1">
                            ⚠️ Deadline passed
                          </dd>
                        )}
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg leading-6 font-medium text-gray-900">
                    Attachments
                  </h3>
                  <p className="mt-1 text-sm text-gray-500">
                    Upload and manage files related to this RFP
                  </p>
                </div>
                <button
                  onClick={() => setShowAttachmentModal(true)}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                >
                  <PaperClipIcon className="h-5 w-5 mr-2" />
                  Add Attachments
                </button>
              </div>
            </div>

            <div className="px-6 py-4">
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
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() =>
                            handleDeleteAttachment(file._id, file.originalName)
                          }
                          className="inline-flex items-center p-1.5 text-red-600 hover:text-red-800 hover:bg-red-50 rounded-md transition-colors"
                          title="Delete attachment"
                        >
                          <XMarkIcon className="h-5 w-5" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-gray-500">
                  No attachments uploaded yet
                </p>
              )}
            </div>
          </div>

          {/* Main Content Grid */}
          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Key Requirements */}
            <div className="bg-white shadow rounded-lg">
              <div className="px-6 py-5 border-b border-gray-200">
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  Key Requirements
                </h3>
              </div>
              <div className="px-6 py-4">
                {rfp.keyRequirements && rfp.keyRequirements.length > 0 ? (
                  <ul className="space-y-2">
                    {rfp.keyRequirements
                      .slice(0, 8)
                      .map((requirement, index) => (
                        <li key={index} className="flex items-start space-x-3">
                          <div className="flex-shrink-0">
                            <div className="w-2 h-2 bg-primary-600 rounded-full mt-2"></div>
                          </div>
                          <p className="text-sm text-gray-700">{requirement}</p>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">
                    No specific requirements identified
                  </p>
                )}
              </div>
            </div>

            {/* Deliverables */}
            <div className="bg-white shadow rounded-lg">
              <div className="px-6 py-5 border-b border-gray-200">
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  Expected Deliverables
                </h3>
              </div>
              <div className="px-6 py-4">
                {rfp.deliverables && rfp.deliverables.length > 0 ? (
                  <ul className="space-y-2">
                    {rfp.deliverables.slice(0, 6).map((deliverable, index) => (
                      <li key={index} className="flex items-start space-x-3">
                        <div className="flex-shrink-0">
                          <div className="w-2 h-2 bg-green-600 rounded-full mt-2"></div>
                        </div>
                        <p className="text-sm text-gray-700">{deliverable}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">
                    No specific deliverables identified
                  </p>
                )}
              </div>
            </div>

            {/* Evaluation Criteria */}
            <div className="bg-white shadow rounded-lg">
              <div className="px-6 py-5 border-b border-gray-200">
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  Evaluation Criteria
                </h3>
              </div>
              <div className="px-6 py-4">
                {rfp.evaluationCriteria && rfp.evaluationCriteria.length > 0 ? (
                  <ul className="space-y-2">
                    {rfp.evaluationCriteria
                      .slice(0, 6)
                      .map((criteria, index) => (
                        <li key={index} className="flex items-start space-x-3">
                          <div className="flex-shrink-0">
                            <div className="w-2 h-2 bg-yellow-600 rounded-full mt-2"></div>
                          </div>
                          <p className="text-sm text-gray-700">
                            {typeof criteria === 'string'
                              ? criteria
                              : (criteria as any).criteria ||
                                'Evaluation criterion'}
                          </p>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">
                    No evaluation criteria specified
                  </p>
                )}
              </div>
            </div>

            <div className="bg-white shadow rounded-lg">
              <div className="px-6 py-5 border-b border-gray-200">
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  Critical Information
                </h3>
              </div>
              <div className="px-6 py-4">
                {rfp.criticalInformation &&
                rfp.criticalInformation.length > 0 ? (
                  <ul className="space-y-2">
                    {rfp.criticalInformation
                      .slice(0, 5)
                      .map((requirement, index) => (
                        <li key={index} className="flex items-start space-x-3">
                          <div className="flex-shrink-0">
                            <div className="w-2 h-2 bg-red-600 rounded-full mt-2"></div>
                          </div>
                          <p className="text-sm text-gray-700">{requirement}</p>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">
                    No critical information identified
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Clarification Questions Section */}
          <div className="mt-8 bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Clarification Questions
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Questions to ask the RFP issuer for clarification on ambiguous
                or missing information
              </p>
            </div>
            <div className="px-6 py-4">
              {rfp.clarificationQuestions &&
              rfp.clarificationQuestions.length > 0 ? (
                <div className="space-y-2">
                  {rfp.clarificationQuestions.map((question, index) => (
                    <div
                      key={index}
                      className="flex items-start py-3 px-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                      onClick={() => toggleQuestion(index)}
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
                <p className="text-sm text-gray-500">
                  No clarification questions identified
                </p>
              )}
            </div>
          </div>

          {/* Generate Section */}
          <div className="mt-8 bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Generate
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Choose how you want to generate your proposal
              </p>
            </div>
            <div className="px-6 py-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div className="border border-gray-200 rounded-lg p-4 hover:border-primary-300 transition-colors">
                  <div className="flex items-center mb-3">
                    <div className="w-10 h-10 bg-gradient-to-br from-purple-100 to-pink-100 rounded-lg flex items-center justify-center mr-3">
                      <svg
                        className="h-5 w-5 text-purple-600"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                        />
                      </svg>
                    </div>
                    <div>
                      <h4 className="font-medium text-gray-900">AI Template</h4>
                      <p className="text-sm text-gray-500">
                        Generate from AI template
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setShowAIPreviewModal(true)}
                    className="w-full inline-flex items-center justify-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                  >
                    Preview
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Generate Proposal Section */}
          <div className="mt-8 bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Generate Proposal
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Create a customized proposal based on this RFP using one of our
                templates
              </p>
            </div>
            <div className="px-6 py-4">
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
                    This controls Title/Cover Letter/Experience content and
                    exports.
                  </p>
                </div>
              )}
              {templates.length > 0 ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
                        className="mt-3 w-full inline-flex items-center justify-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
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
                <p className="text-sm text-gray-500">Loading templates...</p>
              )}
            </div>
          </div>

          {/* Compare Proposals (Reviewer) */}
          <div className="mt-8 bg-white shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Proposals (Compare)
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Compare proposals for this RFP by reviewer score and status.
              </p>
            </div>
            <div className="px-6 py-4">
              {proposalsLoading ? (
                <p className="text-sm text-gray-500">Loading proposals...</p>
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
            </div>
          </div>
        </div>
      </div>

      {/* AI Preview Modal */}
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

