'use client'

import AIModal from '@/components/AIModal'
import ContentLibraryModal from '@/components/ContentLibraryModal'
import TextEditor from '@/components/TextEditor'
import Modal from '@/components/ui/Modal'
import { PipelineBreadcrumbs } from '@/components/ui/PipelineBreadcrumbs'
import api, {
  Proposal,
  aiApi,
  canvaApi,
  cleanPathToken,
  contentApi,
  extractList,
  proposalApi,
  proposalApiPdf,
  proxyUrl,
} from '@/lib/api'
import {
  formatTitleObjectToText,
  getContentLibraryType,
  getSelectedIds,
  isContentLibrarySection,
  isTitleSectionName,
  parseTitleTextToObject,
  renderSectionContent,
} from '@/utils/proposalHelpers'
import {
  ArrowDownTrayIcon,
  BookOpenIcon,
  BuildingOfficeIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  CheckIcon,
  ChevronDownIcon,
  DocumentTextIcon,
  PencilSquareIcon,
  PlusIcon,
  SparklesIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'

export default function ProposalDetailPage() {
  const router = useRouter()
  const params = useParams<{ id?: string }>()
  const id = typeof params?.id === 'string' ? params.id : ''

  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editingSection, setEditingSection] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [isAddingSection, setIsAddingSection] = useState(false)
  const [newSectionTitle, setNewSectionTitle] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [showAIModal, setShowAIModal] = useState(false)
  const [aiEditingSection, setAiEditingSection] = useState<string | null>(null)
  const [isAILoading, setIsAILoading] = useState(false)
  const [showDownloadMenu, setShowDownloadMenu] = useState(false)
  const [downloadFormat, setDownloadFormat] = useState<'pdf' | 'docx'>('pdf')
  const downloadMenuRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<number | null>(null)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [sectionToDelete, setSectionToDelete] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string>('')
  const [infoModalOpen, setInfoModalOpen] = useState(false)
  const [infoModalTitle, setInfoModalTitle] = useState('')
  const [infoModalMessage, setInfoModalMessage] = useState('')
  const [infoModalVariant, setInfoModalVariant] = useState<
    'info' | 'success' | 'error'
  >('info')
  const [showContentLibraryModal, setShowContentLibraryModal] = useState(false)
  const [contentLibrarySection, setContentLibrarySection] = useState<
    string | null
  >(null)
  const [contentLibraryType, setContentLibraryType] = useState<
    'team' | 'references' | 'company'
  >('team')
  const [isContentLibraryLoading, setIsContentLibraryLoading] = useState(false)
  const [companies, setCompanies] = useState<any[]>([])
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(
    null,
  )
  const [switchingCompany, setSwitchingCompany] = useState(false)
  const [reviewScore, setReviewScore] = useState<string>('')
  const [reviewNotes, setReviewNotes] = useState<string>('')
  const [savingReview, setSavingReview] = useState(false)
  const [rubric, setRubric] = useState<{
    rebuttalItems: { id: string; text: string; done: boolean }[]
    submissionChecklist: { id: string; text: string; done: boolean }[]
  }>({ rebuttalItems: [], submissionChecklist: [] })
  const [rubricBaseline, setRubricBaseline] = useState<string>('')
  const [savingRubric, setSavingRubric] = useState(false)
  const [newRebuttalText, setNewRebuttalText] = useState('')
  const [newSubmissionText, setNewSubmissionText] = useState('')

  const rubricDirty = useMemo(() => {
    try {
      return JSON.stringify(rubric) !== (rubricBaseline || '')
    } catch {
      return true
    }
  }, [rubric, rubricBaseline])

  const openInfo = (
    title: string,
    message: string,
    variant: 'info' | 'success' | 'error' = 'info',
  ) => {
    setInfoModalTitle(title)
    setInfoModalMessage(message)
    setInfoModalVariant(variant)
    setInfoModalOpen(true)
  }

  useEffect(() => {
    if (id) {
      loadProposal(id)
    }
  }, [id])

  // Poll while async proposal generation is running.
  useEffect(() => {
    const status = String(
      (proposal as any)?.generationStatus || '',
    ).toLowerCase()
    const isRunning = status === 'queued' || status === 'running'

    if (!id || !isRunning) {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      return
    }

    if (pollRef.current) return
    pollRef.current = window.setInterval(() => {
      loadProposal(id)
    }, 2000)

    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, (proposal as any)?.generationStatus])

  useEffect(() => {
    const loadCompanies = async () => {
      try {
        const resp = await contentApi.getCompanies()
        setCompanies(extractList<any>(resp))
      } catch {
        setCompanies([])
      }
    }
    loadCompanies()
  }, [])

  // Close download menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        downloadMenuRef.current &&
        !downloadMenuRef.current.contains(event.target as Node)
      ) {
        setShowDownloadMenu(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const loadProposal = async (proposalId: string) => {
    try {
      const response = await proposalApi.get(proposalId)
      const proposalData = (response as any)?.data?.data
        ? (response as any).data.data
        : response.data
      setProposal(proposalData as Proposal)
      setSelectedCompanyId((proposalData as any)?.companyId || null)
      const existingScore = (proposalData as any)?.review?.score
      setReviewScore(
        existingScore === null || existingScore === undefined
          ? ''
          : String(existingScore),
      )
      setReviewNotes(String((proposalData as any)?.review?.notes || ''))

      const rawRubric = (proposalData as any)?.review?.rubric
      const defaultRubric = {
        rebuttalItems: [
          {
            id: 'r1',
            text: 'Confirm compliance gaps are addressed',
            done: false,
          },
          {
            id: 'r2',
            text: 'Run a red-team pass for clarity and risks',
            done: false,
          },
        ],
        submissionChecklist: [
          { id: 's1', text: 'Final narrative edit complete', done: false },
          { id: 's2', text: 'Formatting/branding checked', done: false },
          { id: 's3', text: 'Exported final PDF/DOCX', done: false },
          { id: 's4', text: 'Submitted to client', done: false },
        ],
      }

      const nextRubric =
        rawRubric && typeof rawRubric === 'object'
          ? {
              rebuttalItems: Array.isArray((rawRubric as any).rebuttalItems)
                ? (rawRubric as any).rebuttalItems
                    .filter((x: any) => x && typeof x === 'object')
                    .map((x: any, idx: number) => ({
                      id: String(x.id || `r_${idx}`).slice(0, 80),
                      text: String(x.text || '').trim(),
                      done: Boolean(x.done),
                    }))
                    .filter((x: any) => x.text)
                    .slice(0, 100)
                : defaultRubric.rebuttalItems,
              submissionChecklist: Array.isArray(
                (rawRubric as any).submissionChecklist,
              )
                ? (rawRubric as any).submissionChecklist
                    .filter((x: any) => x && typeof x === 'object')
                    .map((x: any, idx: number) => ({
                      id: String(x.id || `s_${idx}`).slice(0, 80),
                      text: String(x.text || '').trim(),
                      done: Boolean(x.done),
                    }))
                    .filter((x: any) => x.text)
                    .slice(0, 100)
                : defaultRubric.submissionChecklist,
            }
          : defaultRubric

      setRubric(nextRubric)
      try {
        setRubricBaseline(JSON.stringify(nextRubric))
      } catch {
        setRubricBaseline('')
      }
    } catch (error) {
      console.error('Error loading proposal:', error)
      setError('Failed to load proposal details')
    } finally {
      setLoading(false)
    }
  }

  const switchCompany = async (companyId: string) => {
    if (!proposal) return
    setSwitchingCompany(true)
    try {
      const resp = await proposalApi.setCompany(proposal._id, companyId)
      setProposal(resp.data as any)
      setSelectedCompanyId(companyId)
      openInfo(
        'Company updated',
        'Proposal company/branding updated.',
        'success',
      )
    } catch (error) {
      console.error('Error switching company:', error)
      openInfo('Update failed', 'Failed to switch proposal company.', 'error')
    } finally {
      setSwitchingCompany(false)
    }
  }

  const saveReview = async () => {
    if (!proposal) return
    setSavingReview(true)
    try {
      const scoreVal =
        reviewScore.trim() === ''
          ? null
          : Math.max(0, Math.min(100, Number(reviewScore)))
      const resp = await proposalApi.updateReview(proposal._id, {
        score: Number.isFinite(Number(scoreVal)) ? (scoreVal as any) : null,
        notes: reviewNotes,
      })
      setProposal(resp.data as any)
      openInfo('Review saved', 'Review score/notes updated.', 'success')
    } catch (error) {
      console.error('Error saving review:', error)
      openInfo('Save failed', 'Failed to save review.', 'error')
    } finally {
      setSavingReview(false)
    }
  }

  const saveRubric = async () => {
    if (!proposal) return
    setSavingRubric(true)
    try {
      const resp = await proposalApi.updateReview(proposal._id, {
        rubric,
      })
      setProposal(resp.data as any)
      try {
        setRubricBaseline(JSON.stringify(rubric))
      } catch {
        setRubricBaseline('')
      }
      openInfo('Saved', 'Review/rebuttal checklist updated.', 'success')
    } catch (error) {
      console.error('Error saving rubric:', error)
      openInfo('Save failed', 'Failed to save review checklist.', 'error')
    } finally {
      setSavingRubric(false)
    }
  }

  const startEdit = (sectionName: string, content: any) => {
    setEditingSection(sectionName)
    if (sectionName === 'Title' && content && typeof content === 'object') {
      setEditContent(formatTitleObjectToText(content))
    } else {
      setEditContent(
        typeof content === 'string' ? content : String(content ?? ''),
      )
    }
  }

  const cancelEdit = () => {
    setEditingSection(null)
    setEditContent('')
  }

  const saveSection = async () => {
    if (!proposal || !editingSection) return

    setSaving(true)
    try {
      const isTitle = editingSection === 'Title'
      const newContent = isTitle
        ? parseTitleTextToObject(editContent)
        : editContent

      const updatedSections = {
        ...proposal.sections,
        [editingSection]: {
          ...proposal.sections[editingSection],
          content: newContent,
          lastModified: new Date().toISOString(),
        },
      }

      const response = await proposalApi.update(proposal._id, {
        sections: updatedSections,
      })
      setProposal(response.data)
      setEditingSection(null)
      setEditContent('')
    } catch (error) {
      console.error('Error saving section:', error)
      openInfo(
        'Save failed',
        'Failed to save section. Please try again.',
        'error',
      )
    } finally {
      setSaving(false)
    }
  }

  const deleteSection = (sectionName: string) => {
    setSectionToDelete(sectionName)
    setDeleteError('')
    setShowDeleteModal(true)
  }

  const performDeleteSection = async () => {
    if (!proposal || !sectionToDelete) return
    setSaving(true)
    try {
      const updatedSections = { ...proposal.sections }
      delete updatedSections[sectionToDelete]

      const response = await proposalApi.update(proposal._id, {
        sections: updatedSections,
      })
      setProposal(response.data)
      setShowDeleteModal(false)
      setSectionToDelete(null)
      setDeleteError('')
    } catch (error) {
      console.error('Error deleting section:', error)
      setDeleteError('Failed to delete section. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const addSection = async () => {
    if (!proposal || !newSectionTitle.trim()) return

    setSaving(true)
    try {
      const updatedSections = {
        ...proposal.sections,
        [newSectionTitle]: {
          content: '',
          type: 'custom',
          lastModified: new Date().toISOString(),
        },
      }

      const response = await proposalApi.update(proposal._id, {
        sections: updatedSections,
      })
      setProposal(response.data)
      setIsAddingSection(false)
      setNewSectionTitle('')
      setEditingSection(newSectionTitle)
      setEditContent('')
    } catch (error) {
      console.error('Error adding section:', error)
      openInfo(
        'Add section failed',
        'Failed to add section. Please try again.',
        'error',
      )
    } finally {
      setSaving(false)
    }
  }

  const uploadToGoogleDrive = async () => {
    if (!proposal) return

    setUploading(true)
    try {
      const fileName = `${proposal.title.replace(
        /[^a-z0-9]/gi,
        '_',
      )}_Proposal.json`

      const response = await api.post(
        proxyUrl(
          `/googledrive/upload-proposal/${cleanPathToken(proposal._id)}`,
        ),
        {
          fileName,
        },
      )

      openInfo(
        'Upload successful',
        `Proposal uploaded to Google Drive. File: ${response.data.file.name}`,
        'success',
      )
    } catch (error) {
      console.error('Error uploading to Google Drive:', error)
      openInfo(
        'Upload failed',
        'Failed to upload to Google Drive. Please ensure Google Drive is configured and try again.',
        'error',
      )
    } finally {
      setUploading(false)
    }
  }

  const downloadProposal = async (format: 'pdf' | 'docx' = downloadFormat) => {
    if (!proposal) {
      alert('Proposal not loaded.')
      return
    }

    setDownloading(true)
    setShowDownloadMenu(false)

    // Show timeout warning after 10 seconds
    const timeoutWarning = setTimeout(() => {
      if (downloading) {
        console.log(
          `${format.toUpperCase()} generation is taking longer than expected...`,
        )
      }
    }, 10000)

    try {
      let response
      let mimeType
      let fileExtension

      if (format === 'pdf') {
        response = await proposalApiPdf.exportPdf(proposal._id)
        mimeType = 'application/pdf'
        fileExtension = 'pdf'
      } else {
        response = await proposalApiPdf.exportDocx(proposal._id)
        mimeType =
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        fileExtension = 'docx'
      }

      const blob = new Blob([response.data], { type: mimeType })
      const link = document.createElement('a')
      link.href = window.URL.createObjectURL(blob)
      link.download = `${proposal.title
        .replace(/[^a-z0-9]/gi, '_')
        .toLowerCase()}.${fileExtension}`
      link.click()

      setTimeout(() => {
        window.URL.revokeObjectURL(link.href)
      }, 1000)
    } catch (err: any) {
      console.error('Download failed:', err)
      let message = 'Unknown error'
      if (err instanceof Error) {
        message = err.message
      } else if (typeof err === 'string') {
        message = err
      } else if (err?.response?.data?.error) {
        message = err.response.data.error
      }
      openInfo(
        'Download failed',
        `Failed to download proposal ${format.toUpperCase()}: ${message}`,
        'error',
      )
    } finally {
      clearTimeout(timeoutWarning)
      setDownloading(false)
    }
  }

  const exportCanvaPdf = async () => {
    if (!proposal) return
    setDownloading(true)
    setShowDownloadMenu(false)
    try {
      const resp = await canvaApi.exportProposalPdf(proposal._id)
      const blob = new Blob([resp.data], { type: 'application/pdf' })
      const link = document.createElement('a')
      link.href = window.URL.createObjectURL(blob)
      link.download = `${proposal.title
        .replace(/[^a-z0-9]/gi, '_')
        .toLowerCase()}_canva.pdf`
      link.click()
      setTimeout(() => window.URL.revokeObjectURL(link.href), 1000)
      openInfo('Canva export', 'Canva PDF export started.', 'success')
    } catch (err: any) {
      console.error('Canva PDF export failed:', err)
      const message =
        err?.response?.data?.error ||
        err?.response?.data?.message ||
        err?.message ||
        'Export failed'
      openInfo(
        'Canva export failed',
        `${message}\n\nTip: configure Canva under Integrations → Canva.`,
        'error',
      )
    } finally {
      setDownloading(false)
    }
  }

  const openInCanva = async () => {
    if (!proposal) return
    setDownloading(true)
    setShowDownloadMenu(false)
    try {
      const resp = await canvaApi.createDesignFromProposal(proposal._id)
      const editUrl = resp.data?.design?.urls?.edit_url || null
      if (!editUrl) {
        openInfo(
          'Canva design created',
          'Design created but no edit URL returned.',
          'info',
        )
        return
      }
      window.open(editUrl, '_blank', 'noopener,noreferrer')
      openInfo('Opened in Canva', 'Design opened in a new tab.', 'success')
    } catch (err: any) {
      console.error('Open in Canva failed:', err)
      const message =
        err?.response?.data?.error ||
        err?.response?.data?.message ||
        err?.message ||
        'Failed to create Canva design'
      openInfo(
        'Open in Canva failed',
        `${message}\n\nTip: configure Canva under Integrations → Canva.`,
        'error',
      )
    } finally {
      setDownloading(false)
    }
  }

  const generateAISections = async () => {
    if (!proposal) return

    setGenerating(true)
    try {
      const response = await proposalApi.generateSections(proposal._id)
      setProposal(response.data.proposal)
      openInfo('AI sections', 'AI sections generated successfully!', 'success')
    } catch (error) {
      console.error('Error generating AI sections:', error)
      openInfo(
        'AI generation failed',
        'Failed to generate AI sections. Please try again.',
        'error',
      )
    } finally {
      setGenerating(false)
    }
  }

  const startAIEdit = (sectionName: string) => {
    setAiEditingSection(sectionName)
    setShowAIModal(true)
  }

  const handleAIEdit = async (prompt: string) => {
    if (!proposal || !aiEditingSection) return

    setIsAILoading(true)
    try {
      const currentContent = proposal.sections[aiEditingSection]?.content || ''

      const response = await aiApi.editText({
        text: currentContent,
        prompt,
      })

      if (response.data.success) {
        const updatedSections = {
          ...proposal.sections,
          [aiEditingSection]: {
            ...proposal.sections[aiEditingSection],
            content: response.data.editedText,
            lastModified: new Date().toISOString(),
          },
        }

        const updateResponse = await proposalApi.update(proposal._id, {
          sections: updatedSections,
        })
        setProposal(updateResponse.data)
        setShowAIModal(false)
        setAiEditingSection(null)
      } else {
        throw new Error(response.data.error || 'AI edit failed')
      }
    } catch (error: any) {
      console.error('AI edit failed:', error)
      const errorMessage =
        error.response?.data?.error ||
        error.message ||
        'AI edit failed. Please try again.'
      openInfo('AI edit failed', errorMessage, 'error')
    } finally {
      setIsAILoading(false)
    }
  }

  const cancelAIEdit = () => {
    setShowAIModal(false)
    setAiEditingSection(null)
  }

  const openContentLibrary = (sectionName: string) => {
    const type = getContentLibraryType(sectionName)
    if (!type) return

    setContentLibrarySection(sectionName)
    setContentLibraryType(type)
    setShowContentLibraryModal(true)
  }

  const handleContentLibrarySelection = async (selectedIds: string[]) => {
    if (!proposal || !contentLibrarySection) return

    setIsContentLibraryLoading(true)
    try {
      const response = await proposalApi.updateContentLibrarySection(
        proposal._id,
        contentLibrarySection,
        {
          selectedIds,
          type: contentLibraryType,
        },
      )

      setProposal(response.data)
      setShowContentLibraryModal(false)
      setContentLibrarySection(null)

      openInfo(
        'Content updated',
        'Content library selection updated successfully!',
        'success',
      )
    } catch (error: any) {
      console.error('Error updating content library selection:', error)
      const errorMessage =
        error.response?.data?.error ||
        'Failed to update content library selection'
      openInfo('Update failed', errorMessage, 'error')
    } finally {
      setIsContentLibraryLoading(false)
    }
  }

  const cancelContentLibrary = () => {
    setShowContentLibraryModal(false)
    setContentLibrarySection(null)
  }

  const sectionEntries = useMemo(() => {
    return Object.entries((proposal?.sections as any) || {})
  }, [proposal])

  const contentLibraryIssues = useMemo(() => {
    return sectionEntries
      .filter(([_, sectionData]) => isContentLibrarySection(sectionData))
      .map(([sectionName, sectionData]: [string, any]) => {
        const t = getContentLibraryType(sectionName)
        const selected = getSelectedIds(sectionData)
        const content = sectionData?.content
        const contentStr = typeof content === 'string' ? content : ''

        const problems: string[] = []

        if (t === 'team' && selected.length === 0) {
          problems.push(`No team members selected for "${sectionName}".`)
        }
        if (t === 'references' && selected.length === 0) {
          problems.push(`No references selected for "${sectionName}".`)
        }
        if (
          t === 'company' &&
          selected.length === 0 &&
          !isTitleSectionName(sectionName)
        ) {
          problems.push(`No company profile selected for "${sectionName}".`)
        }

        if (
          contentStr.includes('No team members available') ||
          contentStr.includes('No suitable team members') ||
          contentStr.includes('No project references available') ||
          contentStr.includes('No suitable project references') ||
          contentStr.includes('No company information available') ||
          contentStr.includes('Selected company not found')
        ) {
          problems.push(
            `"${sectionName}" is missing required content library data.`,
          )
        }

        return problems
      })
      .flat()
  }, [sectionEntries])

  const compliance = useMemo(() => {
    const rfp = (proposal as any)?.rfp
    const reqs = Array.isArray(rfp?.review?.requirements)
      ? rfp.review.requirements
      : []
    const counts = { ok: 0, risk: 0, gap: 0, unknown: 0 }
    const items = reqs
      .map((r: any) => ({
        text: String(r?.text || '').trim(),
        status: String(r?.status || 'unknown').toLowerCase(),
        notes: String(r?.notes || ''),
        mappedSections: Array.isArray(r?.mappedSections)
          ? r.mappedSections
              .map((x: any) => String(x || '').trim())
              .filter(Boolean)
          : [],
      }))
      .filter((x: any) => x.text)
      .slice(0, 200)
    items.forEach((x: any) => {
      if (x.status === 'ok') counts.ok += 1
      else if (x.status === 'risk') counts.risk += 1
      else if (x.status === 'gap') counts.gap += 1
      else counts.unknown += 1
    })
    const gaps = items.filter((x: any) => x.status === 'gap')
    const risks = items.filter((x: any) => x.status === 'risk')
    return { counts, items, gaps, risks }
  }, [proposal])

  const derivedReady = useMemo(() => {
    const noContentIssues = contentLibraryIssues.length === 0
    const noGaps = (compliance?.gaps || []).length === 0
    const hasScore = reviewScore.trim() !== ''
    return {
      noContentIssues,
      noGaps,
      hasScore,
      ok: noContentIssues && noGaps,
    }
  }, [contentLibraryIssues.length, compliance?.gaps, reviewScore])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (error || !proposal) {
    return (
      <div className="text-center py-12">
        <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
        <h3 className="mt-2 text-sm font-medium text-gray-900">
          Proposal not found
        </h3>
        <p className="mt-1 text-sm text-gray-500">
          {error || 'The proposal you are looking for does not exist.'}
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

  const genStatus = String(
    (proposal as any)?.generationStatus || '',
  ).toLowerCase()
  const genRunning = genStatus === 'queued' || genStatus === 'running'
  const genError =
    genStatus === 'error'
      ? String((proposal as any)?.generationError || '').trim()
      : ''

  return (
    <div>
      <div className="mb-4 px-4 sm:px-6 lg:max-w-6xl lg:mx-auto lg:px-8">
        <PipelineBreadcrumbs
          items={[
            { label: 'Pipeline', href: '/pipeline' },
            { label: 'Proposals', href: '/proposals' },
            { label: proposal.title || 'Proposal' },
          ]}
        />
      </div>
      {/* Header */}
      <div className="bg-white shadow">
        <div className="px-4 sm:px-6 lg:max-w-6xl lg:mx-auto lg:px-8">
          <div className="py-6 md:flex md:items-center md:justify-between lg:border-t lg:border-gray-200">
            <div className="flex-1 min-w-0">
              <div className="flex items-center">
                <DocumentTextIcon className="h-8 w-8 text-gray-400 mr-3" />
                <div className="min-w-0 flex-1">
                  <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl truncate">
                    {proposal.title}
                  </h1>
                  <div className="mt-1 flex items-center text-sm text-gray-500">
                    <BuildingOfficeIcon className="h-4 w-4 mr-1" />
                    {(proposal as any).rfp?.clientName || 'Unknown Client'}
                    <span className="mx-2">•</span>
                    <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                      {proposal.status}
                    </span>
                  </div>
                </div>
              </div>
              {genRunning && (
                <div className="mt-3 text-sm text-blue-800 bg-blue-50 border border-blue-200 rounded-md px-3 py-2">
                  Generating proposal sections… This page will update
                  automatically.
                </div>
              )}
              {!genRunning && genError && (
                <div className="mt-3 text-sm text-red-800 bg-red-50 border border-red-200 rounded-md px-3 py-2">
                  AI generation failed. {genError}
                </div>
              )}
            </div>
            <div className="mt-6 flex space-x-3 md:mt-0 md:ml-4">
              {companies.length > 0 && (
                <div className="flex items-center space-x-2">
                  <select
                    value={selectedCompanyId || ''}
                    onChange={(e) => {
                      const next = e.target.value
                      setSelectedCompanyId(next || null)
                      if (next) switchCompany(next)
                    }}
                    disabled={switchingCompany}
                    className="border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
                    title="Switch proposal company/branding"
                  >
                    <option value="" disabled>
                      Select company
                    </option>
                    {companies.map((c) => (
                      <option key={c.companyId} value={c.companyId}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  {switchingCompany && (
                    <div className="text-sm text-gray-500">Updating…</div>
                  )}
                </div>
              )}
              <div className="relative" ref={downloadMenuRef}>
                <button
                  onClick={() => setShowDownloadMenu(!showDownloadMenu)}
                  disabled={downloading}
                  className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {downloading ? (
                    <>
                      <div className="animate-spin -ml-1 mr-3 h-5 w-5 border-2 border-white border-t-transparent rounded-full" />
                      Generating {downloadFormat.toUpperCase()}...
                    </>
                  ) : (
                    <>
                      <ArrowDownTrayIcon
                        className="-ml-1 mr-2 h-5 w-5"
                        aria-hidden="true"
                      />
                      Download {downloadFormat.toUpperCase()}
                      <ChevronDownIcon
                        className="ml-2 h-4 w-4"
                        aria-hidden="true"
                      />
                    </>
                  )}
                </button>

                {showDownloadMenu && !downloading && (
                  <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg py-1 z-10 border border-gray-200">
                    <button
                      onClick={() => {
                        setDownloadFormat('pdf')
                        downloadProposal('pdf')
                      }}
                      className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <DocumentTextIcon className="mr-3 h-4 w-4" />
                      Download as PDF
                    </button>
                    <button
                      onClick={() => {
                        setDownloadFormat('docx')
                        downloadProposal('docx')
                      }}
                      className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      <DocumentTextIcon className="mr-3 h-4 w-4" />
                      Download as DOCX
                    </button>
                    <div className="my-1 border-t border-gray-200" />
                    <button
                      onClick={openInCanva}
                      className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                      title="Create a Canva design from this proposal and open it"
                    >
                      <SparklesIcon className="mr-3 h-4 w-4" />
                      Open in Canva
                    </button>
                    <button
                      onClick={exportCanvaPdf}
                      className="flex items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                      title="Create a Canva design and export as PDF"
                    >
                      <SparklesIcon className="mr-3 h-4 w-4" />
                      Export Canva PDF
                    </button>
                  </div>
                )}
              </div>
              {/* <button
                onClick={uploadToGoogleDrive}
                disabled={uploading}
                className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              >
                {uploading ? (
                  <>
                    <div className="animate-spin -ml-1 mr-3 h-5 w-5 border-2 border-white border-t-transparent rounded-full" />
                    Uploading...
                  </>
                ) : (
                  <>
                    Upload to Drive
                  </>
                )}
              </button> */}
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mt-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Overview Cards */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3 mb-8">
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <CheckCircleIcon className="h-6 w-6 text-green-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Status
                      </dt>
                      <dd className="text-lg font-medium text-gray-900 capitalize">
                        {proposal.status}
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
                    <CalendarDaysIcon className="h-6 w-6 text-blue-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Created
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {new Date(proposal.createdAt).toLocaleDateString(
                          'en-US',
                        )}
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
                    <DocumentTextIcon className="h-6 w-6 text-purple-400" />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Sections
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {sectionEntries.length}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Reviewer */}
          <div className="mb-6 bg-white overflow-hidden shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Reviewer
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Score and notes for comparing proposals under this RFP.
              </p>
            </div>
            <div className="px-6 py-4 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Score (0–100)
                  </label>
                  <input
                    value={reviewScore}
                    onChange={(e) => setReviewScore(e.target.value)}
                    inputMode="numeric"
                    className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
                    placeholder="e.g., 82"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-gray-700">
                    Notes
                  </label>
                  <textarea
                    value={reviewNotes}
                    onChange={(e) => setReviewNotes(e.target.value)}
                    rows={3}
                    className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
                    placeholder="Key strengths, risks, compliance issues, interview questions…"
                  />
                </div>
              </div>
              <div className="flex items-center justify-end">
                <button
                  onClick={saveReview}
                  disabled={savingReview}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                >
                  {savingReview ? 'Saving…' : 'Save review'}
                </button>
              </div>
            </div>
          </div>

          {contentLibraryIssues.length > 0 && (
            <div className="mb-6 bg-amber-50 border border-amber-200 rounded-lg p-4">
              <div className="text-sm font-semibold text-amber-900">
                Content Library items missing (this can cause generic or
                inaccurate sections)
              </div>
              <ul className="mt-2 text-sm text-amber-800 list-disc pl-5 space-y-1">
                {contentLibraryIssues.slice(0, 6).map((msg, idx) => (
                  <li key={idx}>{msg}</li>
                ))}
              </ul>
              <div className="mt-3 text-xs text-amber-700">
                Tip: use “Select from Library” on Team/References sections to
                fix this.
              </div>
            </div>
          )}

          {/* Review / rebuttal / submission */}
          <div className="mb-6 bg-white overflow-hidden shadow rounded-lg">
            <div className="px-6 py-5 border-b border-gray-200">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg leading-6 font-medium text-gray-900">
                    Review / rebuttal / submission
                  </h3>
                  <p className="mt-1 text-sm text-gray-500">
                    Track compliance gaps, rebuttal items, and submission
                    readiness.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={saveRubric}
                    disabled={savingRubric || !rubricDirty}
                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                  >
                    {savingRubric
                      ? 'Saving…'
                      : rubricDirty
                      ? 'Save checklist'
                      : 'Saved'}
                  </button>
                </div>
              </div>
            </div>

            <div className="px-6 py-4 space-y-6">
              {/* Compliance summary */}
              <div className="rounded-lg border border-gray-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      Compliance summary
                    </div>
                    <div className="mt-1 text-xs text-gray-600">
                      Derived from RFP requirement assessments.
                    </div>
                  </div>
                  {(proposal as any)?.rfp?._id ? (
                    <Link
                      href={`/rfps/${(proposal as any).rfp._id}`}
                      className="text-sm text-primary-600 hover:text-primary-800"
                    >
                      Open RFP →
                    </Link>
                  ) : null}
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="px-2 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">
                    OK {compliance.counts.ok}
                  </span>
                  <span className="px-2 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-900">
                    Risk {compliance.counts.risk}
                  </span>
                  <span className="px-2 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">
                    Gap {compliance.counts.gap}
                  </span>
                  <span className="px-2 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-800">
                    Unknown {compliance.counts.unknown}
                  </span>
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-semibold border ${
                      derivedReady.ok
                        ? 'bg-green-50 text-green-800 border-green-200'
                        : 'bg-amber-50 text-amber-900 border-amber-200'
                    }`}
                    title="Derived readiness: no content-library issues + no GAP requirements."
                  >
                    Derived readiness: {derivedReady.ok ? 'OK' : 'Needs work'}
                  </span>
                </div>

                {(compliance.gaps.length > 0 ||
                  compliance.risks.length > 0) && (
                  <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        Gaps
                      </div>
                      {compliance.gaps.length === 0 ? (
                        <div className="mt-2 text-sm text-gray-500">None.</div>
                      ) : (
                        <ul className="mt-2 space-y-2">
                          {compliance.gaps
                            .slice(0, 8)
                            .map((g: any, idx: number) => (
                              <li
                                key={`${idx}-${g.text}`}
                                className="rounded-md border border-red-200 bg-red-50 p-3"
                              >
                                <div className="text-sm font-semibold text-red-900">
                                  {g.text}
                                </div>
                                {g.notes ? (
                                  <div className="mt-1 text-xs text-red-800">
                                    {g.notes}
                                  </div>
                                ) : null}
                                {g.mappedSections?.length ? (
                                  <div className="mt-1 text-xs text-red-800">
                                    Sections: {g.mappedSections.join(', ')}
                                  </div>
                                ) : null}
                              </li>
                            ))}
                        </ul>
                      )}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        Risks
                      </div>
                      {compliance.risks.length === 0 ? (
                        <div className="mt-2 text-sm text-gray-500">None.</div>
                      ) : (
                        <ul className="mt-2 space-y-2">
                          {compliance.risks
                            .slice(0, 8)
                            .map((g: any, idx: number) => (
                              <li
                                key={`${idx}-${g.text}`}
                                className="rounded-md border border-amber-200 bg-amber-50 p-3"
                              >
                                <div className="text-sm font-semibold text-amber-900">
                                  {g.text}
                                </div>
                                {g.notes ? (
                                  <div className="mt-1 text-xs text-amber-800">
                                    {g.notes}
                                  </div>
                                ) : null}
                                {g.mappedSections?.length ? (
                                  <div className="mt-1 text-xs text-amber-800">
                                    Sections: {g.mappedSections.join(', ')}
                                  </div>
                                ) : null}
                              </li>
                            ))}
                        </ul>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Rebuttal checklist */}
              <div className="rounded-lg border border-gray-200 p-4">
                <div className="text-sm font-semibold text-gray-900">
                  Rebuttal / action items
                </div>
                <div className="mt-2 space-y-2">
                  {rubric.rebuttalItems.length === 0 ? (
                    <div className="text-sm text-gray-500">No items yet.</div>
                  ) : (
                    rubric.rebuttalItems.map((it) => (
                      <div
                        key={it.id}
                        className="flex items-center gap-2 rounded-md border border-gray-200 p-2"
                      >
                        <input
                          type="checkbox"
                          checked={it.done}
                          onChange={() =>
                            setRubric((prev) => ({
                              ...prev,
                              rebuttalItems: prev.rebuttalItems.map((x) =>
                                x.id === it.id ? { ...x, done: !x.done } : x,
                              ),
                            }))
                          }
                        />
                        <input
                          value={it.text}
                          onChange={(e) => {
                            const v = e.target.value
                            setRubric((prev) => ({
                              ...prev,
                              rebuttalItems: prev.rebuttalItems.map((x) =>
                                x.id === it.id ? { ...x, text: v } : x,
                              ),
                            }))
                          }}
                          className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm bg-white"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            setRubric((prev) => ({
                              ...prev,
                              rebuttalItems: prev.rebuttalItems.filter(
                                (x) => x.id !== it.id,
                              ),
                            }))
                          }
                          className="px-2 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                          title="Remove"
                        >
                          <XMarkIcon className="h-4 w-4" />
                        </button>
                      </div>
                    ))
                  )}
                  <div className="flex items-center gap-2">
                    <input
                      value={newRebuttalText}
                      onChange={(e) => setNewRebuttalText(e.target.value)}
                      placeholder="Add an item…"
                      className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm bg-white"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const t = newRebuttalText.trim()
                        if (!t) return
                        setRubric((prev) => ({
                          ...prev,
                          rebuttalItems: [
                            ...prev.rebuttalItems,
                            { id: `r_${Date.now()}`, text: t, done: false },
                          ],
                        }))
                        setNewRebuttalText('')
                      }}
                      className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                    >
                      Add
                    </button>
                  </div>
                </div>
              </div>

              {/* Submission checklist */}
              <div className="rounded-lg border border-gray-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      Submission readiness checklist
                    </div>
                    <div className="mt-1 text-xs text-gray-600">
                      Tip: derived readiness does not include
                      narrative/formatting work.
                    </div>
                  </div>
                  <div className="text-xs text-gray-600">
                    {rubric.submissionChecklist.filter((x) => x.done).length}/
                    {rubric.submissionChecklist.length} done
                  </div>
                </div>

                <div className="mt-3 space-y-2">
                  {rubric.submissionChecklist.map((it) => (
                    <div
                      key={it.id}
                      className="flex items-center gap-2 rounded-md border border-gray-200 p-2"
                    >
                      <input
                        type="checkbox"
                        checked={it.done}
                        onChange={() =>
                          setRubric((prev) => ({
                            ...prev,
                            submissionChecklist: prev.submissionChecklist.map(
                              (x) =>
                                x.id === it.id ? { ...x, done: !x.done } : x,
                            ),
                          }))
                        }
                      />
                      <input
                        value={it.text}
                        onChange={(e) => {
                          const v = e.target.value
                          setRubric((prev) => ({
                            ...prev,
                            submissionChecklist: prev.submissionChecklist.map(
                              (x) => (x.id === it.id ? { ...x, text: v } : x),
                            ),
                          }))
                        }}
                        className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm bg-white"
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setRubric((prev) => ({
                            ...prev,
                            submissionChecklist:
                              prev.submissionChecklist.filter(
                                (x) => x.id !== it.id,
                              ),
                          }))
                        }
                        className="px-2 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                        title="Remove"
                      >
                        <XMarkIcon className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  <div className="flex items-center gap-2">
                    <input
                      value={newSubmissionText}
                      onChange={(e) => setNewSubmissionText(e.target.value)}
                      placeholder="Add a checklist item…"
                      className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm bg-white"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const t = newSubmissionText.trim()
                        if (!t) return
                        setRubric((prev) => ({
                          ...prev,
                          submissionChecklist: [
                            ...prev.submissionChecklist,
                            { id: `s_${Date.now()}`, text: t, done: false },
                          ],
                        }))
                        setNewSubmissionText('')
                      }}
                      className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                    >
                      Add
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Add Section Button */}
          <div className="mb-6">
            {isAddingSection ? (
              <div className="bg-white shadow rounded-lg p-6">
                <div className="flex items-center space-x-4">
                  <input
                    type="text"
                    placeholder="Section title"
                    value={newSectionTitle}
                    onChange={(e) => setNewSectionTitle(e.target.value)}
                    className="flex-1 border-gray-300 rounded-md shadow-sm focus:ring-primary-500 bg-gray-100 focus:border-primary-500"
                    onKeyDown={(e) => e.key === 'Enter' && addSection()}
                  />
                  <button
                    onClick={addSection}
                    disabled={!newSectionTitle.trim() || saving}
                    className="inline-flex items-center px-3 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                  >
                    <CheckIcon className="h-4 w-4 mr-1" />
                    Add
                  </button>
                  <button
                    onClick={() => {
                      setIsAddingSection(false)
                      setNewSectionTitle('')
                    }}
                    className="inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
                  >
                    <XMarkIcon className="h-4 w-4 mr-1" />
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setIsAddingSection(true)}
                className="inline-flex items-center px-4 py-2 border border-dashed border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
              >
                <PlusIcon className="h-4 w-4 mr-2" />
                Add Section
              </button>
            )}
          </div>

          {/* Proposal Sections */}
          <div className="space-y-8">
            {sectionEntries.map(([sectionName, sectionData]: [string, any]) => (
              <div key={sectionName} className="bg-white shadow rounded-lg">
                <div className="px-6 py-5 border-b border-gray-200">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">
                      {sectionName}
                    </h3>
                    <div className="flex items-center space-x-2">
                      {/* Content Library Button - only show for content library sections, excluding Title/Title Page */}
                      {isContentLibrarySection(sectionData) &&
                        getContentLibraryType(sectionName) &&
                        !isTitleSectionName(sectionName) && (
                          <button
                            onClick={() => openContentLibrary(sectionName)}
                            className="bg-gradient-to-r from-blue-500 to-indigo-500 text-white px-3 py-1 rounded-full text-xs font-medium shadow-lg hover:shadow-xl transition-all duration-200 hover:scale-105 flex items-center space-x-1"
                            title="Select from Library"
                          >
                            <BookOpenIcon className="h-3 w-3" />
                            <span>Select from Library</span>
                          </button>
                        )}
                      {/* Ask AI - disable for content library sections to prevent hallucinations */}
                      {!isContentLibrarySection(sectionData) && (
                        <button
                          onClick={() => startAIEdit(sectionName)}
                          className="bg-gradient-to-r from-purple-500 to-pink-500 text-white px-3 py-1 rounded-full text-xs font-medium shadow-lg hover:shadow-xl transition-all duration-200 hover:scale-105 flex items-center space-x-1"
                          title="Ask with AI"
                        >
                          <SparklesIcon className="h-3 w-3" />
                          <span>Ask with AI</span>
                        </button>
                      )}
                      {editingSection !== sectionName && (
                        <div className="flex items-center space-x-1">
                          <button
                            onClick={() =>
                              startEdit(sectionName, sectionData.content || '')
                            }
                            className="p-1 text-gray-400 hover:text-gray-600"
                            title="Edit section"
                          >
                            <PencilSquareIcon className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => deleteSection(sectionName)}
                            className="p-1 text-gray-400 hover:text-red-600"
                            title="Delete section"
                          >
                            <TrashIcon className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <div className="px-6 py-4">
                  {editingSection === sectionName ? (
                    <div className="space-y-4">
                      <TextEditor
                        value={editContent}
                        onChange={setEditContent}
                        placeholder="Enter section content..."
                        className="min-h-64"
                      />
                      <div className="flex items-center space-x-3">
                        <button
                          onClick={saveSection}
                          disabled={saving}
                          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                        >
                          {saving ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                          ) : (
                            <CheckIcon className="h-4 w-4 mr-2" />
                          )}
                          Save Changes
                        </button>
                        <button
                          onClick={cancelEdit}
                          disabled={saving}
                          className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                        >
                          <XMarkIcon className="h-4 w-4 mr-2" />
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <div className="prose max-w-none text-sm text-gray-700 overflow-hidden">
                        <div
                          dangerouslySetInnerHTML={{
                            __html: renderSectionContent(
                              sectionData.content || '',
                              sectionName,
                            ),
                          }}
                        />
                      </div>
                      {sectionData.lastModified && (
                        <div className="mt-4 text-xs text-gray-400">
                          Last modified:{' '}
                          {new Date(sectionData.lastModified).toLocaleString(
                            'en-US',
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {sectionEntries.length === 0 && (
            <div className="text-center py-12 bg-white shadow rounded-lg">
              <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">
                No Content
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                This proposal has no sections or content yet.
              </p>
              <div className="mt-4">
                <button
                  onClick={() => setIsAddingSection(true)}
                  className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                >
                  <PlusIcon className="-ml-1 mr-2 h-5 w-5" />
                  Add First Section
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* AI Modal */}
      <AIModal
        isOpen={showAIModal}
        onClose={cancelAIEdit}
        onApply={handleAIEdit}
        isLoading={isAILoading}
      />

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        title="Delete section?"
        footer={
          <>
            <button
              onClick={() => setShowDeleteModal(false)}
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={performDeleteSection}
              disabled={saving}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            >
              {saving ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
              ) : null}
              Confirm
            </button>
          </>
        }
      >
        <div className="space-y-2">
          <p className="text-sm text-gray-700">
            Are you sure you want to delete
            {sectionToDelete ? ` "${sectionToDelete}"` : ''}?
          </p>
          <p className="text-xs text-gray-500">This action cannot be undone.</p>
          {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}
        </div>
      </Modal>

      {/* Info Modal */}
      <Modal
        isOpen={infoModalOpen}
        onClose={() => setInfoModalOpen(false)}
        title={infoModalTitle}
        footer={
          <button
            onClick={() => setInfoModalOpen(false)}
            className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
          >
            OK
          </button>
        }
      >
        <p
          className={`text-sm ${
            infoModalVariant === 'error'
              ? 'text-red-700'
              : infoModalVariant === 'success'
              ? 'text-green-700'
              : 'text-gray-700'
          }`}
        >
          {infoModalMessage}
        </p>
      </Modal>

      {/* Content Library Modal */}
      <ContentLibraryModal
        isOpen={showContentLibraryModal}
        onClose={cancelContentLibrary}
        onApply={handleContentLibrarySelection}
        type={contentLibraryType}
        currentSelectedIds={
          contentLibrarySection
            ? getSelectedIds(proposal?.sections[contentLibrarySection])
            : []
        }
        isLoading={isContentLibraryLoading}
      />

      <div className="mt-6 flex items-center justify-end">
        <button
          onClick={generateAISections}
          disabled={generating}
          className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50"
        >
          {generating ? 'Generating…' : 'Generate AI sections'}
        </button>
      </div>

      {/* (Optional) Google Drive upload button retained */}
      {/* <div className="mt-2">
        <button
          onClick={uploadToGoogleDrive}
          disabled={uploading}
          className="text-sm text-blue-700 underline"
        >
          {uploading ? 'Uploading…' : 'Upload proposal JSON to Google Drive'}
        </button>
      </div> */}
    </div>
  )
}
