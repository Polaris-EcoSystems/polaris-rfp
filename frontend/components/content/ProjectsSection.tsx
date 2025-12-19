import {
  EyeIcon,
  FolderIcon,
  PencilIcon,
  StarIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import { useMemo, useState } from 'react'

export default function ProjectsSection({ ctx }: { ctx: any }) {
  const {
    projects,
    projectsForCompany,
    unassignedProjects,
    allProjects,
    selectedCompanyId,
    assignProjectToSelectedCompany,
    assignManyToSelectedCompany,
    scope: controlledScope,
    setScope: setControlledScope,
    selectedProject,
    setSelectedProject,
    showAddProject,
    setShowAddProject,
    projectForm,
    setProjectForm,
    addArrayItem,
    updateArrayItem,
    removeArrayItem,
    handleAddProject,
    handleEditProject,
    editingProject,
    handleSaveProject,
    handleDeleteProject,
  } = ctx

  const [localScope, setLocalScope] = useState<
    'company' | 'unassigned' | 'all'
  >(selectedCompanyId ? 'company' : 'all')
  const scope: 'company' | 'unassigned' | 'all' = controlledScope ?? localScope
  const setScope =
    typeof setControlledScope === 'function'
      ? setControlledScope
      : setLocalScope
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<'title' | 'client' | 'industry'>('title')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const pageSize = 20
  const [bulkAssigning, setBulkAssigning] = useState(false)

  const filteredSorted = useMemo(() => {
    const q = String(search || '')
      .trim()
      .toLowerCase()
    const list =
      scope === 'unassigned'
        ? Array.isArray(unassignedProjects)
          ? unassignedProjects
          : []
        : scope === 'company'
        ? Array.isArray(projectsForCompany)
          ? projectsForCompany
          : []
        : Array.isArray(allProjects)
        ? allProjects
        : Array.isArray(projects)
        ? projects
        : []

    const filtered = q
      ? list.filter((p: any) => {
          const title = String(p?.title || '')
            .toLowerCase()
            .trim()
          const client = String(p?.clientName || '')
            .toLowerCase()
            .trim()
          const industry = String(p?.industry || '')
            .toLowerCase()
            .trim()
          const duration = String(p?.duration || '')
            .toLowerCase()
            .trim()
          return (
            title.includes(q) ||
            client.includes(q) ||
            industry.includes(q) ||
            duration.includes(q)
          )
        })
      : list

    const keyFn = (p: any) => {
      if (sortBy === 'client') return String(p?.clientName || '')
      if (sortBy === 'industry') return String(p?.industry || '')
      return String(p?.title || '')
    }

    const dir = sortDir === 'desc' ? -1 : 1
    const sorted = [...filtered].sort((a, b) => {
      const av = keyFn(a).toLowerCase()
      const bv = keyFn(b).toLowerCase()
      if (av < bv) return -1 * dir
      if (av > bv) return 1 * dir
      return 0
    })

    return sorted
  }, [
    projects,
    projectsForCompany,
    unassignedProjects,
    allProjects,
    scope,
    search,
    sortBy,
    sortDir,
  ])

  const totalPages = Math.max(1, Math.ceil(filteredSorted.length / pageSize))
  const currentPage = Math.min(Math.max(1, page), totalPages)
  const paged = useMemo(() => {
    const start = (currentPage - 1) * pageSize
    return filteredSorted.slice(start, start + pageSize)
  }, [filteredSorted, currentPage])

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Projects List */}
      <div className="lg:col-span-2">
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-5 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Past Projects
              </h3>
              <div className="flex items-center gap-2">
                {selectedCompanyId &&
                scope === 'unassigned' &&
                filteredSorted.length > 0 &&
                typeof assignManyToSelectedCompany === 'function' ? (
                  <button
                    type="button"
                    disabled={bulkAssigning}
                    onClick={async () => {
                      if (
                        !confirm(
                          `Assign ${filteredSorted.length} project(s) to the selected company?`,
                        )
                      )
                        return
                      try {
                        setBulkAssigning(true)
                        await assignManyToSelectedCompany(filteredSorted)
                      } finally {
                        setBulkAssigning(false)
                      }
                    }}
                    className="inline-flex items-center px-3 py-1 border border-gray-300 text-xs font-medium rounded text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-60"
                  >
                    {bulkAssigning
                      ? 'Assigning…'
                      : `Assign all (${filteredSorted.length})`}
                  </button>
                ) : null}
                <button
                  onClick={() => setShowAddProject(true)}
                  className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-white bg-primary-600 hover:bg-primary-700"
                >
                  + Add Project
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Scope</span>
                <select
                  value={scope}
                  onChange={(e) => {
                    setScope(e.target.value as any)
                    setPage(1)
                  }}
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm bg-white"
                >
                  <option value="company" disabled={!selectedCompanyId}>
                    This company
                  </option>
                  <option value="unassigned">Unassigned</option>
                  <option value="all">All</option>
                </select>
              </div>
              {!selectedCompanyId ? (
                <div className="text-xs text-gray-500">
                  Select a company to work “company-first”.
                </div>
              ) : null}
            </div>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex-1 sm:max-w-md">
                <input
                  type="text"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
                  placeholder="Search by title, client, industry, duration…"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                />
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={sortBy}
                  onChange={(e) => {
                    setSortBy(e.target.value as any)
                    setPage(1)
                  }}
                  className="border border-gray-300 rounded-md px-3 py-2 text-sm bg-white"
                >
                  <option value="title">Sort: Title</option>
                  <option value="client">Sort: Client</option>
                  <option value="industry">Sort: Industry</option>
                </select>
                <button
                  type="button"
                  onClick={() => {
                    setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
                    setPage(1)
                  }}
                  className="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white hover:bg-gray-50"
                  title="Toggle sort direction"
                >
                  {sortDir === 'asc' ? '↑' : '↓'}
                </button>
              </div>
            </div>
            <div className="mt-2 text-xs text-gray-500">
              Showing {paged.length} of {filteredSorted.length} projects
            </div>
          </div>
          <div className="divide-y divide-gray-200">
            {filteredSorted.length > 0 ? (
              paged.map((project: any, index: number) => (
                <div
                  key={project._id || project.projectId || index}
                  className={`px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                    selectedProject === project
                      ? 'bg-primary-50 border-r-2 border-primary-500'
                      : ''
                  }`}
                  onClick={() => setSelectedProject(project)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0 h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center">
                        <FolderIcon className="h-5 w-5 text-blue-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900">
                          {project.title}
                        </p>
                        <p className="text-xs text-gray-500">
                          {project.clientName}
                        </p>
                        <p className="text-xs text-gray-400">
                          {project.industry} • {project.duration}
                        </p>
                      </div>
                    </div>
                    <div className="flex space-x-1">
                      {selectedCompanyId &&
                      !String(project?.companyId || '').trim() &&
                      typeof assignProjectToSelectedCompany === 'function' ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            assignProjectToSelectedCompany(project)
                          }}
                          className="inline-flex items-center px-2 py-1 text-xs font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200"
                          title="Assign this item to the selected company"
                        >
                          Assign
                        </button>
                      ) : null}
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedProject(project)
                        }}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-primary-600 bg-primary-100 rounded hover:bg-primary-200"
                      >
                        <EyeIcon className="h-3 w-3 mr-1" />
                        View
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleEditProject(project)
                        }}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-blue-600 bg-blue-100 rounded hover:bg-blue-200"
                      >
                        <PencilIcon className="h-3 w-3 mr-1" />
                        Edit
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteProject(project)
                        }}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-red-600 bg-red-100 rounded hover:bg-red-200"
                      >
                        <TrashIcon className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="px-6 py-4">
                <p className="text-gray-500 text-sm">
                  No projects found{search ? ' for this search' : ''}.
                </p>
              </div>
            )}
          </div>
          {totalPages > 1 && (
            <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                className="px-3 py-2 text-sm rounded border border-gray-300 bg-white disabled:opacity-50"
              >
                Prev
              </button>
              <div className="text-sm text-gray-600">
                Page {currentPage} / {totalPages}
              </div>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="px-3 py-2 text-sm rounded border border-gray-300 bg-white disabled:opacity-50"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Project Details Panel */}
      <div className="lg:col-span-1">
        <div className="bg-white shadow rounded-lg sticky top-6">
          <div className="px-6 py-5 border-b border-gray-200">
            <h3 className="text-lg leading-6 font-medium text-gray-900">
              Project Details
            </h3>
          </div>
          <div className="px-6 py-4">
            {selectedProject ? (
              <div className="space-y-4">
                <div className="text-center">
                  <div className="flex-shrink-0 h-16 w-16 rounded-full bg-blue-100 flex items-center justify-center mx-auto mb-3">
                    <FolderIcon className="h-8 w-8 text-blue-600" />
                  </div>
                  <h4 className="font-medium text-gray-900">
                    {selectedProject.title}
                  </h4>
                  <p className="text-sm text-gray-500">
                    {selectedProject.clientName}
                  </p>
                </div>

                <div>
                  <h5 className="text-sm font-medium text-gray-700 mb-2">
                    Description
                  </h5>
                  <p className="text-sm text-gray-600">
                    {selectedProject.description}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-1">
                      Industry
                    </h5>
                    <p className="text-xs text-gray-600">
                      {selectedProject.industry}
                    </p>
                  </div>
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-1">
                      Duration
                    </h5>
                    <p className="text-xs text-gray-600">
                      {selectedProject.duration}
                    </p>
                  </div>
                </div>

                <div>
                  <h5 className="text-sm font-medium text-gray-700 mb-2">
                    Key Outcomes
                  </h5>
                  <ul className="space-y-1">
                    {selectedProject.keyOutcomes
                      ?.slice(0, 3)
                      .map((outcome: string, index: number) => (
                        <li key={index} className="flex items-start space-x-1">
                          <StarIcon className="h-3 w-3 text-yellow-400 mt-1 flex-shrink-0" />
                          <span className="text-xs text-gray-600">
                            {outcome}
                          </span>
                        </li>
                      ))}
                  </ul>
                </div>

                <div>
                  <h5 className="text-sm font-medium text-gray-700 mb-2">
                    Technologies
                  </h5>
                  <div className="flex flex-wrap gap-1">
                    {selectedProject.technologies
                      ?.slice(0, 6)
                      .map((tech: string, index: number) => (
                        <span
                          key={index}
                          className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded"
                        >
                          {tech}
                        </span>
                      ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <FolderIcon className="mx-auto h-8 w-8 text-gray-400" />
                <p className="mt-2 text-sm text-gray-500">
                  Select a project to view its details
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modals moved to page level */}
    </div>
  )
}
