import { TrashIcon } from '@heroicons/react/24/outline'

type AddProjectModalProps = {
  open: boolean
  projectForm: any
  setProjectForm: (v: any) => void
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

export default function AddProjectModal({
  open,
  projectForm,
  setProjectForm,
  companies = [],
  addArrayItem,
  updateArrayItem,
  removeArrayItem,
  onAdd,
  onClose,
}: AddProjectModalProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white max-h-[80vh] overflow-y-auto">
        <div className="mb-4">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Add Past Project
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
              <p className="text-xs text-gray-500 mt-1">
                Projects roll up to the selected company for capability
                generation.
              </p>
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

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Key Outcomes
              </label>
              {projectForm.keyOutcomes.map((outcome: string, index: number) => (
                <div key={index} className="flex mb-2">
                  <input
                    type="text"
                    value={outcome}
                    onChange={(e) =>
                      updateArrayItem(
                        'keyOutcomes',
                        index,
                        e.target.value,
                        setProjectForm,
                        projectForm,
                      )
                    }
                    className="flex-1 border border-gray-300 rounded-md px-3 py-2"
                    placeholder="Key outcome or achievement"
                  />
                  <button
                    onClick={() =>
                      removeArrayItem(
                        'keyOutcomes',
                        index,
                        setProjectForm,
                        projectForm,
                      )
                    }
                    className="ml-2 text-red-600 hover:text-red-800"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <button
                onClick={() =>
                  addArrayItem('keyOutcomes', setProjectForm, projectForm)
                }
                className="text-primary-600 hover:text-primary-800 text-sm"
              >
                + Add Outcome
              </button>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Technologies Used
              </label>
              {projectForm.technologies.map((tech: string, index: number) => (
                <div key={index} className="flex mb-2">
                  <input
                    type="text"
                    value={tech}
                    onChange={(e) =>
                      updateArrayItem(
                        'technologies',
                        index,
                        e.target.value,
                        setProjectForm,
                        projectForm,
                      )
                    }
                    className="flex-1 border border-gray-300 rounded-md px-3 py-2"
                    placeholder="Technology or tool"
                  />
                  <button
                    onClick={() =>
                      removeArrayItem(
                        'technologies',
                        index,
                        setProjectForm,
                        projectForm,
                      )
                    }
                    className="ml-2 text-red-600 hover:text-red-800"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <button
                onClick={() =>
                  addArrayItem('technologies', setProjectForm, projectForm)
                }
                className="text-primary-600 hover:text-primary-800 text-sm"
              >
                + Add Technology
              </button>
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
            Add Project
          </button>
        </div>
      </div>
    </div>
  )
}
