import { TrashIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'
import api from '../../../lib/api'

function ensureBulletText(value: string) {
  const v = String(value || '')
  if (!v) return ''
  if (v.startsWith('• ')) return v
  return '• ' + v
}

function defaultProfile() {
  return {
    id: `profile_${Date.now()}`,
    label: 'Tailored bio',
    projectTypes: [],
    bio: '• ',
    experience: '• ',
  }
}

type AddMemberModalProps = {
  open: boolean
  memberForm: any
  setMemberForm: (v: any) => void
  addArrayItem: (field: string, setState: any, state: any) => void
  updateArrayItem: (
    field: string,
    index: number,
    value: string,
    setState: any,
    state: any,
  ) => void
  removeArrayItem: (
    field: string,
    index: number,
    setState: any,
    state: any,
  ) => void
  onAdd: () => void
  onClose: () => void
}

export default function AddMemberModal({
  open,
  memberForm,
  setMemberForm,
  addArrayItem,
  updateArrayItem,
  removeArrayItem,
  onAdd,
  onClose,
}: AddMemberModalProps) {
  const [companies, setCompanies] = useState<any[]>([])
  const [loadingCompanies, setLoadingCompanies] = useState(false)

  // Fetch companies when modal opens
  useEffect(() => {
    if (open) {
      fetchCompanies()
    }
  }, [open])

  const fetchCompanies = async () => {
    try {
      setLoadingCompanies(true)
      const response = await api.get('/api/content/companies')
      setCompanies(response.data || [])
    } catch (error) {
      console.error('Error fetching companies:', error)
      setCompanies([])
    } finally {
      setLoadingCompanies(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white max-h-[80vh] overflow-y-auto">
        <div className="mb-4">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Add Team Member
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Name & Credentials
              </label>
              <input
                type="text"
                value={memberForm.nameWithCredentials}
                onChange={(e) =>
                  setMemberForm({
                    ...memberForm,
                    nameWithCredentials: e.target.value,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="e.g., Saxon Metzger, MBA"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Position/Title
              </label>
              <input
                type="text"
                value={memberForm.position}
                onChange={(e) =>
                  setMemberForm({
                    ...memberForm,
                    position: e.target.value,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="e.g., Project Manager"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Email
              </label>
              <input
                type="email"
                value={memberForm.email || ''}
                onChange={(e) =>
                  setMemberForm({
                    ...memberForm,
                    email: e.target.value,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="e.g., saxon.metzger@example.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Company
              </label>
              <select
                value={memberForm.companyId || ''}
                onChange={(e) =>
                  setMemberForm({
                    ...memberForm,
                    companyId: e.target.value || null,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 bg-white"
                disabled={loadingCompanies}
              >
                <option value="">No Company</option>
                {companies.map((company) => (
                  <option key={company.companyId} value={company.companyId}>
                    {company.name}
                    {company.sharedInfo ? ' 🔗' : ''}
                  </option>
                ))}
              </select>
              {loadingCompanies && (
                <p className="text-xs text-gray-500 mt-1">
                  Loading companies...
                </p>
              )}
              {!loadingCompanies && companies.length === 0 && (
                <p className="text-xs text-gray-500 mt-1">
                  No companies available
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Headshot URL
              </label>
              <input
                type="url"
                value={memberForm.headshotUrl || ''}
                onChange={(e) =>
                  setMemberForm({
                    ...memberForm,
                    headshotUrl: e.target.value,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="https://..."
              />
              {memberForm.headshotUrl && (
                <div className="mt-2 flex items-center gap-3">
                  <img
                    src={memberForm.headshotUrl}
                    alt="Headshot preview"
                    className="h-12 w-12 rounded-full object-cover border"
                    onError={(e) => {
                      ;(e.currentTarget as HTMLImageElement).style.display =
                        'none'
                    }}
                  />
                  <p className="text-xs text-gray-500">
                    Used in team profiles and Canva headshot autofill.
                  </p>
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Professional Biography (Bullet Points)
              </label>
              <textarea
                value={memberForm.biography}
                onChange={(e) => {
                  setMemberForm({
                    ...memberForm,
                    biography: ensureBulletText(e.target.value),
                  })
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    const textarea = e.target as HTMLTextAreaElement
                    const cursorPosition = textarea.selectionStart
                    const currentValue = memberForm.biography || ''

                    // Insert new line with bullet point
                    const newValue =
                      currentValue.slice(0, cursorPosition) +
                      '\n• ' +
                      currentValue.slice(cursorPosition)

                    setMemberForm({
                      ...memberForm,
                      biography: newValue,
                    })

                    // Set cursor position after the bullet point
                    setTimeout(() => {
                      textarea.selectionStart = textarea.selectionEnd =
                        cursorPosition + 3
                    }, 0)
                  }
                }}
                onFocus={(e) => {
                  const textarea = e.target as HTMLTextAreaElement
                  // If empty, start with a bullet point
                  if (!memberForm.biography) {
                    setMemberForm({
                      ...memberForm,
                      biography: '• ',
                    })
                    setTimeout(() => {
                      textarea.selectionStart = textarea.selectionEnd = 2
                    }, 0)
                  }
                }}
                rows={8}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 font-mono"
                placeholder="• Start typing here..."
              />
              <p className="text-xs text-gray-500 mt-1">
                Press Enter to automatically create a new bullet point
              </p>
            </div>

            <div className="border-t pt-4">
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium text-gray-700">
                  Tailored bios & experience (by proposal type)
                </label>
                <button
                  type="button"
                  onClick={() =>
                    setMemberForm({
                      ...memberForm,
                      bioProfiles: [
                        ...(Array.isArray(memberForm.bioProfiles)
                          ? memberForm.bioProfiles
                          : []),
                        defaultProfile(),
                      ],
                    })
                  }
                  className="px-3 py-1 text-xs rounded bg-gray-100 hover:bg-gray-200"
                >
                  + Add tailored profile
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                If a profile’s project types match the RFP’s projectType, we’ll
                automatically use that bio/experience in proposals.
              </p>

              {(Array.isArray(memberForm.bioProfiles)
                ? memberForm.bioProfiles
                : []
              ).length === 0 ? (
                <p className="text-sm text-gray-500 mt-3">
                  No tailored profiles yet.
                </p>
              ) : (
                <div className="mt-3 space-y-4">
                  {(memberForm.bioProfiles || []).map((p: any, idx: number) => (
                    <div key={p.id || idx} className="rounded border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <label className="block text-xs font-medium text-gray-700">
                            Label
                          </label>
                          <input
                            type="text"
                            value={p.label || ''}
                            onChange={(e) => {
                              const next = [...(memberForm.bioProfiles || [])]
                              next[idx] = { ...p, label: e.target.value }
                              setMemberForm({
                                ...memberForm,
                                bioProfiles: next,
                              })
                            }}
                            className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                            placeholder="e.g., Software delivery bio"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            const next = [...(memberForm.bioProfiles || [])]
                            next.splice(idx, 1)
                            setMemberForm({ ...memberForm, bioProfiles: next })
                          }}
                          className="mt-6 inline-flex items-center px-2 py-2 text-xs font-medium text-red-600 bg-red-100 rounded hover:bg-red-200"
                          title="Remove profile"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>

                      <div className="mt-3">
                        <label className="block text-xs font-medium text-gray-700">
                          Project types (comma-separated)
                        </label>
                        <input
                          type="text"
                          value={
                            Array.isArray(p.projectTypes)
                              ? p.projectTypes.join(', ')
                              : ''
                          }
                          onChange={(e) => {
                            const raw = e.target.value
                            const types = raw
                              .split(',')
                              .map((s) => s.trim())
                              .filter(Boolean)
                            const next = [...(memberForm.bioProfiles || [])]
                            next[idx] = { ...p, projectTypes: types }
                            setMemberForm({ ...memberForm, bioProfiles: next })
                          }}
                          className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                          placeholder="software_development, strategic_communications"
                        />
                      </div>

                      <div className="mt-3">
                        <label className="block text-xs font-medium text-gray-700">
                          Tailored bio (bullet points)
                        </label>
                        <textarea
                          rows={6}
                          value={p.bio || ''}
                          onChange={(e) => {
                            const next = [...(memberForm.bioProfiles || [])]
                            next[idx] = {
                              ...p,
                              bio: ensureBulletText(e.target.value),
                            }
                            setMemberForm({ ...memberForm, bioProfiles: next })
                          }}
                          className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 font-mono text-sm"
                          placeholder="• ..."
                        />
                      </div>

                      <div className="mt-3">
                        <label className="block text-xs font-medium text-gray-700">
                          Relevant experience (bullet points)
                        </label>
                        <textarea
                          rows={6}
                          value={p.experience || ''}
                          onChange={(e) => {
                            const next = [...(memberForm.bioProfiles || [])]
                            next[idx] = {
                              ...p,
                              experience: ensureBulletText(e.target.value),
                            }
                            setMemberForm({ ...memberForm, bioProfiles: next })
                          }}
                          className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 font-mono text-sm"
                          placeholder="• ..."
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="flex justify-end space-x-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400"
          >
            Cancel
          </button>
          <button
            onClick={onAdd}
            className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
          >
            Add Member
          </button>
        </div>
      </div>
    </div>
  )
}
