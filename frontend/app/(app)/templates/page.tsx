'use client'

import {
  CogIcon,
  EyeIcon,
  PencilSquareIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import CreateProposalModal from '@/components/proposals/CreateProposalModal'
import { useToast } from '@/components/ui/Toast'
import { Template, templateApi } from '@/lib/api'

export default function TemplatesPage() {
  const router = useRouter()
  const { success, error: showError, info } = useToast()
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(
    null,
  )
  const [templateDetails, setTemplateDetails] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [showTitleModal, setShowTitleModal] = useState(false)
  const [creating, setCreating] = useState(false)
  const [selectedTemplateType, setSelectedTemplateType] = useState<
    string | null
  >(null)

  useEffect(() => {
    loadTemplates()
  }, [])

  const loadTemplates = async () => {
    try {
      const response = await templateApi.list()
      const templatesData =
        (response as any).data?.data || (response as any).data || []
      setTemplates(Array.isArray(templatesData) ? templatesData : [])
    } catch (error) {
      console.error('Error loading templates:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadTemplateDetails = async (templateId: string) => {
    setLoadingDetails(true)
    try {
      const response = await templateApi.get(templateId)
      setTemplateDetails((response as any).data)
    } catch (error) {
      console.error('Error loading template details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }

  const handleTemplateSelect = (template: Template) => {
    setSelectedTemplate(template)
    loadTemplateDetails(template.id)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    )
  }

  return (
    <>
      <div>
        <div className="md:flex md:items-center md:justify-between">
          <div className="flex-1 min-w-0">
            <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
              Proposal Templates
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Pre-built templates for different types of projects
            </p>
          </div>
          <div className="mt-4 flex md:mt-0 md:ml-4">
            <button
              onClick={() => setShowTitleModal(true)}
              className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
            >
              <PlusIcon className="-ml-1 mr-2 h-5 w-5" aria-hidden="true" />
              Create Template
            </button>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-3">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              {templates.length > 0 ? (
                templates.map((template) => (
                  <div
                    key={template.id}
                    className={`bg-white overflow-hidden shadow rounded-lg cursor-pointer transition-all hover:shadow-lg ${
                      selectedTemplate?.id === template.id
                        ? 'ring-2 ring-primary-500 shadow-lg'
                        : ''
                    }`}
                    onClick={() => handleTemplateSelect(template)}
                  >
                    <div className="p-6">
                      <div className="flex items-center">
                        <div className="flex-shrink-0">
                          <CogIcon className="h-8 w-8 text-primary-600" />
                        </div>
                        <div className="ml-5 w-0 flex-1">
                          <dl>
                            <dt className="text-sm font-medium text-gray-500 truncate">
                              {template.name}
                            </dt>
                            <dd className="text-lg font-medium text-gray-900">
                              {template.projectType.replace('_', ' ')}
                            </dd>
                          </dl>
                        </div>
                      </div>
                      <div className="mt-4 flex items-center justify-between">
                        <p className="text-sm text-gray-500">
                          {template.sectionCount} sections
                        </p>
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              router.push(`/templates/${template.id}`)
                            }}
                            className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-primary-600 bg-primary-100 hover:bg-primary-200"
                          >
                            <PencilSquareIcon className="h-3 w-3 mr-1" />
                            Edit
                          </button>
                          <button className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-gray-600 bg-gray-100 hover:bg-gray-200">
                            <EyeIcon className="h-3 w-3 mr-1" />
                            Preview
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="col-span-1 sm:col-span-2 text-center py-12 bg-white rounded-lg shadow">
                  <CogIcon className="mx-auto h-12 w-12 text-gray-400" />
                  <h3 className="mt-2 text-sm font-medium text-gray-900">
                    No Templates
                  </h3>
                  <p className="mt-1 text-sm text-gray-500">
                    No proposal templates are available yet.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <CreateProposalModal
        isOpen={showTitleModal}
        onClose={() => {
          if (!creating) setShowTitleModal(false)
        }}
        loading={creating}
        selectedTemplateType={selectedTemplateType}
        onTemplateTypeSelect={setSelectedTemplateType}
        onCreate={async (title: string) => {
          if (!selectedTemplateType) {
            info('Please select a template type')
            return
          }
          setCreating(true)
          try {
            const res = await templateApi.create({
              name: title,
              templateType: selectedTemplateType,
            })
            const id = (res as any)?.data?.id || (res as any)?.id
            if (id) {
              await loadTemplates()
              success('Template created successfully')
            } else {
              showError('Template created but ID not returned')
            }
          } catch (_e) {
            showError('Failed to create template')
          } finally {
            setCreating(false)
            setShowTitleModal(false)
            setSelectedTemplateType(null)
          }
        }}
      />
    </>
  )
}
