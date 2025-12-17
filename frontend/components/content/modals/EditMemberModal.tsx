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

type EditMemberModalProps = {
  open: boolean
  memberForm: any
  setMemberForm: (v: any) => void
  onSave: () => void
  onClose: () => void
}

export default function EditMemberModal({
  open,
  memberForm,
  setMemberForm,
  onSave,
  onClose,
}: EditMemberModalProps) {
  const [companies, setCompanies] = useState<any[]>([])
  const [loadingCompanies, setLoadingCompanies] = useState(false)
  const [headshotUploading, setHeadshotUploading] = useState(false)
  const [headshotUploadError, setHeadshotUploadError] = useState<string | null>(
    null,
  )
  const [headshotPreviewUrl, setHeadshotPreviewUrl] = useState<string>('')

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

  useEffect(() => {
    return () => {
      if (headshotPreviewUrl) URL.revokeObjectURL(headshotPreviewUrl)
    }
  }, [headshotPreviewUrl])

  const uploadHeadshotFile = async (file: File) => {
    if (!file) return
    setHeadshotUploadError(null)
    setHeadshotUploading(true)

    // Client-side safety checks
    const maxBytes = 5 * 1024 * 1024 // 5MB
    const isImage = file.type?.startsWith('image/')
    if (!isImage) {
      setHeadshotUploading(false)
      setHeadshotUploadError('Please choose an image file (jpg/png/webp).')
      return
    }
    if (file.size > maxBytes) {
      setHeadshotUploading(false)
      setHeadshotUploadError('Image is too large. Max size is 5MB.')
      return
    }

    const localPreview = URL.createObjectURL(file)
    setHeadshotPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return localPreview
    })

    try {
      const contentType = file.type || 'application/octet-stream'
      const resp = await api.post('/api/content/team/headshot/presign', {
        fileName: file.name,
        contentType,
        memberId: memberForm?.memberId || undefined,
      })
      const { putUrl, key, s3Uri } = resp.data || {}
      if (!putUrl || !key) throw new Error('Upload URL missing from response')

      const putResp = await fetch(String(putUrl), {
        method: 'PUT',
        headers: {
          'Content-Type': contentType,
        },
        body: file,
      })

      if (!putResp.ok) {
        throw new Error(`S3 upload failed (${putResp.status})`)
      }

      setMemberForm((prev: any) => ({
        ...prev,
        headshotS3Key: String(key),
        headshotS3Uri: s3Uri ? String(s3Uri) : prev?.headshotS3Uri,
      }))
    } catch (e: any) {
      console.error('Headshot upload error:', e)
      setHeadshotUploadError(e?.message || 'Failed to upload headshot')
    } finally {
      setHeadshotUploading(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white max-h-[80vh] overflow-y-auto">
        <div className="mb-4">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Edit Team Member
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
                Headshot
              </label>

              <div className="mt-1 flex items-center gap-3">
                <input
                  type="file"
                  accept="image/*"
                  disabled={headshotUploading}
                  onChange={(e) => {
                    const f = e.currentTarget.files?.[0]
                    if (f) uploadHeadshotFile(f)
                    // allow re-selecting the same file
                    e.currentTarget.value = ''
                  }}
                  className="block w-full text-sm"
                />
                {memberForm?.headshotS3Key && (
                  <button
                    type="button"
                    onClick={() => {
                      setMemberForm((prev: any) => ({
                        ...prev,
                        headshotS3Key: null,
                        headshotS3Uri: null,
                      }))
                      setHeadshotPreviewUrl((prev) => {
                        if (prev) URL.revokeObjectURL(prev)
                        return ''
                      })
                    }}
                    className="px-3 py-2 text-xs rounded bg-gray-100 hover:bg-gray-200"
                    disabled={headshotUploading}
                  >
                    Remove
                  </button>
                )}
              </div>

              {(headshotPreviewUrl || memberForm?.headshotUrl) && (
                <div className="mt-2 flex items-center gap-3">
                  <img
                    src={headshotPreviewUrl || memberForm.headshotUrl}
                    alt="Headshot preview"
                    className="h-12 w-12 rounded-full object-cover border"
                    onError={(e) => {
                      ;(e.currentTarget as HTMLImageElement).style.display =
                        'none'
                    }}
                  />
                  <div className="text-xs text-gray-500">
                    <div>
                      {headshotUploading
                        ? 'Uploading…'
                        : memberForm?.headshotS3Key
                        ? 'Uploaded. Click “Save Changes” to persist.'
                        : 'Upload an image or paste a URL below.'}
                    </div>
                    {headshotUploadError && (
                      <div className="text-red-600 mt-1">
                        {headshotUploadError}
                      </div>
                    )}
                  </div>
                </div>
              )}

              <label className="block text-xs font-medium text-gray-600 mt-3">
                Headshot URL (optional)
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
                          ✕
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
            onClick={onSave}
            className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}
