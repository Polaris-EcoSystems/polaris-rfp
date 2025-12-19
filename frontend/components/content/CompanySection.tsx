import { contentApi } from '@/lib/api'
import {
  BuildingOfficeIcon,
  CheckIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useState } from 'react'
import AddCompanyModal from './modals/AddCompanyModal'

function parseEvidenceTokens(
  input: string,
): Array<
  | { kind: 'text'; value: string }
  | { kind: 'token'; tokenType: 'project' | 'reference'; id: string }
> {
  const s = String(input || '')
  if (!s) return [{ kind: 'text', value: '' }]

  const re = /\[\[(project|reference):([^\]]+)\]\]/g
  const parts: Array<
    | { kind: 'text'; value: string }
    | { kind: 'token'; tokenType: 'project' | 'reference'; id: string }
  > = []

  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(s))) {
    const start = m.index
    const end = start + m[0].length
    if (start > last) {
      parts.push({ kind: 'text', value: s.slice(last, start) })
    }
    parts.push({
      kind: 'token',
      tokenType: (m[1] as any) === 'reference' ? 'reference' : 'project',
      id: String(m[2] || '').trim(),
    })
    last = end
  }
  if (last < s.length) {
    parts.push({ kind: 'text', value: s.slice(last) })
  }
  return parts
}

function resolveEvidenceLabel(
  meta: any,
  tokenType: 'project' | 'reference',
  id: string,
) {
  const items = Array.isArray(meta?.evidenceItems) ? meta.evidenceItems : []
  const match = items.find(
    (x: any) =>
      String(x?.type || '').toLowerCase() === tokenType &&
      String(x?.id || '').trim() === String(id || '').trim(),
  )
  const label = String(match?.label || '').trim()
  return (
    label || (tokenType === 'project' ? `Project ${id}` : `Reference ${id}`)
  )
}

// Using a single ctx prop to keep wiring simple during extraction
export default function CompanySection({ ctx }: { ctx: any }) {
  const {
    companies,
    selectedCompany,
    setSelectedCompany,
    editingCompany,
    companyForm,
    setCompanyForm,
    showAddCompany,
    setShowAddCompany,
    handleEditCompany,
    handleSaveCompany,
    handleCancelCompanyEdit,
    handleAddCompany,
    handleDeleteCompany,
    projects,
    references,
    setSelectedProject,
    setSelectedReference,
  } = ctx
  const [isSaving, setIsSaving] = useState(false)
  const [isRegenerating, setIsRegenerating] = useState(false)
  const addArrayItem = (field: string) => {
    setCompanyForm({
      ...companyForm,
      [field]: [...(companyForm[field] || []), ''],
    })
  }

  const updateArrayItem = (field: string, index: number, value: string) => {
    const updated = [...(companyForm[field] || [])]
    updated[index] = value
    setCompanyForm({
      ...companyForm,
      [field]: updated,
    })
  }

  const removeArrayItem = (field: string, index: number) => {
    setCompanyForm({
      ...companyForm,
      [field]: (companyForm[field] || []).filter(
        (_: any, i: number) => i !== index,
      ),
    })
  }

  const handleAddNewCompany = () => {
    setCompanyForm({
      name: '',
      tagline: '',
      description: '',
      founded: '',
      location: '',
      website: '',
      email: '',
      phone: '',
      coreCapabilities: [''],
      certifications: [''],
      industryFocus: [''],
      missionStatement: '',
      visionStatement: '',
      values: [''],
      statistics: {
        yearsInBusiness: '',
        projectsCompleted: '',
        clientsSatisfied: '',
        teamMembers: '',
      },
      socialMedia: {
        linkedin: '',
        twitter: '',
        facebook: '',
      },
      coverLetter: '',
      firmQualificationsAndExperience: '',
    })
    setShowAddCompany(true)
  }
  const onSaveCompany = async () => {
    try {
      setIsSaving(true)
      await handleSaveCompany()
    } catch (error) {
      console.error('Error saving company:', error)
    } finally {
      setIsSaving(false)
    }
  }

  const onRegenerateCapabilities = async () => {
    const companyId = selectedCompany?.companyId
    if (!companyId) return
    try {
      setIsRegenerating(true)
      const resp = await contentApi.regenerateCompanyCapabilities(companyId)
      const updated = resp.data

      // update company list + selected company (keep wiring local to avoid prop explosion)
      if (typeof setSelectedCompany === 'function') {
        setSelectedCompany(updated)
      }
      if (Array.isArray(companies)) {
        const next = companies.map((c: any) =>
          c.companyId === companyId ? updated : c,
        )
        if (typeof ctx?.setCompanies === 'function') {
          ctx.setCompanies(next)
        }
      }
    } catch (e) {
      console.error('Failed to regenerate capabilities statement:', e)
    } finally {
      setIsRegenerating(false)
    }
  }

  const onClickEvidenceToken = async (
    tokenType: 'project' | 'reference',
    id: string,
  ) => {
    const targetId = String(id || '').trim()
    if (!targetId) return

    const scrollTo = (anchorId: string) => {
      try {
        if (typeof window === 'undefined') return
        const el = window.document?.getElementById(anchorId)
        if (!el) return
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      } catch (_e) {
        // ignore
      }
    }

    if (tokenType === 'project') {
      scrollTo('section-projects')
      const list = Array.isArray(projects) ? projects : []
      const found =
        list.find(
          (p: any) => String(p?._id || p?.projectId || '') === targetId,
        ) || null
      if (found && typeof setSelectedProject === 'function') {
        setSelectedProject(found)
        return
      }
      // fallback fetch
      try {
        const resp = await contentApi.getProjectById(targetId)
        if (typeof setSelectedProject === 'function')
          setSelectedProject(resp.data)
        scrollTo('section-projects')
      } catch (_e) {
        // ignore
      }
      return
    }

    scrollTo('section-references')
    const list = Array.isArray(references) ? references : []
    const found =
      list.find(
        (r: any) => String(r?._id || r?.referenceId || '') === targetId,
      ) || null
    if (found && typeof setSelectedReference === 'function') {
      setSelectedReference(found)
      return
    }
    try {
      const resp = await contentApi.getReferenceById(targetId)
      if (typeof setSelectedReference === 'function')
        setSelectedReference(resp.data)
      scrollTo('section-references')
    } catch (_e) {
      // ignore
    }
  }
  return (
    <div className="space-y-6">
      {/* Company Selection and Actions */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-5 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <BuildingOfficeIcon className="h-5 w-5 text-gray-400 mr-2" />
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Company Information ({companies.length})
              </h3>
            </div>
            <div className="flex space-x-2">
              <button
                onClick={handleAddNewCompany}
                className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-white bg-green-600 hover:bg-green-700"
              >
                <PlusIcon className="h-3 w-3 mr-1" />
                Add Company
              </button>
            </div>
          </div>
        </div>

        {/* Company List */}
        <div className="px-6 py-4">
          {companies.length > 0 ? (
            <div className="space-y-3">
              {companies.map((company: any) => (
                <div
                  key={company.companyId}
                  className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                    selectedCompany?.companyId === company.companyId
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                  onClick={() => setSelectedCompany(company)}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">
                        {company.name}
                      </h4>
                      <p className="text-sm text-gray-500 mt-1">
                        {company.location} • Founded{' '}
                        {company.founded
                          ? new Date(company.founded).getFullYear()
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="flex space-x-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedCompany(company)
                          handleEditCompany()
                        }}
                        className="p-1 text-gray-400 hover:text-primary-600"
                      >
                        <PencilIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteCompany(company)
                        }}
                        className="p-1 text-gray-400 hover:text-red-600"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <BuildingOfficeIcon className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">
                No companies
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Get started by adding your first company.
              </p>
              <div className="mt-6">
                <button
                  onClick={handleAddNewCompany}
                  className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700"
                >
                  <PlusIcon className="h-4 w-4 mr-2" />
                  Add Company
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Selected Company Details */}
      {selectedCompany && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-5 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <BuildingOfficeIcon className="h-5 w-5 text-gray-400 mr-2" />
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  {selectedCompany.name}
                </h3>
              </div>
              <div className="flex space-x-2">
                {editingCompany ? (
                  <>
                    <button
                      onClick={onSaveCompany}
                      disabled={isSaving}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-white bg-green-600 hover:bg-green-700"
                    >
                      <CheckIcon className="h-3 w-3 mr-1" />
                      Save
                    </button>
                    <button
                      onClick={handleCancelCompanyEdit}
                      className="inline-flex items-center px-3 py-1 border border-gray-300 text-xs font-medium rounded text-gray-700 bg-white hover:bg-gray-50"
                    >
                      <XMarkIcon className="h-3 w-3 mr-1" />
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={onRegenerateCapabilities}
                      disabled={isRegenerating}
                      className="inline-flex items-center px-3 py-1 border border-gray-300 text-xs font-medium rounded text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-60"
                      title="Regenerate the capabilities statement from projects and references"
                    >
                      {isRegenerating
                        ? 'Regenerating…'
                        : 'Regenerate capabilities'}
                    </button>
                    <button
                      onClick={handleEditCompany}
                      className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-primary-600 bg-primary-100 hover:bg-primary-200"
                    >
                      <PencilIcon className="h-3 w-3 mr-1" />
                      Edit
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="px-6 py-6">
            {editingCompany ? (
              <div className="space-y-6">
                {/* Basic Information */}
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Company Name *
                    </label>
                    <input
                      type="text"
                      value={companyForm.companyName || companyForm.name || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          companyName: e.target.value,
                          name: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Tagline
                    </label>
                    <input
                      type="text"
                      value={companyForm.tagline || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          tagline: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Description *
                  </label>
                  <textarea
                    value={companyForm.description || ''}
                    onChange={(e) =>
                      setCompanyForm({
                        ...companyForm,
                        description: e.target.value,
                      })
                    }
                    rows={3}
                    className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                  />
                </div>

                {/* Company Details */}
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Founded Date
                    </label>
                    <input
                      type="date"
                      value={
                        companyForm.founded
                          ? new Date(companyForm.founded)
                              .toISOString()
                              .split('T')[0]
                          : ''
                      }
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          founded: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Location
                    </label>
                    <input
                      type="text"
                      value={companyForm.location || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          location: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                </div>

                {/* Contact Information */}
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Website
                    </label>
                    <input
                      type="url"
                      value={companyForm.website || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          website: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Email
                    </label>
                    <input
                      type="email"
                      value={companyForm.email || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          email: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Phone
                    </label>
                    <input
                      type="tel"
                      value={companyForm.phone || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          phone: e.target.value,
                        })
                      }
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                </div>

                {/* Core Capabilities */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Core Capabilities
                  </label>
                  <div className="space-y-2">
                    {(companyForm.coreCapabilities || []).map(
                      (capability: string, index: number) => (
                        <div key={index} className="flex space-x-2">
                          <input
                            type="text"
                            value={capability}
                            onChange={(e) =>
                              updateArrayItem(
                                'coreCapabilities',
                                index,
                                e.target.value,
                              )
                            }
                            className="flex-1 border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                            placeholder="Enter capability"
                          />
                          <button
                            onClick={() =>
                              removeArrayItem('coreCapabilities', index)
                            }
                            className="px-3 py-2 text-red-600 hover:text-red-800"
                          >
                            <XMarkIcon className="h-4 w-4" />
                          </button>
                        </div>
                      ),
                    )}
                    <button
                      onClick={() => addArrayItem('coreCapabilities')}
                      className="text-primary-600 hover:text-primary-800 text-sm"
                    >
                      + Add Capability
                    </button>
                  </div>
                </div>

                {/* Certifications */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Certifications
                  </label>
                  <div className="space-y-2">
                    {(companyForm.certifications || []).map(
                      (cert: string, index: number) => (
                        <div key={index} className="flex space-x-2">
                          <input
                            type="text"
                            value={cert}
                            onChange={(e) =>
                              updateArrayItem(
                                'certifications',
                                index,
                                e.target.value,
                              )
                            }
                            className="flex-1 border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                            placeholder="Enter certification"
                          />
                          <button
                            onClick={() =>
                              removeArrayItem('certifications', index)
                            }
                            className="px-3 py-2 text-red-600 hover:text-red-800"
                          >
                            <XMarkIcon className="h-4 w-4" />
                          </button>
                        </div>
                      ),
                    )}
                    <button
                      onClick={() => addArrayItem('certifications')}
                      className="text-primary-600 hover:text-primary-800 text-sm"
                    >
                      + Add Certification
                    </button>
                  </div>
                </div>

                {/* Industry Focus */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Industry Focus
                  </label>
                  <div className="space-y-2">
                    {(companyForm.industryFocus || []).map(
                      (industry: string, index: number) => (
                        <div key={index} className="flex space-x-2">
                          <input
                            type="text"
                            value={industry}
                            onChange={(e) =>
                              updateArrayItem(
                                'industryFocus',
                                index,
                                e.target.value,
                              )
                            }
                            className="flex-1 border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                            placeholder="Enter industry"
                          />
                          <button
                            onClick={() =>
                              removeArrayItem('industryFocus', index)
                            }
                            className="px-3 py-2 text-red-600 hover:text-red-800"
                          >
                            <XMarkIcon className="h-4 w-4" />
                          </button>
                        </div>
                      ),
                    )}
                    <button
                      onClick={() => addArrayItem('industryFocus')}
                      className="text-primary-600 hover:text-primary-800 text-sm"
                    >
                      + Add Industry
                    </button>
                  </div>
                </div>

                {/* Mission & Vision */}
                <div className="grid grid-cols-1 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Mission Statement
                    </label>
                    <textarea
                      value={companyForm.missionStatement || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          missionStatement: e.target.value,
                        })
                      }
                      rows={3}
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Vision Statement
                    </label>
                    <textarea
                      value={companyForm.visionStatement || ''}
                      onChange={(e) =>
                        setCompanyForm({
                          ...companyForm,
                          visionStatement: e.target.value,
                        })
                      }
                      rows={3}
                      className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                </div>

                {/* Values */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Core Values
                  </label>
                  <div className="space-y-2">
                    {(companyForm.values || []).map(
                      (value: string, index: number) => (
                        <div key={index} className="flex space-x-2">
                          <input
                            type="text"
                            value={value}
                            onChange={(e) =>
                              updateArrayItem('values', index, e.target.value)
                            }
                            className="flex-1 border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                            placeholder="Enter value"
                          />
                          <button
                            onClick={() => removeArrayItem('values', index)}
                            className="px-3 py-2 text-red-600 hover:text-red-800"
                          >
                            <XMarkIcon className="h-4 w-4" />
                          </button>
                        </div>
                      ),
                    )}
                    <button
                      onClick={() => addArrayItem('values')}
                      className="text-primary-600 hover:text-primary-800 text-sm"
                    >
                      + Add Value
                    </button>
                  </div>
                </div>

                {/* Statistics */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">
                    Company Statistics
                  </label>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-gray-600">
                        Years in Business
                      </label>
                      <input
                        type="number"
                        value={companyForm.statistics?.yearsInBusiness || ''}
                        onChange={(e) =>
                          setCompanyForm({
                            ...companyForm,
                            statistics: {
                              ...companyForm.statistics,
                              yearsInBusiness: e.target.value,
                            },
                          })
                        }
                        className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600">
                        Projects Completed
                      </label>
                      <input
                        type="number"
                        value={companyForm.statistics?.projectsCompleted || ''}
                        onChange={(e) =>
                          setCompanyForm({
                            ...companyForm,
                            statistics: {
                              ...companyForm.statistics,
                              projectsCompleted: e.target.value,
                            },
                          })
                        }
                        className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600">
                        Clients Satisfied
                      </label>
                      <input
                        type="number"
                        value={companyForm.statistics?.clientsSatisfied || ''}
                        onChange={(e) =>
                          setCompanyForm({
                            ...companyForm,
                            statistics: {
                              ...companyForm.statistics,
                              clientsSatisfied: e.target.value,
                            },
                          })
                        }
                        className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600">
                        Team Members
                      </label>
                      <input
                        type="number"
                        value={companyForm.statistics?.teamMembers || ''}
                        onChange={(e) =>
                          setCompanyForm({
                            ...companyForm,
                            statistics: {
                              ...companyForm.statistics,
                              teamMembers: e.target.value,
                            },
                          })
                        }
                        className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                  </div>
                </div>

                {/* Social Media */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">
                    Social Media
                  </label>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-600">
                        LinkedIn
                      </label>
                      <input
                        type="url"
                        value={companyForm.socialMedia?.linkedin || ''}
                        onChange={(e) =>
                          setCompanyForm({
                            ...companyForm,
                            socialMedia: {
                              ...companyForm.socialMedia,
                              linkedin: e.target.value,
                            },
                          })
                        }
                        className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600">
                        Twitter
                      </label>
                      <input
                        type="url"
                        value={companyForm.socialMedia?.twitter || ''}
                        onChange={(e) =>
                          setCompanyForm({
                            ...companyForm,
                            socialMedia: {
                              ...companyForm.socialMedia,
                              twitter: e.target.value,
                            },
                          })
                        }
                        className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600">
                        Facebook
                      </label>
                      <input
                        type="url"
                        value={companyForm.socialMedia?.facebook || ''}
                        onChange={(e) =>
                          setCompanyForm({
                            ...companyForm,
                            socialMedia: {
                              ...companyForm.socialMedia,
                              facebook: e.target.value,
                            },
                          })
                        }
                        className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                      />
                    </div>
                  </div>
                </div>

                {/* Cover Letter */}
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Cover Letter
                  </label>
                  <textarea
                    value={companyForm.coverLetter || ''}
                    onChange={(e) =>
                      setCompanyForm({
                        ...companyForm,
                        coverLetter: e.target.value,
                      })
                    }
                    rows={6}
                    className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    placeholder="Enter your company's cover letter template..."
                  />
                </div>

                {/* Firm Qualifications and Experience */}
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    Firm Qualifications and Experience
                  </label>
                  <textarea
                    value={companyForm.firmQualificationsAndExperience || ''}
                    onChange={(e) =>
                      setCompanyForm({
                        ...companyForm,
                        firmQualificationsAndExperience: e.target.value,
                      })
                    }
                    rows={8}
                    className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-primary-500 focus:border-primary-500"
                    placeholder="Describe your firm's qualifications, experience, and expertise..."
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                <div>
                  <h4 className="text-lg font-medium text-gray-900">
                    {selectedCompany.name}
                  </h4>
                  {selectedCompany.tagline && (
                    <p className="text-sm text-gray-600 mt-1">
                      {selectedCompany.tagline}
                    </p>
                  )}
                  <p className="text-sm text-gray-600 mt-2">
                    {selectedCompany.description}
                  </p>
                </div>

                <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <h5 className="text-sm font-medium text-gray-900">
                      Capabilities Statement
                    </h5>
                    <div className="text-xs text-gray-500">
                      {selectedCompany?.capabilitiesStatementMeta?.generatedAt
                        ? `Updated ${new Date(
                            selectedCompany.capabilitiesStatementMeta.generatedAt,
                          ).toLocaleString()}`
                        : 'Not generated yet'}
                    </div>
                  </div>
                  <div className="mt-3 text-sm text-gray-700 whitespace-pre-wrap">
                    {(selectedCompany.capabilitiesStatement
                      ? parseEvidenceTokens(
                          selectedCompany.capabilitiesStatement,
                        )
                      : [
                          {
                            kind: 'text' as const,
                            value:
                              'Add past projects and references to generate a capabilities statement for this company.',
                          },
                        ]
                    ).map((p, idx) => {
                      if (p.kind === 'text')
                        return <span key={idx}>{p.value}</span>
                      const label = resolveEvidenceLabel(
                        selectedCompany?.capabilitiesStatementMeta,
                        p.tokenType,
                        p.id,
                      )
                      return (
                        <button
                          key={`${p.tokenType}:${p.id}:${idx}`}
                          type="button"
                          onClick={() =>
                            onClickEvidenceToken(p.tokenType, p.id)
                          }
                          className="mx-0.5 inline-flex items-center rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-gray-700 hover:bg-gray-100"
                          title={`Jump to ${p.tokenType} ${p.id}`}
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Founded
                    </h5>
                    <p className="text-sm text-gray-900">
                      {selectedCompany.founded
                        ? new Date(selectedCompany.founded).getFullYear()
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Location
                    </h5>
                    <p className="text-sm text-gray-900">
                      {selectedCompany.location || 'N/A'}
                    </p>
                  </div>
                </div>

                {(selectedCompany.website ||
                  selectedCompany.email ||
                  selectedCompany.phone) && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Contact Information
                    </h5>
                    <div className="space-y-1">
                      {selectedCompany.website && (
                        <p className="text-sm text-gray-900">
                          <span className="font-medium">Website:</span>
                          <a
                            href={selectedCompany.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary-600 hover:text-primary-800 ml-1"
                          >
                            {selectedCompany.website}
                          </a>
                        </p>
                      )}
                      {selectedCompany.email && (
                        <p className="text-sm text-gray-900">
                          <span className="font-medium">Email:</span>
                          <a
                            href={`mailto:${selectedCompany.email}`}
                            className="text-primary-600 hover:text-primary-800 ml-1"
                          >
                            {selectedCompany.email}
                          </a>
                        </p>
                      )}
                      {selectedCompany.phone && (
                        <p className="text-sm text-gray-900">
                          <span className="font-medium">Phone:</span>
                          <a
                            href={`tel:${selectedCompany.phone}`}
                            className="text-primary-600 hover:text-primary-800 ml-1"
                          >
                            {selectedCompany.phone}
                          </a>
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {selectedCompany.coreCapabilities &&
                  selectedCompany.coreCapabilities.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Core Capabilities
                      </h5>
                      <div className="flex flex-wrap gap-2">
                        {selectedCompany.coreCapabilities.map(
                          (capability: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded-full"
                            >
                              {capability}
                            </span>
                          ),
                        )}
                      </div>
                    </div>
                  )}

                {selectedCompany.certifications &&
                  selectedCompany.certifications.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Certifications
                      </h5>
                      <div className="flex flex-wrap gap-2">
                        {selectedCompany.certifications.map(
                          (cert: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full"
                            >
                              {cert}
                            </span>
                          ),
                        )}
                      </div>
                    </div>
                  )}

                {selectedCompany.industryFocus &&
                  selectedCompany.industryFocus.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Industry Focus
                      </h5>
                      <div className="flex flex-wrap gap-2">
                        {selectedCompany.industryFocus.map(
                          (industry: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs font-medium bg-purple-100 text-purple-800 rounded-full"
                            >
                              {industry}
                            </span>
                          ),
                        )}
                      </div>
                    </div>
                  )}

                {selectedCompany.missionStatement && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Mission Statement
                    </h5>
                    <p className="text-sm text-gray-700">
                      {selectedCompany.missionStatement}
                    </p>
                  </div>
                )}

                {selectedCompany.visionStatement && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Vision Statement
                    </h5>
                    <p className="text-sm text-gray-700">
                      {selectedCompany.visionStatement}
                    </p>
                  </div>
                )}

                {selectedCompany.values &&
                  selectedCompany.values.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Core Values
                      </h5>
                      <ul className="space-y-1">
                        {selectedCompany.values.map(
                          (value: string, index: number) => (
                            <li
                              key={index}
                              className="flex items-start space-x-2"
                            >
                              <div className="w-2 h-2 bg-primary-600 rounded-full mt-2 flex-shrink-0"></div>
                              <span className="text-sm text-gray-700">
                                {value}
                              </span>
                            </li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}

                {selectedCompany.statistics && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Company Statistics
                    </h5>
                    <div className="grid grid-cols-2 gap-4">
                      {selectedCompany.statistics.yearsInBusiness && (
                        <div>
                          <span className="text-sm font-medium text-gray-600">
                            Years in Business:
                          </span>
                          <span className="text-sm text-gray-900 ml-1">
                            {selectedCompany.statistics.yearsInBusiness}
                          </span>
                        </div>
                      )}
                      {selectedCompany.statistics.projectsCompleted && (
                        <div>
                          <span className="text-sm font-medium text-gray-600">
                            Projects Completed:
                          </span>
                          <span className="text-sm text-gray-900 ml-1">
                            {selectedCompany.statistics.projectsCompleted}
                          </span>
                        </div>
                      )}
                      {selectedCompany.statistics.clientsSatisfied && (
                        <div>
                          <span className="text-sm font-medium text-gray-600">
                            Clients Satisfied:
                          </span>
                          <span className="text-sm text-gray-900 ml-1">
                            {selectedCompany.statistics.clientsSatisfied}
                          </span>
                        </div>
                      )}
                      {selectedCompany.statistics.teamMembers && (
                        <div>
                          <span className="text-sm font-medium text-gray-600">
                            Team Members:
                          </span>
                          <span className="text-sm text-gray-900 ml-1">
                            {selectedCompany.statistics.teamMembers}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {selectedCompany.socialMedia &&
                  (selectedCompany.socialMedia.linkedin ||
                    selectedCompany.socialMedia.twitter ||
                    selectedCompany.socialMedia.facebook) && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Social Media
                      </h5>
                      <div className="space-y-1">
                        {selectedCompany.socialMedia.linkedin && (
                          <p className="text-sm text-gray-900">
                            <span className="font-medium">LinkedIn:</span>
                            <a
                              href={selectedCompany.socialMedia.linkedin}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary-600 hover:text-primary-800 ml-1"
                            >
                              {selectedCompany.socialMedia.linkedin}
                            </a>
                          </p>
                        )}
                        {selectedCompany.socialMedia.twitter && (
                          <p className="text-sm text-gray-900">
                            <span className="font-medium">Twitter:</span>
                            <a
                              href={selectedCompany.socialMedia.twitter}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary-600 hover:text-primary-800 ml-1"
                            >
                              {selectedCompany.socialMedia.twitter}
                            </a>
                          </p>
                        )}
                        {selectedCompany.socialMedia.facebook && (
                          <p className="text-sm text-gray-900">
                            <span className="font-medium">Facebook:</span>
                            <a
                              href={selectedCompany.socialMedia.facebook}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary-600 hover:text-primary-800 ml-1"
                            >
                              {selectedCompany.socialMedia.facebook}
                            </a>
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                {selectedCompany.coverLetter && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Cover Letter
                    </h5>
                    <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 p-4 rounded-md">
                      {selectedCompany.coverLetter}
                    </div>
                  </div>
                )}

                {selectedCompany.firmQualificationsAndExperience && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Firm Qualifications and Experience
                    </h5>
                    <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 p-4 rounded-md">
                      {selectedCompany.firmQualificationsAndExperience}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Company Modal */}
      <AddCompanyModal
        showAddCompany={showAddCompany}
        setShowAddCompany={setShowAddCompany}
        companyForm={companyForm}
        setCompanyForm={setCompanyForm}
        handleAddCompany={handleAddCompany}
        addArrayItem={addArrayItem}
        updateArrayItem={updateArrayItem}
        removeArrayItem={removeArrayItem}
      />
    </div>
  )
}
