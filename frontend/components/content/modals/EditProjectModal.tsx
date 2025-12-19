type EditProjectModalProps = {
  open: boolean
  projectForm: any
  setProjectForm: (v: any) => void
  companies?: any[]
  onSave: () => void
  onClose: () => void
}

export default function EditProjectModal({
  open,
  projectForm,
  setProjectForm,
  companies = [],
  onSave,
  onClose,
}: EditProjectModalProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white max-h-[80vh] overflow-y-auto">
        <div className="mb-4">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Edit Project
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Company
              </label>
              <select
                value={projectForm.companyId || ''}
                onChange={(e) =>
                  setProjectForm({
                    ...projectForm,
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
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Project Title
                </label>
                <input
                  type="text"
                  value={projectForm.title}
                  onChange={(e) =>
                    setProjectForm({ ...projectForm, title: e.target.value })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Client Name
                </label>
                <input
                  type="text"
                  value={projectForm.clientName}
                  onChange={(e) =>
                    setProjectForm({
                      ...projectForm,
                      clientName: e.target.value,
                    })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Description
              </label>
              <textarea
                value={projectForm.description}
                onChange={(e) =>
                  setProjectForm({
                    ...projectForm,
                    description: e.target.value,
                  })
                }
                rows={3}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Industry
                </label>
                <input
                  type="text"
                  value={projectForm.industry}
                  onChange={(e) =>
                    setProjectForm({ ...projectForm, industry: e.target.value })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Project Type
                </label>
                <input
                  type="text"
                  value={projectForm.projectType}
                  onChange={(e) =>
                    setProjectForm({
                      ...projectForm,
                      projectType: e.target.value,
                    })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Duration
                </label>
                <input
                  type="text"
                  value={projectForm.duration}
                  onChange={(e) =>
                    setProjectForm({ ...projectForm, duration: e.target.value })
                  }
                  className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2"
                />
              </div>
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
