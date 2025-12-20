import {
  CheckIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import api, { proxyUrl } from '../lib/api'
import type {
  Company,
  ContentLibraryModalProps,
  ProjectReference,
  TeamMember,
} from '../types/contentLibrary'

export default function ContentLibraryModal({
  isOpen,
  onClose,
  onApply,
  type,
  currentSelectedIds = [],
  isLoading = false,
}: ContentLibraryModalProps) {
  const [items, setItems] = useState<
    (TeamMember | ProjectReference | Company)[]
  >([])
  const [selectedIds, setSelectedIds] = useState<string[]>(currentSelectedIds)
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<string>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const pageSize = 30
  const [viewMode, setViewMode] = useState<'all' | 'selected'>('all')
  const [assignmentFilter, setAssignmentFilter] = useState<
    'all' | 'assigned' | 'unassigned'
  >('all')
  const [hasEmailOnly, setHasEmailOnly] = useState(false)
  const searchInputRef = useRef<HTMLInputElement | null>(null)

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      let response
      if (type === 'team') {
        response = await api.get(proxyUrl('/api/content/team'))
      } else if (type === 'references') {
        response = await api.get(proxyUrl('/api/content/references'))
      } else if (type === 'company') {
        response = await api.get(proxyUrl('/api/content/companies'))
      }
      if (response) {
        const next = Array.isArray(response.data) ? response.data : []
        setItems(next)
        // Keep focus stable if possible; otherwise pick the first item.
        const firstId: string | null = next.length
          ? String(getItemId(next[0] as any) || '').trim() || null
          : null
        setFocusedId((prev) => {
          if (prev && next.some((x: any) => getItemId(x) === prev)) return prev
          return firstId
        })
      }
    } catch (err) {
      console.error('Error loading content library items:', err)
      setError('Failed to load content library items')
    } finally {
      setLoading(false)
    }
  }, [type])

  useEffect(() => {
    if (isOpen) {
      loadItems()
      setSelectedIds(currentSelectedIds)
      setSearch('')
      setSortDir('asc')
      setPage(1)
      setViewMode('all')
      setAssignmentFilter('all')
      setHasEmailOnly(false)
      setSortBy(type === 'references' ? 'org' : 'name')
      // focus search input on open (best-effort)
      setTimeout(() => {
        try {
          searchInputRef.current?.focus()
        } catch (_e) {
          // ignore
        }
      }, 0)
    }
  }, [isOpen, type, currentSelectedIds, loadItems])

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id)
        ? prev.filter((selectedId) => selectedId !== id)
        : [...prev, id],
    )
  }

  const handleApply = () => {
    onApply(selectedIds)
  }

  const getItemId = (item: TeamMember | ProjectReference | Company) => {
    if ('memberId' in item) return item.memberId
    if ('organizationName' in item) return item._id
    return item.companyId
  }

  const normalize = (v: any) =>
    String(v || '')
      .toLowerCase()
      .trim()

  const getItemTitle = (item: TeamMember | ProjectReference | Company) => {
    if ('memberId' in item)
      return item.nameWithCredentials || String((item as any)?.name || '')
    if ('organizationName' in item) return item.organizationName || ''
    return item.name || ''
  }

  const getItemSubtitle = (item: TeamMember | ProjectReference | Company) => {
    if ('memberId' in item) return item.position || ''
    if ('organizationName' in item)
      return [item.contactName, item.timePeriod].filter(Boolean).join(' • ')
    return [item.email, item.phone].filter(Boolean).join(' • ')
  }

  const getSearchBlob = (item: TeamMember | ProjectReference | Company) => {
    if ('memberId' in item) {
      return [
        item.nameWithCredentials,
        String((item as any)?.name || ''),
        item.position,
        item.email,
        item.company?.name,
        item.biography,
      ]
        .filter(Boolean)
        .join(' ')
    }
    if ('organizationName' in item) {
      return [
        item.organizationName,
        item.contactName,
        item.contactTitle,
        item.additionalTitle,
        item.contactEmail,
        item.contactPhone,
        item.timePeriod,
        item.scopeOfWork,
      ]
        .filter(Boolean)
        .join(' ')
    }
    return [
      item.name,
      item.description,
      item.email,
      item.phone,
      item.coverLetter,
    ]
      .filter(Boolean)
      .join(' ')
  }

  const filteredSorted = useMemo(() => {
    const q = normalize(search)
    const list0 = Array.isArray(items) ? items : []
    const selectedSet = new Set(selectedIds)
    const list1 =
      viewMode === 'selected'
        ? list0.filter((it) => selectedSet.has(getItemId(it)))
        : list0

    const list2 =
      type === 'team' || type === 'references'
        ? list1.filter((it: any) => {
            const hasCompany = Boolean(String(it?.companyId || '').trim())
            if (assignmentFilter === 'assigned') return hasCompany
            if (assignmentFilter === 'unassigned') return !hasCompany
            return true
          })
        : list1

    const list3 = hasEmailOnly
      ? list2.filter((it: any) => {
          if (type === 'team') return Boolean(String(it?.email || '').trim())
          if (type === 'references')
            return Boolean(String(it?.contactEmail || '').trim())
          if (type === 'company') return Boolean(String(it?.email || '').trim())
          return true
        })
      : list2

    const filtered = q
      ? list3.filter((it) => normalize(getSearchBlob(it)).includes(q))
      : list3

    const dir = sortDir === 'desc' ? -1 : 1
    const keyFn = (it: any) => {
      if (type === 'references') {
        if (sortBy === 'contact') return normalize(it?.contactName)
        if (sortBy === 'time') return normalize(it?.timePeriod)
        return normalize(it?.organizationName)
      }
      if (type === 'company') {
        if (sortBy === 'email') return normalize(it?.email)
        return normalize(it?.name)
      }
      // team
      if (sortBy === 'role') return normalize(it?.position || it?.title)
      if (sortBy === 'company') return normalize(it?.company?.name)
      return normalize(it?.nameWithCredentials || it?.name)
    }

    return [...filtered].sort((a, b) => {
      const av = keyFn(a)
      const bv = keyFn(b)
      if (av < bv) return -1 * dir
      if (av > bv) return 1 * dir
      return 0
    })
  }, [
    items,
    search,
    sortBy,
    sortDir,
    type,
    viewMode,
    assignmentFilter,
    hasEmailOnly,
    selectedIds,
  ])

  const totalPages = Math.max(1, Math.ceil(filteredSorted.length / pageSize))
  const currentPage = Math.min(Math.max(1, page), totalPages)
  const paged = useMemo(() => {
    const start = (currentPage - 1) * pageSize
    return filteredSorted.slice(start, start + pageSize)
  }, [filteredSorted, currentPage])

  const focusedItem = useMemo(() => {
    if (!focusedId) return null
    return filteredSorted.find((x) => getItemId(x) === focusedId) || null
  }, [filteredSorted, focusedId])

  const setFocus = (id: string) => {
    setFocusedId(id)
  }

  const isSelected = (id: string) => selectedIds.includes(id)

  const selectAllOnPage = () => {
    const ids = paged.map((x) => getItemId(x))
    setSelectedIds((prev) => Array.from(new Set([...prev, ...ids])))
  }

  const selectAllFiltered = () => {
    const ids = filteredSorted.map((x) => getItemId(x))
    if (!ids.length) return
    if (
      ids.length > 150 &&
      !confirm(`Select all ${ids.length} items in this filtered view?`)
    ) {
      return
    }
    setSelectedIds((prev) => Array.from(new Set([...prev, ...ids])))
  }

  const clearAll = () => setSelectedIds([])

  const toggleFocused = () => {
    if (!focusedId) return
    toggleSelection(focusedId)
  }

  useEffect(() => {
    if (!isOpen) return
    if (loading) return
    if (!paged.length) {
      setFocusedId(null)
      return
    }
    const ids = paged.map((x) => getItemId(x))
    if (focusedId && ids.includes(focusedId)) return
    const first = String(getItemId(paged[0]) || '').trim()
    setFocusedId(first || null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, loading, currentPage, paged])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) return
    if (isLoading) return
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
      return
    }

    // Don't steal arrows when typing in the search box.
    const target = e.target as HTMLElement | null
    const isTyping =
      target?.tagName === 'INPUT' ||
      target?.tagName === 'TEXTAREA' ||
      (target as any)?.isContentEditable
    if (isTyping) return

    if (e.key === 'Enter') {
      e.preventDefault()
      handleApply()
      return
    }
    if (e.key === ' ') {
      e.preventDefault()
      toggleFocused()
      return
    }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()

    const list = paged
    if (!list.length) return
    const ids = list.map((x) => getItemId(x))
    const idx = focusedId ? ids.indexOf(focusedId) : -1
    const nextIdx =
      e.key === 'ArrowDown'
        ? Math.min(ids.length - 1, Math.max(0, idx + 1))
        : Math.max(0, idx <= 0 ? 0 : idx - 1)
    setFocusedId(ids[nextIdx])
  }

  const title =
    type === 'team'
      ? 'Select Team Members'
      : type === 'references'
      ? 'Select Project References'
      : 'Select Company Profile'
  const emptyMessage =
    type === 'team'
      ? 'No team members available in the content library.'
      : type === 'references'
      ? 'No project references available in the content library.'
      : 'No company profiles available in the content library.'

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onKeyDown={onKeyDown}
    >
      {/* Backdrop with blur */}
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal Content */}
      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-5xl mx-4 max-h-[90vh] flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
            <div className="mt-1 text-xs text-gray-500">
              Tip: use ↑/↓ to move, space to toggle, enter to apply.
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            disabled={isLoading}
            aria-label="Close"
          >
            <XMarkIcon className="h-6 w-6" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 border-b border-gray-100">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex-1 md:max-w-md">
              <div className="relative">
                <MagnifyingGlassIcon className="h-4 w-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  ref={searchInputRef}
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
                  placeholder={
                    type === 'team'
                      ? 'Search name, role, email, company…'
                      : type === 'references'
                      ? 'Search org, contact, email, time…'
                      : 'Search name, email, phone…'
                  }
                  aria-label="Search content library items"
                  className="w-full border border-gray-300 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {(type === 'team' || type === 'references') &&
              viewMode !== 'selected' ? (
                <select
                  value={assignmentFilter}
                  onChange={(e) => {
                    setAssignmentFilter(e.target.value as any)
                    setPage(1)
                  }}
                  className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
                  title="Filter by assignment"
                >
                  <option value="all">All</option>
                  <option value="assigned">Assigned</option>
                  <option value="unassigned">Unassigned</option>
                </select>
              ) : null}

              {(type === 'team' ||
                type === 'references' ||
                type === 'company') &&
              viewMode !== 'selected' ? (
                <label className="inline-flex items-center gap-2 px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white">
                  <input
                    type="checkbox"
                    checked={hasEmailOnly}
                    onChange={(e) => {
                      setHasEmailOnly(e.target.checked)
                      setPage(1)
                    }}
                  />
                  <span className="text-sm text-gray-700">Has email</span>
                </label>
              ) : null}

              <button
                type="button"
                onClick={() => {
                  setViewMode((v) => (v === 'all' ? 'selected' : 'all'))
                  setPage(1)
                }}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-50"
                disabled={viewMode === 'all' && selectedIds.length === 0}
                title="Toggle selection review"
              >
                {viewMode === 'selected'
                  ? 'Show all'
                  : `Selected only (${selectedIds.length})`}
              </button>

              <select
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value)
                  setPage(1)
                }}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
              >
                {type === 'team' ? (
                  <>
                    <option value="name">Sort: Name</option>
                    <option value="role">Sort: Role</option>
                    <option value="company">Sort: Company</option>
                  </>
                ) : type === 'references' ? (
                  <>
                    <option value="org">Sort: Organization</option>
                    <option value="contact">Sort: Contact</option>
                    <option value="time">Sort: Time period</option>
                  </>
                ) : (
                  <>
                    <option value="name">Sort: Name</option>
                    <option value="email">Sort: Email</option>
                  </>
                )}
              </select>
              <button
                type="button"
                onClick={() => {
                  setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
                  setPage(1)
                }}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50"
                title="Toggle sort direction"
              >
                {sortDir === 'asc' ? '↑' : '↓'}
              </button>
              <button
                type="button"
                onClick={selectAllOnPage}
                disabled={!paged.length || loading}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-50"
                title="Select all items on this page"
              >
                Select page
              </button>
              <button
                type="button"
                onClick={selectAllFiltered}
                disabled={!filteredSorted.length || loading}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-50"
                title="Select all items in this filtered view"
              >
                Select all
              </button>
              <button
                type="button"
                onClick={clearAll}
                disabled={!selectedIds.length || loading}
                className="px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-50"
              >
                Clear
              </button>
              <div className="text-xs text-gray-500">
                {filteredSorted.length} items • {selectedIds.length} selected
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-red-600">{error}</p>
              <button
                onClick={loadItems}
                className="mt-2 text-sm text-primary-600 hover:text-primary-700"
              >
                Try again
              </button>
            </div>
          ) : filteredSorted.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              {viewMode === 'selected'
                ? 'No items selected.'
                : search
                ? 'No matches for this search.'
                : emptyMessage}
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-5 h-full">
              <div className="lg:col-span-3 border-r border-gray-100 overflow-y-auto">
                <div
                  className="divide-y divide-gray-100"
                  role="listbox"
                  aria-multiselectable="true"
                >
                  {paged.map((item) => {
                    const id = getItemId(item)
                    const selected = isSelected(id)
                    const focused = focusedId === id
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => setFocus(id)}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                          focused ? 'bg-primary-50' : ''
                        }`}
                        role="option"
                        aria-selected={selected}
                        aria-current={focused ? 'true' : undefined}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-gray-900 truncate">
                              {getItemTitle(item)}
                            </div>
                            <div className="text-xs text-gray-500 truncate">
                              {getItemSubtitle(item) || '—'}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span
                              className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${
                                selected
                                  ? 'bg-primary-600 border-primary-600 text-white'
                                  : 'border-gray-300'
                              }`}
                              onClick={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                                toggleSelection(id)
                              }}
                              role="checkbox"
                              aria-checked={selected}
                              tabIndex={-1}
                            >
                              {selected ? (
                                <CheckIcon className="w-4 h-4" />
                              ) : null}
                            </span>
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>

                {totalPages > 1 ? (
                  <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage <= 1}
                      className="px-3 py-2 text-sm rounded-lg border border-gray-300 bg-white disabled:opacity-50"
                    >
                      Prev
                    </button>
                    <div className="text-sm text-gray-600">
                      Page {currentPage} / {totalPages}
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setPage((p) => Math.min(totalPages, p + 1))
                      }
                      disabled={currentPage >= totalPages}
                      className="px-3 py-2 text-sm rounded-lg border border-gray-300 bg-white disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                ) : null}
              </div>

              <div className="hidden lg:block lg:col-span-2 overflow-y-auto">
                <div className="p-5">
                  {focusedItem ? (
                    <div className="space-y-4">
                      <div>
                        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                          Preview
                        </div>
                        <div className="mt-1 text-lg font-semibold text-gray-900">
                          {getItemTitle(focusedItem)}
                        </div>
                        <div className="mt-1 text-sm text-gray-600">
                          {getItemSubtitle(focusedItem)}
                        </div>
                      </div>

                      {type === 'team' ? (
                        <div className="text-sm text-gray-700 whitespace-pre-wrap">
                          {String(
                            (focusedItem as TeamMember).biography || '',
                          ).trim() || 'No biography.'}
                        </div>
                      ) : type === 'references' ? (
                        <div className="space-y-2 text-sm text-gray-700">
                          <div>
                            <span className="text-xs font-semibold text-gray-500">
                              Contact
                            </span>
                            <div>
                              {(focusedItem as ProjectReference).contactName}
                              {(focusedItem as ProjectReference).contactTitle
                                ? `, ${
                                    (focusedItem as ProjectReference)
                                      .contactTitle
                                  }`
                                : ''}
                            </div>
                            {(focusedItem as ProjectReference).contactEmail ? (
                              <div className="text-xs text-gray-600">
                                {(focusedItem as ProjectReference).contactEmail}
                              </div>
                            ) : null}
                          </div>
                          <div>
                            <span className="text-xs font-semibold text-gray-500">
                              Scope of work
                            </span>
                            <div className="whitespace-pre-wrap">
                              {String(
                                (focusedItem as ProjectReference).scopeOfWork ||
                                  '',
                              ).trim() || '—'}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-3 text-sm text-gray-700">
                          {(focusedItem as Company).description ? (
                            <div className="whitespace-pre-wrap">
                              {(focusedItem as Company).description}
                            </div>
                          ) : (
                            <div className="text-gray-500">No description.</div>
                          )}
                          {(focusedItem as Company).coverLetter ? (
                            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700 whitespace-pre-wrap">
                              {(focusedItem as Company).coverLetter}
                            </div>
                          ) : null}
                        </div>
                      )}

                      <button
                        type="button"
                        onClick={() => toggleSelection(getItemId(focusedItem))}
                        className={`w-full inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium ${
                          isSelected(getItemId(focusedItem))
                            ? 'bg-gray-100 text-gray-800 hover:bg-gray-200'
                            : 'bg-primary-600 text-white hover:bg-primary-700'
                        }`}
                      >
                        {isSelected(getItemId(focusedItem))
                          ? 'Remove from selection'
                          : 'Add to selection'}
                      </button>
                    </div>
                  ) : (
                    <div className="text-sm text-gray-600">
                      Select an item to preview it.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-between gap-3">
          <div className="text-xs text-gray-600">
            Selected:{' '}
            <span className="font-semibold">{selectedIds.length}</span>
          </div>
          <div className="flex items-center justify-end space-x-3">
            <button
              onClick={onClose}
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
              disabled={isLoading}
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={isLoading}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                  Applying...
                </>
              ) : (
                `Apply Selection (${selectedIds.length})`
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
