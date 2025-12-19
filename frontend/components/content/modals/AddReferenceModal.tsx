type AddReferenceModalProps = {
  open: boolean
  referenceForm: any
  setReferenceForm: (v: any) => void
  companies?: any[]
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

export default function AddReferenceModal({
  open,
  referenceForm,
  setReferenceForm,
  companies = [],
  addArrayItem,
  updateArrayItem,
  removeArrayItem,
  onAdd,
  onClose,
}: AddReferenceModalProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white max-h-[80vh] overflow-y-auto">
        <div className="mb-4">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Add Client Reference
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Company
              </label>
              <select
                value={referenceForm.companyId || ''}
                onChange={(e) =>
                  setReferenceForm({
                    ...referenceForm,
                    companyId: e.target.value || null,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 bg-white"
              >
                <option value="">Unassigned</option>
                {(companies || []).map((c: any) => (
                  <option key={c.companyId} value={c.companyId}>
                    {c.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                References roll up to the selected company for capability
                generation.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Organization Name
                </label>
                <input
                  type="text"
                  value={referenceForm.organizationName}
                  onChange={(e) =>
                    setReferenceForm({
                      ...referenceForm,
                      organizationName: e.target.value,
                    })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                  placeholder="e.g., Rend Lake Conservancy District"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Time Period
                </label>
                <input
                  type="text"
                  value={referenceForm.timePeriod}
                  onChange={(e) =>
                    setReferenceForm({
                      ...referenceForm,
                      timePeriod: e.target.value,
                    })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                  placeholder="e.g., (2022-2025)"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Contact Name & Credentials
              </label>
              <input
                type="text"
                value={referenceForm.contactName}
                onChange={(e) =>
                  setReferenceForm({
                    ...referenceForm,
                    contactName: e.target.value,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="e.g., Gary Williams, MPA"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Contact Title/Position
              </label>
              <input
                type="text"
                value={referenceForm.contactTitle}
                onChange={(e) =>
                  setReferenceForm({
                    ...referenceForm,
                    contactTitle: e.target.value,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="e.g., General Manager (CEO) of the Rend Lake Conservancy District"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Additional Title/Background (Optional)
              </label>
              <input
                type="text"
                value={referenceForm.additionalTitle}
                onChange={(e) =>
                  setReferenceForm({
                    ...referenceForm,
                    additionalTitle: e.target.value,
                  })
                }
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="e.g., Former City Manager - City of Carbondale"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Email
                </label>
                <input
                  type="email"
                  value={referenceForm.contactEmail}
                  onChange={(e) =>
                    setReferenceForm({
                      ...referenceForm,
                      contactEmail: e.target.value,
                    })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                  placeholder="e.g., gm@rendlake.org"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Phone
                </label>
                <input
                  type="tel"
                  value={referenceForm.contactPhone}
                  onChange={(e) =>
                    setReferenceForm({
                      ...referenceForm,
                      contactPhone: e.target.value,
                    })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                  placeholder="e.g., (618) 439-4321"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Scope of Work
              </label>
              <textarea
                value={referenceForm.scopeOfWork}
                onChange={(e) =>
                  setReferenceForm({
                    ...referenceForm,
                    scopeOfWork: e.target.value,
                  })
                }
                rows={5}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                placeholder="Describe the work performed, achievements, recognition, etc. (e.g., Received honors for work as Primary Author of the City of Carbondale's Sustainability Plan...)"
              />
            </div>

            <div>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={referenceForm.isPublic}
                  onChange={(e) =>
                    setReferenceForm({
                      ...referenceForm,
                      isPublic: e.target.checked,
                    })
                  }
                  className="mr-2"
                />
                <span className="text-sm text-gray-700">
                  Make this reference publicly visible
                </span>
              </label>
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
            Add Reference
          </button>
        </div>
      </div>
    </div>
  )
}
