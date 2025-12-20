import {
  ClipboardDocumentListIcon,
  EnvelopeIcon,
  EyeIcon,
  PencilIcon,
  PhoneIcon,
  TrashIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { useMemo, useState } from 'react'
import AuditMeta from './ui/AuditMeta'
import ContentPanel from './ui/ContentPanel'
import ContentSplitLayout from './ui/ContentSplitLayout'
import EmptyState from './ui/EmptyState'
import PaginationControls from './ui/PaginationControls'

export default function ReferencesSection({ ctx }: { ctx: any }) {
  const {
    references,
    referencesForCompany,
    unassignedReferences,
    allReferences,
    selectedCompanyId,
    searchQuery: controlledSearch,
    setSearchQuery: setControlledSearch,
    projectTypeFilter,
    qualityFilterLabel,
    qualityFilterIds,
    clearQualityFilter,
    assignReferenceToSelectedCompany,
    assignManyToSelectedCompany,
    scope: controlledScope,
    setScope: setControlledScope,
    selectedReference,
    setSelectedReference,
    handleViewReference,
    showAddReference,
    setShowAddReference,
    referenceForm,
    setReferenceForm,
    addArrayItem,
    updateArrayItem,
    removeArrayItem,
    handleAddReference,
    handleEditReference,
    editingReference,
    handleSaveReference,
    handleDeleteReference,
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
  const search =
    typeof controlledSearch === 'string' ? controlledSearch : localSearch
  const setSearch =
    typeof setControlledSearch === 'function'
      ? setControlledSearch
      : setLocalSearch
  const [sortBy, setSortBy] = useState<'org' | 'contact' | 'time'>('org')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const pageSize = 20
  const [bulkAssigning, setBulkAssigning] = useState(false)

  const filteredSorted = useMemo(() => {
    const q = String(search || '')
      .trim()
      .toLowerCase()
    const qualityIds = Array.isArray(qualityFilterIds) ? qualityFilterIds : []
    const qualitySet = new Set(
      qualityIds.map((x: any) => String(x || '').trim()),
    )
    const list =
      scope === 'unassigned'
        ? Array.isArray(unassignedReferences)
          ? unassignedReferences
          : []
        : scope === 'company'
        ? Array.isArray(referencesForCompany)
          ? referencesForCompany
          : []
        : Array.isArray(allReferences)
        ? allReferences
        : Array.isArray(references)
        ? references
        : []

    const listAfterQuality =
      qualitySet.size > 0
        ? list.filter((r: any) =>
            qualitySet.has(String(r?._id || r?.referenceId || '').trim()),
          )
        : list

    const baseFiltered = listAfterQuality.filter((r: any) => {
      const pt = String(r?.projectType || '').trim()
      if (projectTypeFilter && pt !== String(projectTypeFilter)) return false
      return true
    })

    const filtered = q
      ? baseFiltered.filter((r: any) => {
          const org = String(r?.organizationName || '')
            .toLowerCase()
            .trim()
          const contact = String(r?.contactName || '')
            .toLowerCase()
            .trim()
          const email = String(r?.contactEmail || '')
            .toLowerCase()
            .trim()
          const time = String(r?.timePeriod || '')
            .toLowerCase()
            .trim()
          return (
            org.includes(q) ||
            contact.includes(q) ||
            email.includes(q) ||
            time.includes(q)
          )
        })
      : baseFiltered

    const keyFn = (r: any) => {
      if (sortBy === 'contact') return String(r?.contactName || '')
      if (sortBy === 'time') return String(r?.timePeriod || '')
      return String(r?.organizationName || '')
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
    references,
    referencesForCompany,
    unassignedReferences,
    allReferences,
    scope,
    projectTypeFilter,
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
          title="Client References"
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
                        `Assign ${filteredSorted.length} reference(s) to the selected company?`,
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
                onClick={() => setShowAddReference(true)}
                className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-white bg-primary-600 hover:bg-primary-700"
              >
                + Add Reference
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
                <option value="org">Sort: Organization</option>
                <option value="contact">Sort: Contact</option>
                <option value="time">Sort: Time period</option>
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
            Showing {paged.length} of {filteredSorted.length} references
          </div>

          <div className="mt-4 -mx-6 border-t border-gray-200" />
          <div className="-mx-6 divide-y divide-gray-200">
            {filteredSorted.length > 0 ? (
              paged.map((reference: any, index: number) => (
                <div
                  key={reference._id || reference.referenceId || index}
                  className={`px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                    selectedReference === reference
                      ? 'bg-primary-50 border-r-2 border-primary-500'
                      : ''
                  } focus:outline-none focus:ring-2 focus:ring-primary-500`}
                  onClick={() => setSelectedReference(reference)}
                  role="button"
                  tabIndex={0}
                  aria-label={`View reference ${
                    reference.organizationName || ''
                  }`}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setSelectedReference(reference)
                    }
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0 h-10 w-10 rounded-full bg-purple-100 flex items-center justify-center">
                        <ClipboardDocumentListIcon className="h-5 w-5 text-purple-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900">
                          {reference.organizationName}
                        </p>
                        <p className="text-xs text-gray-500">
                          {reference.contactName}
                        </p>
                        <p className="text-xs text-gray-400">
                          {reference.timePeriod}
                        </p>
                      </div>
                    </div>
                    <div className="flex space-x-1">
                      {selectedCompanyId &&
                      !String(reference?.companyId || '').trim() &&
                      typeof assignReferenceToSelectedCompany === 'function' ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            assignReferenceToSelectedCompany(reference)
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
                          if (typeof handleViewReference === 'function') {
                            handleViewReference(reference)
                          } else {
                            setSelectedReference(reference)
                          }
                        }}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-primary-600 bg-primary-100 rounded hover:bg-primary-200"
                      >
                        <EyeIcon className="h-3 w-3 mr-1" />
                        View
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleEditReference(reference)
                        }}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-blue-600 bg-blue-100 rounded hover:bg-blue-200"
                      >
                        <PencilIcon className="h-3 w-3 mr-1" />
                        Edit
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteReference(reference)
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
                    ? 'No references match this search.'
                    : 'No references found.'
                }
                description={
                  search
                    ? 'Try a different query, or widen the scope.'
                    : 'Add your first reference to get started.'
                }
              />
            )}
          </div>
        </ContentPanel>
      }
      details={
        <ContentPanel title="Reference Details" sticky>
          {selectedReference ? (
            <div className="space-y-4">
              <div className="text-center">
                <div className="flex-shrink-0 h-16 w-16 rounded-full bg-purple-100 flex items-center justify-center mx-auto mb-3">
                  <ClipboardDocumentListIcon className="h-8 w-8 text-purple-600" />
                </div>
                <h4 className="font-medium text-gray-900">
                  {selectedReference.organizationName}
                </h4>
                <p className="text-sm text-gray-500">
                  {selectedReference.timePeriod}
                </p>
                <AuditMeta
                  className="mt-2"
                  createdAt={selectedReference.createdAt}
                  updatedAt={selectedReference.updatedAt}
                  version={selectedReference.version}
                />
              </div>

              <div>
                <h5 className="text-sm font-medium text-gray-700 mb-2">
                  Contact Information
                </h5>
                <div className="space-y-2">
                  <div>
                    <div className="flex items-center space-x-2">
                      <UserGroupIcon className="h-3 w-3 text-gray-400" />
                      <span className="text-sm font-medium text-gray-800">
                        {selectedReference.contactName}
                      </span>
                    </div>
                    {selectedReference.contactTitle && (
                      <p className="text-xs text-gray-600 ml-5">
                        {selectedReference.contactTitle}
                      </p>
                    )}
                    {selectedReference.additionalTitle && (
                      <p className="text-xs text-gray-500 ml-5 italic">
                        {selectedReference.additionalTitle}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center space-x-2">
                    <EnvelopeIcon className="h-3 w-3 text-gray-400" />
                    <span className="text-sm text-gray-600">
                      {selectedReference.contactEmail}
                    </span>
                  </div>
                  {selectedReference.contactPhone && (
                    <div className="flex items-center space-x-2">
                      <PhoneIcon className="h-3 w-3 text-gray-400" />
                      <span className="text-sm text-gray-600">
                        {selectedReference.contactPhone}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {selectedReference.scopeOfWork && (
                <div>
                  <h5 className="text-sm font-medium text-gray-700 mb-2">
                    Scope of Work
                  </h5>
                  <div className="text-xs text-gray-600 leading-relaxed">
                    {selectedReference.scopeOfWork}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <EmptyState
              title="Select a reference"
              description="Pick a row to preview details."
              icon={<ClipboardDocumentListIcon className="h-10 w-10" />}
            />
          )}
        </ContentPanel>
      }
    />
  )
}
