'use client'

import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  CogIcon,
  DocumentTextIcon,
  EyeIcon,
  PencilSquareIcon,
  PlusIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useParams, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import TextEditor from '@/components/TextEditor'
import { templateApi } from '@/lib/api'

interface TemplateSection {
  title: string
  contentType: string
  required: boolean
  components?: string[]
  subsections?: string[]
  content?: string
}

export default function TemplateEditorPage() {
  const router = useRouter()
  const params = useParams<{ id?: string }>()
  const id = typeof params?.id === 'string' ? params.id : ''

  const [template, setTemplate] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editingSection, setEditingSection] = useState<number | null>(null)
  const [editContent, setEditContent] = useState<TemplateSection>({
    title: '',
    contentType: 'static',
    required: true,
  })
  const [isAddingSection, setIsAddingSection] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  useEffect(() => {
    if (id) {
      loadTemplate(id)
    }
  }, [id])

  const loadTemplate = async (templateId: string) => {
    try {
      const response = await templateApi.get(templateId)
      setTemplate((response as any).data)
    } catch (error) {
      console.error('Error loading template:', error)
      setError('Failed to load template details')
    } finally {
      setLoading(false)
    }
  }

  const startEdit = (index: number) => {
    const section = template.sections[index]
    setEditingSection(index)
    setEditContent({ ...section })
  }

  const cancelEdit = () => {
    setEditingSection(null)
    setEditContent({ title: '', contentType: 'static', required: true })
  }

  const saveSection = async () => {
    if (!template) return

    setSaving(true)
    try {
      const updatedSections = [...template.sections]
      if (editingSection !== null) {
        updatedSections[editingSection] = editContent
      } else {
        updatedSections.push(editContent)
      }

      const response = await templateApi.update(template.id, {
        sections: updatedSections,
      })
      setTemplate((response as any).data)

      setEditingSection(null)
      setIsAddingSection(false)
      setEditContent({ title: '', contentType: 'static', required: true })
    } catch (error) {
      console.error('Error saving section:', error)
      alert('Failed to save section. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const deleteSection = async (index: number) => {
    if (!template) return
    if (!confirm('Are you sure you want to delete this section?')) return

    setSaving(true)
    try {
      const updatedSections = template.sections.filter(
        (_: any, i: number) => i !== index,
      )
      const response = await templateApi.update(template.id, {
        sections: updatedSections,
      })
      setTemplate((response as any).data)
    } catch (error) {
      console.error('Error deleting section:', error)
      alert('Failed to delete section. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const moveSection = (index: number, direction: 'up' | 'down') => {
    if (!template) return

    const sections = [...template.sections]
    const newIndex = direction === 'up' ? index - 1 : index + 1

    if (newIndex < 0 || newIndex >= sections.length) return

    const temp = sections[index]
    sections[index] = sections[newIndex]
    sections[newIndex] = temp

    setTemplate({
      ...template,
      sections,
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (error || !template) {
    return (
      <div className="text-center py-12">
        <CogIcon className="mx-auto h-12 w-12 text-gray-400" />
        <h3 className="mt-2 text-sm font-medium text-gray-900">
          Template not found
        </h3>
        <p className="mt-1 text-sm text-gray-500">
          {error || 'The template you are looking for does not exist.'}
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
      {/* Header */}
      <div className="bg-white shadow">
        <div className="px-4 sm:px-6 lg:max-w-6xl lg:mx-auto lg:px-8">
          <div className="py-6 md:flex md:items-center md:justify-between lg:border-t lg:border-gray-200">
            <div className="flex-1 min-w-0">
              <div className="flex items-center">
                <CogIcon className="h-8 w-8 text-gray-400 mr-3" />
                <div>
                  <h1 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                    {template.name}
                  </h1>
                  <div className="mt-1 flex items-center text-sm text-gray-500">
                    <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full">
                      {template.projectType.replace('_', ' ')}
                    </span>
                    <span className="mx-2">•</span>
                    <span>{template.sections?.length || 0} sections</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-4 flex md:mt-0 md:ml-4 space-x-3">
              <button
                onClick={() => setShowPreview(!showPreview)}
                className={`inline-flex items-center px-4 py-2 border text-sm font-medium rounded-md ${
                  showPreview
                    ? 'border-primary-300 text-primary-700 bg-primary-50'
                    : 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
                }`}
              >
                <EyeIcon className="h-4 w-4 mr-2" />
                {showPreview ? 'Hide Preview' : 'Show Preview'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mt-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Add Section Button */}
          <div className="mb-6">
            {isAddingSection ? (
              <div className="bg-white shadow rounded-lg p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                  Add New Section
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Section Title
                    </label>
                    <input
                      type="text"
                      value={editContent.title}
                      onChange={(e) =>
                        setEditContent({
                          ...editContent,
                          title: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500"
                      placeholder="Enter section title"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700">
                        Content Type
                      </label>
                      <select
                        value={editContent.contentType}
                        onChange={(e) =>
                          setEditContent({
                            ...editContent,
                            contentType: e.target.value,
                          })
                        }
                        className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500"
                      >
                        <option value="static">Static</option>
                        <option value="dynamic">Dynamic</option>
                        <option value="structured">Structured</option>
                      </select>
                    </div>
                    <div className="flex items-center">
                      <input
                        type="checkbox"
                        checked={editContent.required}
                        onChange={(e) =>
                          setEditContent({
                            ...editContent,
                            required: e.target.checked,
                          })
                        }
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                      />
                      <label className="ml-2 block text-sm text-gray-900">
                        Required Section
                      </label>
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Template Content
                    </label>
                    <TextEditor
                      value={editContent.content || ''}
                      onChange={(content) =>
                        setEditContent({ ...editContent, content })
                      }
                      placeholder="Enter template content with placeholders like {{company_name}}, {{project_description}}, etc."
                      className="mt-1"
                    />
                  </div>
                  <div className="flex items-center space-x-3">
                    <button
                      onClick={saveSection}
                      disabled={!editContent.title.trim() || saving}
                      className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                    >
                      {saving ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                      ) : (
                        <CheckIcon className="h-4 w-4 mr-2" />
                      )}
                      Add Section
                    </button>
                    <button
                      onClick={() => {
                        setIsAddingSection(false)
                        setEditContent({
                          title: '',
                          contentType: 'static',
                          required: true,
                        })
                      }}
                      className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
                    >
                      <XMarkIcon className="h-4 w-4 mr-2" />
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <button
                onClick={() => {
                  setIsAddingSection(true)
                  setEditingSection(null)
                  setEditContent({
                    title: '',
                    contentType: 'static',
                    required: true,
                  })
                }}
                className="inline-flex items-center px-4 py-2 border border-dashed border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
              >
                <PlusIcon className="h-4 w-4 mr-2" />
                Add Section
              </button>
            )}
          </div>

          {/* Template Sections */}
          <div className="space-y-6">
            {template.sections?.map(
              (section: TemplateSection, index: number) => (
                <div key={index} className="bg-white shadow rounded-lg">
                  <div className="px-6 py-4 border-b border-gray-200">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <h3 className="text-lg font-medium text-gray-900">
                          {section.title}
                        </h3>
                        <span
                          className={`px-2 py-1 text-xs font-medium rounded-full ${
                            section.contentType === 'dynamic'
                              ? 'bg-green-100 text-green-800'
                              : section.contentType === 'structured'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}
                        >
                          {section.contentType}
                        </span>
                        {section.required && (
                          <span className="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800">
                            Required
                          </span>
                        )}
                      </div>
                      <div className="flex items-center space-x-1">
                        <button
                          onClick={() => moveSection(index, 'up')}
                          disabled={index === 0}
                          className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
                          title="Move up"
                        >
                          <ArrowUpIcon className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => moveSection(index, 'down')}
                          disabled={index === template.sections.length - 1}
                          className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
                          title="Move down"
                        >
                          <ArrowDownIcon className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => startEdit(index)}
                          className="p-1 text-gray-400 hover:text-gray-600"
                          title="Edit section"
                        >
                          <PencilSquareIcon className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => deleteSection(index)}
                          className="p-1 text-gray-400 hover:text-red-600"
                          title="Delete section"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                  <div className="px-6 py-4">
                    {editingSection === index ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium text-gray-700">
                              Section Title
                            </label>
                            <input
                              type="text"
                              value={editContent.title}
                              onChange={(e) =>
                                setEditContent({
                                  ...editContent,
                                  title: e.target.value,
                                })
                              }
                              className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700">
                              Content Type
                            </label>
                            <select
                              value={editContent.contentType}
                              onChange={(e) =>
                                setEditContent({
                                  ...editContent,
                                  contentType: e.target.value,
                                })
                              }
                              className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500"
                            >
                              <option value="static">Static</option>
                              <option value="dynamic">Dynamic</option>
                              <option value="structured">Structured</option>
                            </select>
                          </div>
                        </div>
                        <div className="flex items-center">
                          <input
                            type="checkbox"
                            checked={editContent.required}
                            onChange={(e) =>
                              setEditContent({
                                ...editContent,
                                required: e.target.checked,
                              })
                            }
                            className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                          />
                          <label className="ml-2 block text-sm text-gray-900">
                            Required Section
                          </label>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700">
                            Template Content
                          </label>
                          <TextEditor
                            value={editContent.content || ''}
                            onChange={(content) =>
                              setEditContent({ ...editContent, content })
                            }
                            placeholder="Enter template content with placeholders..."
                            className="mt-1"
                          />
                        </div>
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
                        <div className="text-sm text-gray-600 mb-2">
                          {section.components && (
                            <div className="mb-2">
                              <span className="font-medium">Components:</span>{' '}
                              {section.components.join(', ')}
                            </div>
                          )}
                          {section.subsections && (
                            <div className="mb-2">
                              <span className="font-medium">Subsections:</span>{' '}
                              {section.subsections.join(', ')}
                            </div>
                          )}
                        </div>
                        {section.content && (
                          <div className="mt-3 p-3 bg-gray-50 rounded-md">
                            <div
                              className="text-sm text-gray-700 prose max-w-none"
                              dangerouslySetInnerHTML={{
                                __html: section.content
                                  .replace(
                                    /\*\*(.*?)\*\*/g,
                                    '<strong>$1</strong>',
                                  )
                                  .replace(/\*(.*?)\*/g, '<em>$1</em>')
                                  .replace(/\n/g, '<br>')
                                  .replace(
                                    /\{\{(.*?)\}\}/g,
                                    '<span class="bg-yellow-100 text-yellow-800 px-1 rounded">{{$1}}</span>',
                                  ),
                              }}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ),
            )}
          </div>

          {(!template.sections || template.sections.length === 0) && (
            <div className="text-center py-12 bg-white shadow rounded-lg">
              <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">
                No Sections
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                This template has no sections yet.
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
    </div>
  )
}
