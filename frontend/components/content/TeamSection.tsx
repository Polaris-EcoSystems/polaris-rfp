import {
  EyeIcon,
  PencilIcon,
  TrashIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import Image from 'next/image'
import { useMemo, useState } from 'react'
import AuditMeta from './ui/AuditMeta'
import ContentPanel from './ui/ContentPanel'
import ContentSplitLayout from './ui/ContentSplitLayout'
import EmptyState from './ui/EmptyState'
import PaginationControls from './ui/PaginationControls'

export default function TeamSection({ ctx }: { ctx: any }) {
  const {
    team,
    teamForCompany,
    unassignedTeam,
    allTeam,
    selectedCompanyId,
    searchQuery: controlledSearch,
    setSearchQuery: setControlledSearch,
    qualityFilterLabel,
    qualityFilterIds,
    clearQualityFilter,
    assignMemberToSelectedCompany,
    assignManyToSelectedCompany,
    scope: controlledScope,
    setScope: setControlledScope,
    selectedMember,
    setSelectedMember,
    showAddMember,
    setShowAddMember,
    openAddMemberModal,
    memberForm,
    setMemberForm,
    addArrayItem,
    updateArrayItem,
    removeArrayItem,
    handleAddMember,
    handleEditMember,
    editingMember,
    handleSaveMember,
    handleDeleteMember,
  } = ctx

  const [localScope, setLocalScope] = useState<
    'company' | 'unassigned' | 'all'
  >(selectedCompanyId ? 'company' : 'all')
  const scope: 'company' | 'unassigned' | 'all' = controlledScope ?? localScope
  const setScope =
    typeof setControlledScope === 'function'
      ? setControlledScope
      : setLocalScope
  const [localSearch, setLocalSearch] = useState('')
  const search = typeof controlledSearch === 'string' ? controlledSearch : localSearch
  const setSearch =
    typeof setControlledSearch === 'function' ? setControlledSearch : setLocalSearch
  const [sortBy, setSortBy] = useState<'name' | 'position' | 'company'>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const pageSize = 20
  const [bulkAssigning, setBulkAssigning] = useState(false)

  const filteredSorted = useMemo(() => {
    const q = String(search || '')
      .trim()
      .toLowerCase()
    const qualityIds = Array.isArray(qualityFilterIds) ? qualityFilterIds : []
    const qualitySet = new Set(qualityIds.map((x: any) => String(x || '').trim()))
    const list =
      scope === 'unassigned'
        ? Array.isArray(unassignedTeam)
          ? unassignedTeam
          : []
        : scope === 'company'
        ? Array.isArray(teamForCompany)
          ? teamForCompany
          : []
        : Array.isArray(allTeam)
        ? allTeam
        : Array.isArray(team)
        ? team
        : []

    const listAfterQuality =
      qualitySet.size > 0
        ? list.filter((m: any) =>
            qualitySet.has(String(m?.memberId || m?._id || '').trim()),
          )
        : list

    const filtered = q
      ? listAfterQuality.filter((m: any) => {
          const name = String(m?.nameWithCredentials || m?.name || '')
            .toLowerCase()
            .trim()
          const pos = String(m?.position || m?.title || '')
            .toLowerCase()
            .trim()
          const email = String(m?.email || '')
            .toLowerCase()
            .trim()
          const company = String(m?.company?.name || '')
            .toLowerCase()
            .trim()
          return (
            name.includes(q) ||
            pos.includes(q) ||
            email.includes(q) ||
            company.includes(q)
          )
        })
      : listAfterQuality

    const keyFn = (m: any) => {
      if (sortBy === 'position') return String(m?.position || m?.title || '')
      if (sortBy === 'company') return String(m?.company?.name || '')
      return String(m?.nameWithCredentials || m?.name || '')
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
    team,
    teamForCompany,
    unassignedTeam,
    allTeam,
    scope,
    search,
    sortBy,
    sortDir,
    qualityFilterIds,
  ])

  const totalPages = Math.max(1, Math.ceil(filteredSorted.length / pageSize))
  const currentPage = Math.min(Math.max(1, page), totalPages)
  const paged = useMemo(() => {
    const start = (currentPage - 1) * pageSize
    return filteredSorted.slice(start, start + pageSize)
  }, [filteredSorted, currentPage])

  return (
    <ContentSplitLayout
      list={
        <ContentPanel
          title="Team Members"
          actions={
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
                        `Assign ${filteredSorted.length} team member(s) to the selected company?`,
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
                onClick={openAddMemberModal}
                className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-white bg-primary-600 hover:bg-primary-700"
              >
                + Add Member
              </button>
            </div>
          }
          footer={
            <PaginationControls
              page={currentPage}
              totalPages={totalPages}
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
            />
          }
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
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

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs text-gray-500">
              Search:{' '}
              <span className="font-semibold text-gray-700">
                {search ? `“${search}”` : '—'}
              </span>
              {search ? (
                <button
                  type="button"
                  onClick={() => {
                    setSearch('')
                    setPage(1)
                  }}
                  className="ml-2 text-xs text-primary-600 hover:text-primary-700"
                >
                  Clear
                </button>
              ) : null}
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
                <option value="name">Sort: Name</option>
                <option value="position">Sort: Role</option>
                <option value="company">Sort: Company</option>
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

          {qualityFilterLabel ? (
            <div className="mt-3 rounded border border-primary-200 bg-primary-50 p-3 text-sm text-primary-800 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <span className="font-semibold">Filter:</span>{' '}
                <span className="font-semibold">{qualityFilterLabel}</span>
              </div>
              {typeof clearQualityFilter === 'function' ? (
                <button
                  type="button"
                  onClick={() => clearQualityFilter()}
                  className="px-2 py-1 text-xs rounded bg-white border border-primary-200 hover:bg-primary-100 text-primary-700"
                >
                  Clear
                </button>
              ) : null}
            </div>
          ) : null}

          <div className="mt-2 text-xs text-gray-500">
            Showing {paged.length} of {filteredSorted.length} members
          </div>

          <div className="mt-4 -mx-6 border-t border-gray-200" />
          <div className="-mx-6 divide-y divide-gray-200">
            {filteredSorted.length > 0 ? (
              paged.map((member: any, index: number) => (
                <div
                  key={member.memberId || member._id || index}
                  className={`px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                    selectedMember === member
                      ? 'bg-primary-50 border-r-2 border-primary-500'
                      : ''
                  } focus:outline-none focus:ring-2 focus:ring-primary-500`}
                  onClick={() => setSelectedMember(member)}
                  role="button"
                  tabIndex={0}
                  aria-label={`View ${member.nameWithCredentials || member.name || 'team member'}`}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setSelectedMember(member)
                    }
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0 h-10 w-10 rounded-full bg-primary-100 flex items-center justify-center">
                        <UserGroupIcon className="h-5 w-5 text-primary-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900">
                          {member.nameWithCredentials || member.name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {member.position || member.title}
                        </p>
                      </div>
                    </div>
                    <div className="flex space-x-1">
                      {selectedCompanyId &&
                      !String(member?.companyId || '').trim() &&
                      typeof assignMemberToSelectedCompany === 'function' ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            assignMemberToSelectedCompany(member)
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
                          setSelectedMember(member)
                        }}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-primary-600 bg-primary-100 rounded hover:bg-primary-200"
                      >
                        <EyeIcon className="h-3 w-3 mr-1" />
                        View
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleEditMember(member)
                        }}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-blue-600 bg-blue-100 rounded hover:bg-blue-200"
                      >
                        <PencilIcon className="h-3 w-3 mr-1" />
                        Edit
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteMember(member)
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
              <EmptyState
                title={
                  search
                    ? 'No team members match this search.'
                    : 'No team members found.'
                }
                description={
                  search
                    ? 'Try a different query, or widen the scope.'
                    : 'Add your first team member to get started.'
                }
              />
            )}
          </div>
        </ContentPanel>
      }
      details={
        <ContentPanel title="Member Details" sticky>
          {selectedMember ? (
            <div className="space-y-4">
              <div className="text-center">
                {selectedMember.headshotUrl ? (
                  <Image
                    src={selectedMember.headshotUrl}
                    alt="Headshot"
                    width={64}
                    height={64}
                    unoptimized
                    className="h-16 w-16 rounded-full object-cover border mx-auto mb-3"
                  />
                ) : (
                  <div className="flex-shrink-0 h-16 w-16 rounded-full bg-primary-100 flex items-center justify-center mx-auto mb-3">
                    <UserGroupIcon className="h-8 w-8 text-primary-600" />
                  </div>
                )}
                <h4 className="font-medium text-gray-900">
                  {selectedMember.nameWithCredentials || selectedMember.name}
                </h4>
                <p className="text-sm text-gray-500">
                  {selectedMember.position || selectedMember.title}
                </p>
                <AuditMeta
                  className="mt-2"
                  createdAt={selectedMember.createdAt}
                  updatedAt={selectedMember.updatedAt}
                  version={selectedMember.version}
                />
                {selectedMember.email && (
                  <a
                    href={`mailto:${selectedMember.email}`}
                    className="text-xs text-primary-600 hover:text-primary-700 hover:underline mt-1 inline-block"
                  >
                    {selectedMember.email}
                  </a>
                )}
                {selectedMember.company && (
                  <div className="mt-2 flex items-center justify-center text-xs text-gray-600">
                    <span className="font-medium">Company:</span>
                    <span className="ml-1">{selectedMember.company.name}</span>
                    {selectedMember.company.sharedInfo && (
                      <span className="ml-1" title="Shared company data">
                        🔗
                      </span>
                    )}
                  </div>
                )}
              </div>

              {selectedMember.biography && (
                <div>
                  <h5 className="text-sm font-medium text-gray-700 mb-2">
                    Default Biography
                  </h5>
                  <div className="text-sm text-gray-600 leading-relaxed">
                    {selectedMember.biography
                      .split('\n')
                      .map((line: string, index: number) => {
                        const trimmedLine = line.trim()
                        if (!trimmedLine) return <br key={index} />

                        // If line starts with bullet point, render as list item
                        if (
                          trimmedLine.startsWith('•') ||
                          trimmedLine.startsWith('-') ||
                          trimmedLine.startsWith('*')
                        ) {
                          return (
                            <div key={index} className="flex items-start mb-1">
                              <span className="text-gray-400 mr-2 mt-0.5">
                                •
                              </span>
                              <span className="flex-1">
                                {trimmedLine.replace(/^[•\-*]\s*/, '')}
                              </span>
                            </div>
                          )
                        }

                        // Regular paragraph
                        return (
                          <p key={index} className="mb-2">
                            {trimmedLine}
                          </p>
                        )
                      })}
                  </div>
                </div>
              )}

                {Array.isArray(selectedMember.bioProfiles) &&
                  selectedMember.bioProfiles.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Tailored Profiles
                      </h5>
                      <div className="space-y-3">
                        {selectedMember.bioProfiles.map(
                          (p: any, idx: number) => (
                            <div
                              key={p.id || idx}
                              className="rounded border border-gray-200 p-3"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-sm font-medium text-gray-900">
                                  {p.label || `Profile ${idx + 1}`}
                                </div>
                                <div className="flex flex-wrap gap-1 justify-end">
                                  {(Array.isArray(p.projectTypes)
                                    ? p.projectTypes
                                    : []
                                  ).map((t: string) => (
                                    <span
                                      key={t}
                                      className="px-2 py-0.5 text-[11px] bg-gray-100 text-gray-700 rounded"
                                    >
                                      {t}
                                    </span>
                                  ))}
                                </div>
                              </div>
                              {p.bio && (
                                <p className="text-xs text-gray-600 mt-2 line-clamp-4 whitespace-pre-wrap">
                                  {String(p.bio).trim()}
                                </p>
                              )}
                              {p.experience && (
                                <p className="text-xs text-gray-600 mt-2 line-clamp-4 whitespace-pre-wrap">
                                  {String(p.experience).trim()}
                                </p>
                              )}
                            </div>
                          ),
                        )}
                      </div>
                    </div>
                  )}

                {/* Legacy fields for backward compatibility */}
                {selectedMember.experienceYears && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Experience
                    </h5>
                    <p className="text-sm text-gray-600">
                      {selectedMember.experienceYears}+ years
                    </p>
                  </div>
                )}

                {selectedMember.education &&
                  selectedMember.education.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Education
                      </h5>
                      <ul className="space-y-1">
                        {selectedMember.education.map(
                          (edu: string, index: number) => (
                            <li key={index} className="text-sm text-gray-600">
                              {edu}
                            </li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}

                {selectedMember.certifications &&
                  selectedMember.certifications.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Certifications
                      </h5>
                      <div className="flex flex-wrap gap-1">
                        {selectedMember.certifications.map(
                          (cert: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded"
                            >
                              {cert}
                            </span>
                          ),
                        )}
                      </div>
                    </div>
                  )}
            </div>
          ) : (
            <EmptyState
              title="Select a team member"
              description="Pick a row to preview details."
              icon={<UserGroupIcon className="h-10 w-10" />}
            />
          )}
        </ContentPanel>
      }
    />
  )
}
