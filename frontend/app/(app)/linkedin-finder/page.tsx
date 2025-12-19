'use client'

import Button from '@/components/ui/Button'
import PipelineContextBanner from '@/components/ui/PipelineContextBanner'
import StepsPanel from '@/components/ui/StepsPanel'
import { finderApi, rfpApi } from '@/lib/api'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'

export default function LinkedInFinderPage() {
  const searchParams = useSearchParams()
  const [rfps, setRfps] = useState<any[]>([])
  const [selectedRfpId, setSelectedRfpId] = useState<string>('')

  const [linkedinConnected, setLinkedinConnected] = useState<boolean | null>(
    null,
  )
  const [storageStateUploading, setStorageStateUploading] = useState(false)
  const [companyLinkedInUrl, setCompanyLinkedInUrl] = useState('')
  const [maxPeople, setMaxPeople] = useState<number>(50)
  const [targetTitlesText, setTargetTitlesText] = useState(
    'procurement\npurchasing\nsourcing\nvp\nhead of\ndirector',
  )

  const [runId, setRunId] = useState<string>('')
  const [run, setRun] = useState<any | null>(null)
  const [profiles, setProfiles] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isStartingRun, setIsStartingRun] = useState(false)
  const [validatingSession, setValidatingSession] = useState(false)
  const [sessionValidation, setSessionValidation] = useState<any | null>(null)
  const [savingToRfp, setSavingToRfp] = useState(false)
  const [saveTopN, setSaveTopN] = useState<number>(10)
  const [saveMode, setSaveMode] = useState<'merge' | 'overwrite'>('merge')
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<Record<string, boolean>>({})
  const [filterText, setFilterText] = useState('')
  const [showHelp, setShowHelp] = useState(false)
  const [showSelectedOnly, setShowSelectedOnly] = useState(false)
  const [minScore, setMinScore] = useState<number>(0)
  const [selectedFirst, setSelectedFirst] = useState<boolean>(true)
  const [sortKey, setSortKey] = useState<
    'buyerScore' | 'name' | 'title' | 'location'
  >('buyerScore')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [functionFilters, setFunctionFilters] = useState<string[]>([])
  const [seniorityFilters, setSeniorityFilters] = useState<string[]>([])
  const headerCheckboxRef = useRef<HTMLInputElement | null>(null)
  const filterInputRef = useRef<HTMLInputElement | null>(null)
  const [highlightedIdx, setHighlightedIdx] = useState<number>(0)
  const [detailsToken, setDetailsToken] = useState<string | null>(null)

  const rfpIdFromQuery = searchParams.get('rfpId') || ''

  const refreshRfps = async () => {
    try {
      const resp = await rfpApi.list()
      setRfps(resp.data?.data || [])
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    void refreshRfps()
  }, [])

  // If navigated from an RFP page, preselect it: /linkedin-finder?rfpId=...
  useEffect(() => {
    if (!rfpIdFromQuery) return
    if (selectedRfpId) return
    if (rfps.length === 0) return
    const exists = rfps.some((r) => r?._id === rfpIdFromQuery)
    if (exists) setSelectedRfpId(rfpIdFromQuery)
  }, [rfpIdFromQuery, rfps, selectedRfpId])

  const refreshLinkedInStatus = async () => {
    try {
      const resp = await finderApi.getStorageStateStatus()
      setLinkedinConnected(Boolean(resp.data?.connected))
    } catch {
      setLinkedinConnected(false)
    }
  }

  const validateSession = async () => {
    setError(null)
    setSaveMessage(null)
    setValidatingSession(true)
    try {
      const resp = await finderApi.validateSession()
      setSessionValidation(resp.data)
      // If the session is valid, treat as connected.
      if (resp.data?.ok === true) setLinkedinConnected(true)
    } catch (e: any) {
      setSessionValidation(null)
      setError(
        e?.response?.data?.detail ||
          e?.response?.data?.error ||
          e?.message ||
          'Failed to validate session',
      )
    } finally {
      setValidatingSession(false)
    }
  }

  useEffect(() => {
    refreshLinkedInStatus()
  }, [])

  // Persist table prefs locally for ergonomics.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem('linkedinFinderPrefs.v1')
      if (!raw) return
      const v = JSON.parse(raw)
      if (v && typeof v === 'object') {
        if (
          v.sortKey === 'buyerScore' ||
          v.sortKey === 'name' ||
          v.sortKey === 'title' ||
          v.sortKey === 'location'
        ) {
          setSortKey(v.sortKey)
        }
        if (v.sortDir === 'asc' || v.sortDir === 'desc') setSortDir(v.sortDir)
        if (typeof v.minScore === 'number') setMinScore(v.minScore)
        if (typeof v.selectedFirst === 'boolean')
          setSelectedFirst(Boolean(v.selectedFirst))
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    try {
      window.localStorage.setItem(
        'linkedinFinderPrefs.v1',
        JSON.stringify({ sortKey, sortDir, minScore, selectedFirst }),
      )
    } catch {
      // ignore
    }
  }, [sortKey, sortDir, minScore, selectedFirst])

  const targetTitles = useMemo(() => {
    return targetTitlesText
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)
  }, [targetTitlesText])

  const selectedRfp = useMemo(() => {
    return rfps.find((r) => r?._id === selectedRfpId) || null
  }, [rfps, selectedRfpId])

  const savedTokens = useMemo(() => {
    const set = new Set<string>()
    const arr = (selectedRfp as any)?.buyerProfiles
    if (!Array.isArray(arr)) return set
    arr.forEach((bp: any) => {
      const tok =
        String(bp?.profileUrl || '').trim() ||
        String(bp?.profileId || '').trim()
      if (tok) set.add(tok)
    })
    return set
  }, [selectedRfp])

  const isSaved = (pOrToken: any): boolean => {
    const tok =
      typeof pOrToken === 'string'
        ? String(pOrToken || '').trim()
        : String(pOrToken?.profileUrl || '').trim() ||
          String(pOrToken?.profileId || '').trim()
    if (!tok) return false
    return savedTokens.has(tok)
  }

  const profileToken = (p: any): string => {
    // Token must match backend selection semantics (profileUrl OR profileId)
    return (
      String(p?.profileUrl || '').trim() || String(p?.profileId || '').trim()
    )
  }

  const uploadStorageState = async (file: File) => {
    setError(null)
    setSaveMessage(null)
    setStorageStateUploading(true)
    try {
      await finderApi.uploadStorageState(file)
      await refreshLinkedInStatus()
      // Attempt a quick validation so user sees immediate feedback.
      try {
        await validateSession()
      } catch {
        // ignore
      }
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.response?.data?.detail ||
          e?.message ||
          'Failed to upload storageState',
      )
    } finally {
      setStorageStateUploading(false)
    }
  }

  const startRun = async () => {
    if (!selectedRfpId) return
    setError(null)
    setIsStartingRun(true)
    try {
      const resp = await finderApi.startRun({
        rfpId: selectedRfpId,
        companyName: selectedRfp?.clientName || undefined,
        companyLinkedInUrl: companyLinkedInUrl.trim() || undefined,
        maxPeople,
        targetTitles,
      })
      const id = resp.data?.runId
      setRunId(id)
      setRun(resp.data?.run || null)
      setProfiles([])
    } catch (e: any) {
      setError(
        e?.response?.data?.error ||
          e?.response?.data?.detail ||
          e?.message ||
          'Failed to start Finder run',
      )
    } finally {
      setIsStartingRun(false)
    }
  }

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    let timer: any = null

    const tick = async () => {
      try {
        const runResp = await finderApi.getRun(runId)
        if (cancelled) return
        setRun(runResp.data)

        const status = String(runResp.data?.status || '')
        if (status === 'done' || status === 'error') {
          try {
            const profResp = await finderApi.listProfiles(runId, 300)
            if (!cancelled) setProfiles(profResp.data?.data || [])
          } catch {
            // ignore
          }
          return
        }

        if (status === 'running') {
          try {
            const profResp = await finderApi.listProfiles(runId, 200)
            if (!cancelled) setProfiles(profResp.data?.data || [])
          } catch {
            // ignore
          }
        }

        timer = setTimeout(tick, 3000)
      } catch (e: any) {
        if (!cancelled) {
          setError(
            e?.response?.data?.detail || e?.message || 'Failed to poll run',
          )
        }
      }
    }

    tick()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [runId])

  const sortedProfiles = useMemo(() => {
    const items = [...profiles]
    const dir = sortDir === 'asc' ? 1 : -1

    const str = (x: any) => String(x || '').toLowerCase()
    const num = (x: any) => {
      const n = Number(x)
      return Number.isFinite(n) ? n : 0
    }

    items.sort((a, b) => {
      if (selectedFirst) {
        const aTok = profileToken(a)
        const bTok = profileToken(b)
        const aSel = Boolean(aTok && selectedKeys[aTok])
        const bSel = Boolean(bTok && selectedKeys[bTok])
        if (aSel !== bSel) return aSel ? -1 : 1
      }

      if (sortKey === 'buyerScore') {
        const d = num(a?.buyerScore) - num(b?.buyerScore)
        if (d !== 0) return d * dir
      } else if (sortKey === 'name') {
        const d = str(a?.name).localeCompare(str(b?.name))
        if (d !== 0) return d * dir
      } else if (sortKey === 'title') {
        const d = str(a?.title).localeCompare(str(b?.title))
        if (d !== 0) return d * dir
      } else if (sortKey === 'location') {
        const d = str(a?.location).localeCompare(str(b?.location))
        if (d !== 0) return d * dir
      }

      // Stable-ish tie break by score desc, then name asc.
      const scoreD = num(b?.buyerScore) - num(a?.buyerScore)
      if (scoreD !== 0) return scoreD
      return str(a?.name).localeCompare(str(b?.name))
    })
    return items
  }, [profiles, sortKey, sortDir, selectedFirst, selectedKeys])

  const toggleSort = (key: typeof sortKey) => {
    setSortKey((prevKey) => {
      if (prevKey === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
        return prevKey
      }
      // Default directions: score desc, strings asc
      setSortDir(key === 'buyerScore' ? 'desc' : 'asc')
      return key
    })
  }

  const sortLabel = (key: typeof sortKey) => {
    if (sortKey !== key) return ''
    return sortDir === 'asc' ? '▲' : '▼'
  }

  const profileRowKey = (p: any): string => {
    return (
      profileToken(p) ||
      String(p?.sk || '').trim() ||
      JSON.stringify([p?.name || '', p?.title || '', p?.location || ''])
    )
  }

  const filteredProfiles = useMemo(() => {
    const q = String(filterText || '')
      .trim()
      .toLowerCase()
    const min = Math.max(0, Math.min(100, Number(minScore || 0)))

    const classifyFunction = (t: string): string | null => {
      if (
        t.includes('procurement') ||
        t.includes('purchasing') ||
        t.includes('sourcing')
      )
        return 'procurement'
      if (t.includes('supply chain')) return 'supply_chain'
      if (t.includes('operations') || t.includes('ops')) return 'operations'
      if (
        t.includes('finance') ||
        t.includes('cfo') ||
        t.includes('accounting')
      )
        return 'finance'
      if (
        t.includes('it') ||
        t.includes('technology') ||
        t.includes('security')
      )
        return 'it'
      if (t.includes('facilities')) return 'facilities'
      if (t.includes('sustainability') || t.includes('environment'))
        return 'sustainability'
      if (t.includes('project') || t.includes('program')) return 'project'
      return null
    }

    const classifySeniority = (t: string): string | null => {
      if (
        t.includes('chief') ||
        t.includes('ceo') ||
        t.includes('cfo') ||
        t.includes('coo')
      )
        return 'c_level'
      if (
        t.includes('svp') ||
        t.includes('evp') ||
        t.includes('vp') ||
        t.includes('vice president')
      )
        return 'vp'
      if (t.includes('head')) return 'head'
      if (t.includes('director')) return 'director'
      if (t.includes('manager') || t.includes('lead')) return 'manager'
      return null
    }

    return sortedProfiles.filter((p) => {
      const score = Number(p?.buyerScore || 0)
      if (score < min) return false

      const token = profileToken(p)
      if (showSelectedOnly && token && !selectedKeys[token]) return false

      const name = String(p?.name || '').toLowerCase()
      const title = String(p?.title || '').toLowerCase()
      const loc = String(p?.location || '').toLowerCase()

      if (q) {
        const hit =
          name.includes(q) ||
          title.includes(q) ||
          loc.includes(q) ||
          token.includes(q)
        if (!hit) return false
      }

      if (functionFilters.length > 0) {
        const f = classifyFunction(title)
        if (!f || !functionFilters.includes(f)) return false
      }

      if (seniorityFilters.length > 0) {
        const s = classifySeniority(title)
        if (!s || !seniorityFilters.includes(s)) return false
      }

      return true
    })
  }, [
    sortedProfiles,
    filterText,
    minScore,
    showSelectedOnly,
    selectedKeys,
    functionFilters,
    seniorityFilters,
  ])

  const visibleProfiles = useMemo(() => {
    return filteredProfiles.slice(0, 200)
  }, [filteredProfiles])

  useEffect(() => {
    // Keep highlight within bounds when filtering changes.
    const max = Math.max(0, visibleProfiles.length - 1)
    setHighlightedIdx((prev) => Math.max(0, Math.min(prev, max)))
  }, [visibleProfiles.length])

  const selectedList = useMemo(() => {
    const keys = Object.keys(selectedKeys).filter((k) => selectedKeys[k])
    return keys
  }, [selectedKeys])

  const toggleSelected = (key: string) => {
    setSelectedKeys((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const selectAllVisible = () => {
    const next: Record<string, boolean> = {}
    visibleProfiles.forEach((p) => {
      const tok = profileToken(p)
      if (tok) next[tok] = true
    })
    setSelectedKeys((prev) => ({ ...prev, ...next }))
  }

  const clearSelection = () => setSelectedKeys({})

  const selectTopN = (n: number) => {
    const next: Record<string, boolean> = {}
    visibleProfiles.slice(0, n).forEach((p) => {
      const tok = profileToken(p)
      if (tok) next[tok] = true
    })
    setSelectedKeys(next)
  }

  const visibleSelectable = useMemo(() => {
    return visibleProfiles.map((p) => profileToken(p)).filter(Boolean)
  }, [visibleProfiles])

  const selectedVisibleCount = useMemo(() => {
    let n = 0
    visibleSelectable.forEach((tok) => {
      if (selectedKeys[tok]) n += 1
    })
    return n
  }, [visibleSelectable, selectedKeys])

  useEffect(() => {
    const el = headerCheckboxRef.current
    if (!el) return
    const total = visibleSelectable.length
    if (total === 0) {
      el.indeterminate = false
      el.checked = false
      return
    }
    el.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < total
    el.checked = selectedVisibleCount > 0 && selectedVisibleCount === total
  }, [visibleSelectable.length, selectedVisibleCount])

  useEffect(() => {
    // Keyboard shortcuts:
    // - / focus filter
    // - j/k or arrows move highlight
    // - space toggle selection on highlighted row
    // - enter open details
    // - s save selected (or highlighted if none)
    // - esc close details
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const tag = String(target?.tagName || '').toLowerCase()
      const isTyping =
        tag === 'input' ||
        tag === 'textarea' ||
        tag === 'select' ||
        (target as any)?.isContentEditable
      if (isTyping) return

      if (e.key === '/') {
        e.preventDefault()
        filterInputRef.current?.focus()
        return
      }

      if (e.key === '?') {
        e.preventDefault()
        setShowHelp((s) => !s)
        return
      }

      if (e.key === 'Escape') {
        if (showHelp) {
          setShowHelp(false)
          e.preventDefault()
          return
        }
        if (detailsToken) {
          setDetailsToken(null)
          e.preventDefault()
        }
        return
      }

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlightedIdx((i) => Math.min(visibleProfiles.length - 1, i + 1))
        return
      }

      if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlightedIdx((i) => Math.max(0, i - 1))
        return
      }

      if (e.key === ' ') {
        e.preventDefault()
        const p = visibleProfiles[highlightedIdx]
        const tok = p ? profileToken(p) : ''
        if (tok) toggleSelected(tok)
        return
      }

      if (e.key === 'Enter') {
        const p = visibleProfiles[highlightedIdx]
        const tok = p ? profileToken(p) : ''
        if (tok) {
          e.preventDefault()
          setDetailsToken(tok)
        }
        return
      }

      if (e.key.toLowerCase() === 's') {
        const p = visibleProfiles[highlightedIdx]
        const tok = p ? profileToken(p) : ''
        if (selectedList.length > 0) {
          e.preventDefault()
          void saveSelectedBuyersToRfp()
          return
        }
        if (tok) {
          e.preventDefault()
          void saveOneBuyerToRfp(tok)
        }
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    detailsToken,
    highlightedIdx,
    selectedList.length,
    visibleProfiles,
    showHelp,
  ])

  useEffect(() => {
    // Keep highlighted row visible.
    const el = document.querySelector(
      `[data-row-idx="${highlightedIdx}"]`,
    ) as HTMLElement | null
    if (el) el.scrollIntoView({ block: 'nearest' })
  }, [highlightedIdx])

  const detailsProfile = useMemo(() => {
    if (!detailsToken) return null
    // Prefer the currently visible list; fallback to all profiles.
    const fromVisible = visibleProfiles.find(
      (p) => profileToken(p) === detailsToken,
    )
    if (fromVisible) return fromVisible
    return sortedProfiles.find((p) => profileToken(p) === detailsToken) || null
  }, [detailsToken, visibleProfiles, sortedProfiles])

  const runLooksLikeAuthError =
    String(run?.error || '')
      .toLowerCase()
      .includes('session expired') ||
    String(run?.error || '')
      .toLowerCase()
      .includes('login/checkpoint') ||
    String(run?.error || '')
      .toLowerCase()
      .includes('checkpoint')

  const saveTopBuyersToRfp = async () => {
    if (!runId || !selectedRfpId) return
    setError(null)
    setSaveMessage(null)
    setSavingToRfp(true)
    try {
      const resp = await finderApi.saveTopToRfp(runId, {
        rfpId: selectedRfpId,
        topN: saveTopN,
        mode: saveMode,
      })
      setSaveMessage(
        `Saved ${resp.data?.saved ?? 0} buyers to this RFP (mode: ${
          resp.data?.mode || saveMode
        }, total saved: ${resp.data?.total ?? '—'}).`,
      )
      await refreshRfps()
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ||
          e?.response?.data?.error ||
          e?.message ||
          'Failed to save buyers to RFP',
      )
    } finally {
      setSavingToRfp(false)
    }
  }

  const saveSelectedBuyersToRfp = async () => {
    if (!runId || !selectedRfpId) return
    if (selectedList.length === 0) return
    setError(null)
    setSaveMessage(null)
    setSavingToRfp(true)
    try {
      const resp = await finderApi.saveTopToRfp(runId, {
        rfpId: selectedRfpId,
        mode: saveMode,
        selected: selectedList,
      })
      setSaveMessage(
        `Saved ${resp.data?.saved ?? 0} selected buyers to this RFP (mode: ${
          resp.data?.mode || saveMode
        }, total saved: ${resp.data?.total ?? '—'}).`,
      )
      await refreshRfps()
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ||
          e?.response?.data?.error ||
          e?.message ||
          'Failed to save buyers to RFP',
      )
    } finally {
      setSavingToRfp(false)
    }
  }

  const saveOneBuyerToRfp = async (token: string) => {
    if (!runId || !selectedRfpId) return
    if (!token) return
    setError(null)
    setSaveMessage(null)
    setSavingToRfp(true)
    try {
      const resp = await finderApi.saveTopToRfp(runId, {
        rfpId: selectedRfpId,
        mode: saveMode,
        selected: [token],
      })
      setSaveMessage(
        `Saved 1 buyer to this RFP (mode: ${
          resp.data?.mode || saveMode
        }, total saved: ${resp.data?.total ?? '—'}).`,
      )
      await refreshRfps()
    } catch (e: any) {
      setError(
        e?.response?.data?.detail ||
          e?.response?.data?.error ||
          e?.message ||
          'Failed to save buyer to RFP',
      )
    } finally {
      setSavingToRfp(false)
    }
  }

  const copySelectedToClipboard = async () => {
    const selectedSet = new Set(selectedList)
    const lines: string[] = []
    sortedProfiles.forEach((p) => {
      const tok = profileToken(p)
      if (!tok || !selectedSet.has(tok)) return
      const name = String(p?.name || '').trim() || 'Unknown'
      const title = String(p?.title || '').trim()
      const url = String(p?.profileUrl || '').trim()
      const score = String(p?.buyerScore ?? '').trim()
      const parts = [
        `${name}${title ? ` — ${title}` : ''}`,
        score ? `(score: ${score})` : '',
        url ? url : '',
      ].filter(Boolean)
      lines.push(parts.join(' '))
    })
    const text = lines.join('\n')
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setSaveMessage(`Copied ${lines.length} selected buyers to clipboard.`)
    } catch {
      setError('Could not write to clipboard. Try again or copy manually.')
    }
  }

  const openDetails = (p: any) => {
    const tok = profileToken(p)
    if (tok) setDetailsToken(tok)
  }

  return (
    <div className="space-y-8">
      <PipelineContextBanner
        variant="tool"
        title="This is a supporting mini-workflow."
        description="Use it to find likely buyers and attach them to an RFP (then review in Pipeline)."
        rightSlot={
          <Button as={Link} href="/rfps" variant="ghost" size="sm">
            View RFPs
          </Button>
        }
      />
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Buyer Profiles</h1>
        <p className="mt-2 text-sm text-gray-600">
          Upload a Playwright LinkedIn{' '}
          <span className="font-mono">storageState</span> once, then run a
          Finder job against an RFP to identify likely buyers.
        </p>
      </div>

      <StepsPanel
        title="Quick flow"
        tone="slate"
        columns={4}
        steps={[
          {
            title: 'Connect',
            description: (
              <>
                Upload a fresh <span className="font-mono">storageState</span>.
              </>
            ),
          },
          {
            title: 'Select RFP',
            description: 'Choose where buyers should attach.',
          },
          { title: 'Run', description: 'Generate and score buyer candidates.' },
          {
            title: 'Save',
            description: 'Save buyers to the RFP, then go back to Pipeline.',
          },
        ]}
      />

      <div className="bg-white shadow rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Run Finder</h2>
          <div className="text-xs text-gray-600">
            LinkedIn session:{' '}
            <span
              className={
                linkedinConnected
                  ? 'text-green-700 font-semibold'
                  : linkedinConnected === false
                  ? 'text-red-700 font-semibold'
                  : 'text-gray-700'
              }
            >
              {linkedinConnected === null
                ? 'checking…'
                : linkedinConnected
                ? 'connected'
                : 'not connected'}
            </span>
          </div>
        </div>

        {run?.status === 'error' && runLooksLikeAuthError && (
          <div className="border border-amber-200 bg-amber-50 rounded-md p-3 text-sm text-amber-900">
            <div className="font-semibold">
              LinkedIn session needs reconnect
            </div>
            <div className="mt-1 text-xs text-amber-800">
              This run failed because your saved LinkedIn session appears
              expired or hit a checkpoint. Upload a fresh{' '}
              <span className="font-mono">storageState</span> and re-run.
            </div>
            <div className="mt-3 flex items-center gap-2">
              <button
                onClick={validateSession}
                disabled={validatingSession}
                className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-amber-300 text-amber-900 bg-white hover:bg-amber-100 disabled:opacity-50"
              >
                {validatingSession ? 'Validating…' : 'Validate session'}
              </button>
              <Link
                href="#upload-storage-state"
                className="text-sm text-amber-900 underline"
              >
                Upload storageState →
              </Link>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700">
              Select RFP
            </label>
            <select
              value={selectedRfpId}
              onChange={(e) => setSelectedRfpId(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
            >
              <option value="">Select…</option>
              {rfps.map((r) => (
                <option key={r?._id} value={r?._id}>
                  {(r?.clientName ? `${r.clientName} — ` : '') +
                    (r?.title || r?._id)}
                </option>
              ))}
            </select>
            {selectedRfp?._id && (
              <div className="mt-2">
                <Link
                  href={`/rfps/${selectedRfp._id}`}
                  className="text-xs text-primary-600 hover:text-primary-800"
                >
                  View selected RFP →
                </Link>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Max people
            </label>
            <input
              type="number"
              value={maxPeople}
              onChange={(e) => setMaxPeople(Number(e.target.value || 0))}
              min={1}
              max={200}
              className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700">
              Company LinkedIn URL (recommended)
            </label>
            <input
              value={companyLinkedInUrl}
              onChange={(e) => setCompanyLinkedInUrl(e.target.value)}
              placeholder="https://www.linkedin.com/company/acme-inc/"
              className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
            />
            <p className="mt-1 text-xs text-gray-600">
              If empty, we’ll attempt to search LinkedIn using the RFP client
              name.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Upload storageState
            </label>
            <input
              id="upload-storage-state"
              type="file"
              accept="application/json,.json"
              disabled={storageStateUploading}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) uploadStorageState(f)
              }}
              className="mt-1 w-full text-sm"
            />
            <p className="mt-1 text-xs text-gray-600">
              Upload once per user. Stored encrypted server-side.
            </p>
            {sessionValidation?.ok === true && (
              <div className="mt-1 text-xs text-green-700">
                Session validated.
              </div>
            )}
            {sessionValidation?.ok === false && (
              <div className="mt-1 text-xs text-red-700">
                Session invalid: {sessionValidation?.reason || 'Unknown reason'}
              </div>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Target titles (one per line)
          </label>
          <textarea
            value={targetTitlesText}
            onChange={(e) => setTargetTitlesText(e.target.value)}
            rows={4}
            className="mt-1 w-full border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => refreshLinkedInStatus()}
            className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
          >
            Refresh status
          </button>
          <button
            onClick={validateSession}
            disabled={validatingSession || linkedinConnected === false}
            className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            {validatingSession ? 'Validating…' : 'Validate session'}
          </button>
          <button
            onClick={startRun}
            disabled={
              isStartingRun ||
              !selectedRfpId ||
              linkedinConnected === false ||
              linkedinConnected === null
            }
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
          >
            {isStartingRun ? 'Starting…' : 'Run Finder'}
          </button>
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}
        {saveMessage && (
          <div className="text-sm text-green-700">{saveMessage}</div>
        )}

        {run && (
          <div className="border rounded-md p-3 bg-gray-50 text-sm text-gray-800">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-semibold">Run:</span>{' '}
                <span className="font-mono text-xs">{runId}</span>
              </div>
              <div>
                <span className="font-semibold">Status:</span>{' '}
                <span>{run?.status}</span>
              </div>
            </div>
            {run?.progress && (
              <div className="mt-2 text-xs text-gray-700">
                Discovered: {run.progress?.discovered || 0} · Saved:{' '}
                {run.progress?.saved || 0} · Scored: {run.progress?.scored || 0}
              </div>
            )}
            {run?.error && (
              <div className="mt-2 text-xs text-red-700">{run.error}</div>
            )}
          </div>
        )}

        {run?.status === 'done' &&
          sortedProfiles.length > 0 &&
          selectedRfpId && (
            <div className="border rounded-md p-3 bg-white">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-900">
                  Save buyers to this RFP
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-700">Mode</label>
                  <select
                    value={saveMode}
                    onChange={(e) =>
                      setSaveMode(
                        e.target.value === 'overwrite' ? 'overwrite' : 'merge',
                      )
                    }
                    className="border border-gray-300 rounded-md px-2 py-1 bg-gray-100 text-gray-900 text-sm"
                  >
                    <option value="merge">Merge</option>
                    <option value="overwrite">Overwrite</option>
                  </select>
                  <label className="text-xs text-gray-700">Top</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={saveTopN}
                    onChange={(e) => setSaveTopN(Number(e.target.value || 0))}
                    className="w-20 border border-gray-300 rounded-md px-2 py-1 bg-gray-100 text-gray-900 text-sm"
                  />
                  <button
                    onClick={saveTopBuyersToRfp}
                    disabled={savingToRfp}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                  >
                    {savingToRfp ? 'Saving…' : 'Save to RFP'}
                  </button>
                </div>
              </div>
              {selectedRfp?._id && (
                <div className="mt-2 text-xs text-gray-600">
                  Merge will dedupe by profile URL/ID and keep best info. View
                  results on the RFP page:{' '}
                  <Link
                    href={`/rfps/${selectedRfp._id}`}
                    className="text-primary-600 hover:text-primary-800"
                  >
                    open RFP →
                  </Link>
                </div>
              )}
            </div>
          )}
      </div>

      {sortedProfiles.length > 0 && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-5 border-b border-gray-200">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-lg font-semibold text-gray-900">
                Buyer candidates
              </h2>
              <div className="text-xs text-gray-600">
                Selected:{' '}
                <span className="font-semibold">{selectedList.length}</span>
              </div>
            </div>
          </div>
          <div className="px-6 py-4 overflow-x-auto">
            <div className="mb-3 flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                    placeholder="Filter by name/title/location…"
                    ref={filterInputRef}
                    className="w-64 border border-gray-300 rounded-md px-3 py-2 bg-gray-100 text-gray-900 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => selectTopN(10)}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                  >
                    Select top 10
                  </button>
                  <button
                    type="button"
                    onClick={selectAllVisible}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                  >
                    Select all visible
                  </button>
                  <button
                    type="button"
                    onClick={clearSelection}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                  >
                    Clear
                  </button>

                  <div className="ml-2 flex items-center gap-2">
                    <label className="text-xs text-gray-700">Min score</label>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={minScore}
                      onChange={(e) => setMinScore(Number(e.target.value || 0))}
                    />
                    <span className="text-xs text-gray-700 w-8 text-right">
                      {minScore}
                    </span>
                  </div>

                  <label className="ml-2 flex items-center gap-2 text-xs text-gray-700 select-none">
                    <input
                      type="checkbox"
                      checked={showSelectedOnly}
                      onChange={(e) =>
                        setShowSelectedOnly(Boolean(e.target.checked))
                      }
                    />
                    Only selected
                  </label>
                  <label className="ml-2 flex items-center gap-2 text-xs text-gray-700 select-none">
                    <input
                      type="checkbox"
                      checked={selectedFirst}
                      onChange={(e) =>
                        setSelectedFirst(Boolean(e.target.checked))
                      }
                    />
                    Selected first
                  </label>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <label className="text-xs text-gray-700">Mode</label>
                  <select
                    value={saveMode}
                    onChange={(e) =>
                      setSaveMode(
                        e.target.value === 'overwrite' ? 'overwrite' : 'merge',
                      )
                    }
                    className="border border-gray-300 rounded-md px-2 py-1 bg-gray-100 text-gray-900 text-sm"
                  >
                    <option value="merge">Merge</option>
                    <option value="overwrite">Overwrite</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      setFilterText('')
                      setMinScore(0)
                      setShowSelectedOnly(false)
                      setSelectedFirst(true)
                      setFunctionFilters([])
                      setSeniorityFilters([])
                      setSortKey('buyerScore')
                      setSortDir('desc')
                      setHighlightedIdx(0)
                    }}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                  >
                    Reset
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowHelp((s) => !s)}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                    aria-label="Keyboard shortcuts"
                    title="Keyboard shortcuts (?)"
                  >
                    ?
                  </button>
                  <button
                    type="button"
                    onClick={copySelectedToClipboard}
                    disabled={selectedList.length === 0}
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50 disabled:opacity-50"
                  >
                    Copy selected
                  </button>
                  <button
                    type="button"
                    onClick={saveSelectedBuyersToRfp}
                    disabled={
                      savingToRfp ||
                      selectedList.length === 0 ||
                      !selectedRfpId ||
                      !runId
                    }
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                  >
                    {savingToRfp ? 'Saving…' : 'Save selected'}
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-gray-600">Function:</span>
                {[
                  { id: 'procurement', label: 'Procurement' },
                  { id: 'operations', label: 'Ops' },
                  { id: 'finance', label: 'Finance' },
                  { id: 'it', label: 'IT/Security' },
                  { id: 'facilities', label: 'Facilities' },
                  { id: 'sustainability', label: 'Sustainability' },
                  { id: 'project', label: 'Project/Program' },
                  { id: 'supply_chain', label: 'Supply Chain' },
                ].map((c) => {
                  const on = functionFilters.includes(c.id)
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() =>
                        setFunctionFilters((prev) =>
                          on ? prev.filter((x) => x !== c.id) : [...prev, c.id],
                        )
                      }
                      className={`px-2 py-1 rounded-full text-xs border ${
                        on
                          ? 'bg-blue-50 border-blue-200 text-blue-800'
                          : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {c.label}
                    </button>
                  )
                })}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-gray-600">Seniority:</span>
                {[
                  { id: 'c_level', label: 'C-level' },
                  { id: 'vp', label: 'VP' },
                  { id: 'head', label: 'Head' },
                  { id: 'director', label: 'Director' },
                  { id: 'manager', label: 'Mgr/Lead' },
                ].map((c) => {
                  const on = seniorityFilters.includes(c.id)
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() =>
                        setSeniorityFilters((prev) =>
                          on ? prev.filter((x) => x !== c.id) : [...prev, c.id],
                        )
                      }
                      className={`px-2 py-1 rounded-full text-xs border ${
                        on
                          ? 'bg-indigo-50 border-indigo-200 text-indigo-800'
                          : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {c.label}
                    </button>
                  )
                })}
              </div>
            </div>

            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-gray-500">
                  <th className="py-2 pr-4">
                    <input
                      ref={headerCheckboxRef}
                      type="checkbox"
                      onChange={() => {
                        const total = visibleSelectable.length
                        if (total === 0) return
                        if (selectedVisibleCount === total) {
                          setSelectedKeys((prev) => {
                            const next = { ...prev }
                            visibleSelectable.forEach((tok) => {
                              delete next[tok]
                            })
                            return next
                          })
                        } else {
                          selectAllVisible()
                        }
                      }}
                    />
                  </th>
                  <th className="py-2 pr-4">
                    <button
                      type="button"
                      className="hover:text-gray-800"
                      onClick={() => toggleSort('buyerScore')}
                    >
                      Score {sortLabel('buyerScore')}
                    </button>
                  </th>
                  <th className="py-2 pr-4">
                    <button
                      type="button"
                      className="hover:text-gray-800"
                      onClick={() => toggleSort('name')}
                    >
                      Name {sortLabel('name')}
                    </button>
                  </th>
                  <th className="py-2 pr-4">
                    <button
                      type="button"
                      className="hover:text-gray-800"
                      onClick={() => toggleSort('title')}
                    >
                      Title {sortLabel('title')}
                    </button>
                  </th>
                  <th className="py-2 pr-4">
                    <button
                      type="button"
                      className="hover:text-gray-800"
                      onClick={() => toggleSort('location')}
                    >
                      Location {sortLabel('location')}
                    </button>
                  </th>
                  <th className="py-2 pr-4">Profile</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {visibleProfiles.map((p, idx) => {
                  const token = profileToken(p)
                  const checked = token ? Boolean(selectedKeys[token]) : false
                  const saved = token ? savedTokens.has(token) : false
                  const rowKey = profileRowKey(p)
                  const highlighted = idx === highlightedIdx
                  return (
                    <tr
                      key={rowKey}
                      data-row-idx={idx}
                      className={`align-top ${checked ? 'bg-blue-50' : ''} ${
                        token ? 'cursor-pointer hover:bg-gray-50' : ''
                      } ${highlighted ? 'ring-2 ring-blue-300' : ''}`}
                      onMouseEnter={() => setHighlightedIdx(idx)}
                      onClick={() => {
                        if (!token) return
                        setHighlightedIdx(idx)
                        toggleSelected(token)
                      }}
                    >
                      <td className="py-3 pr-4">
                        <input
                          type="checkbox"
                          disabled={!token}
                          checked={checked}
                          onChange={() => {
                            if (!token) return
                            toggleSelected(token)
                          }}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </td>
                      <td className="py-3 pr-4 font-semibold text-gray-900">
                        {p?.buyerScore ?? 0}
                      </td>
                      <td className="py-3 pr-4 text-gray-900">
                        <button
                          type="button"
                          className="text-left text-gray-900 hover:underline"
                          onClick={(e) => {
                            e.stopPropagation()
                            openDetails(p)
                          }}
                        >
                          {p?.name || '—'}
                        </button>
                        {saved && (
                          <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                            Saved
                          </span>
                        )}
                        {p?.ai?.personaSummary && (
                          <div className="mt-1 text-xs text-gray-700 max-w-xl">
                            {p.ai.personaSummary}
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-4 text-gray-900">
                        {p?.title || '—'}
                      </td>
                      <td className="py-3 pr-4 text-gray-700">
                        {p?.location || '—'}
                      </td>
                      <td className="py-3 pr-4">
                        {p?.profileUrl ? (
                          <a
                            href={p.profileUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="text-primary-600 hover:text-primary-800"
                            onClick={(e) => e.stopPropagation()}
                          >
                            Open →
                          </a>
                        ) : (
                          '—'
                        )}
                        {Array.isArray(p?.buyerReasons) &&
                          p.buyerReasons.length > 0 && (
                            <div className="mt-1 text-xs text-gray-600">
                              {p.buyerReasons.slice(0, 2).join(' · ')}
                            </div>
                          )}
                      </td>
                      <td className="py-3 pr-4">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            if (!token) return
                            saveOneBuyerToRfp(token)
                          }}
                          disabled={
                            !token || !selectedRfpId || !runId || savingToRfp
                          }
                          className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            openDetails(p)
                          }}
                          disabled={!token}
                          className="ml-2 inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50 disabled:opacity-50"
                        >
                          Details
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="mt-2 text-xs text-gray-600">
              Showing {visibleProfiles.length} of {filteredProfiles.length}{' '}
              results{filterText ? ' (filtered)' : ''}.
            </div>
          </div>
        </div>
      )}

      {/* Keyboard shortcuts help */}
      {showHelp && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setShowHelp(false)}
          />
          <div className="absolute left-1/2 top-24 w-[92vw] max-w-xl -translate-x-1/2 rounded-xl bg-white shadow-2xl border border-gray-200">
            <div className="p-4 border-b border-gray-200 flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-semibold text-gray-900">
                  Keyboard shortcuts
                </div>
                <div className="mt-1 text-xs text-gray-600">
                  Press <span className="font-mono">?</span> to toggle,{' '}
                  <span className="font-mono">Esc</span> to close.
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowHelp(false)}
                className="text-gray-500 hover:text-gray-900"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <div className="p-4 text-sm text-gray-800 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <div className="font-semibold text-gray-900">Navigation</div>
                <div className="mt-1 text-xs text-gray-700 space-y-1">
                  <div>
                    <span className="font-mono">j/k</span> or{' '}
                    <span className="font-mono">↑/↓</span> — move highlight
                  </div>
                  <div>
                    <span className="font-mono">Enter</span> — open details
                  </div>
                  <div>
                    <span className="font-mono">Esc</span> — close details/help
                  </div>
                </div>
              </div>
              <div>
                <div className="font-semibold text-gray-900">Actions</div>
                <div className="mt-1 text-xs text-gray-700 space-y-1">
                  <div>
                    <span className="font-mono">Space</span> — toggle select
                  </div>
                  <div>
                    <span className="font-mono">s</span> — save selected (or
                    highlighted)
                  </div>
                  <div>
                    <span className="font-mono">/</span> — focus filter
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sticky bulk action bar */}
      {selectedList.length > 0 && (
        <div className="fixed bottom-4 left-4 right-4 lg:left-72 z-40">
          <div className="mx-auto max-w-5xl bg-white border border-gray-200 shadow-lg rounded-xl px-4 py-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm text-gray-900">
              <span className="font-semibold">{selectedList.length}</span>{' '}
              selected
              <span className="ml-2 text-xs text-gray-600">
                (space toggles, j/k moves, s saves)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={copySelectedToClipboard}
                className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
              >
                Copy
              </button>
              <button
                type="button"
                onClick={saveSelectedBuyersToRfp}
                disabled={savingToRfp || !selectedRfpId || !runId}
                className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
              >
                {savingToRfp ? 'Saving…' : 'Save to RFP'}
              </button>
              <button
                type="button"
                onClick={clearSelection}
                className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
              >
                Clear
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Details drawer */}
      {detailsProfile && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setDetailsToken(null)}
          />
          <div className="absolute right-0 top-0 h-full w-full sm:w-[520px] bg-white shadow-2xl border-l border-gray-200 overflow-y-auto">
            <div className="p-5 border-b border-gray-200 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-lg font-semibold text-gray-900 truncate">
                  {detailsProfile?.name || 'Buyer'}
                </div>
                <div className="mt-1 text-sm text-gray-700">
                  {detailsProfile?.title || '—'}
                </div>
                <div className="mt-1 text-xs text-gray-600">
                  {detailsProfile?.location || '—'} · Score:{' '}
                  <span className="font-semibold">
                    {detailsProfile?.buyerScore ?? 0}
                  </span>
                  {isSaved(detailsProfile) && (
                    <>
                      {' '}
                      ·{' '}
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                        Saved to RFP
                      </span>
                    </>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDetailsToken(null)}
                className="text-gray-500 hover:text-gray-900"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const tok = profileToken(detailsProfile)
                    if (tok) toggleSelected(tok)
                  }}
                  className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                >
                  Toggle select
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const tok = profileToken(detailsProfile)
                    if (tok) saveOneBuyerToRfp(tok)
                  }}
                  disabled={!selectedRfpId || !runId || savingToRfp}
                  className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                >
                  {savingToRfp ? 'Saving…' : 'Save to RFP'}
                </button>
                {detailsProfile?.profileUrl ? (
                  <a
                    href={detailsProfile.profileUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-800 bg-white hover:bg-gray-50"
                  >
                    Open LinkedIn →
                  </a>
                ) : null}
              </div>

              {Array.isArray(detailsProfile?.buyerReasons) &&
                detailsProfile.buyerReasons.length > 0 && (
                  <div className="border border-gray-200 rounded-lg p-4">
                    <div className="text-sm font-semibold text-gray-900">
                      Why this is a buyer
                    </div>
                    <ul className="mt-2 text-sm text-gray-700 list-disc pl-5 space-y-1">
                      {detailsProfile.buyerReasons
                        .slice(0, 10)
                        .map((r: any, i: number) => (
                          <li key={i}>{String(r)}</li>
                        ))}
                    </ul>
                  </div>
                )}

              {detailsProfile?.ai?.personaSummary && (
                <div className="border border-gray-200 rounded-lg p-4">
                  <div className="text-sm font-semibold text-gray-900">
                    Persona summary
                  </div>
                  <div className="mt-2 text-sm text-gray-700">
                    {detailsProfile.ai.personaSummary}
                  </div>
                </div>
              )}

              {Array.isArray(detailsProfile?.ai?.likelyGoals) &&
                detailsProfile.ai.likelyGoals.length > 0 && (
                  <div className="border border-gray-200 rounded-lg p-4">
                    <div className="text-sm font-semibold text-gray-900">
                      Likely goals
                    </div>
                    <ul className="mt-2 text-sm text-gray-700 list-disc pl-5 space-y-1">
                      {detailsProfile.ai.likelyGoals
                        .slice(0, 10)
                        .map((r: any, i: number) => (
                          <li key={i}>{String(r)}</li>
                        ))}
                    </ul>
                  </div>
                )}

              {Array.isArray(detailsProfile?.ai?.likelyConcerns) &&
                detailsProfile.ai.likelyConcerns.length > 0 && (
                  <div className="border border-gray-200 rounded-lg p-4">
                    <div className="text-sm font-semibold text-gray-900">
                      Likely concerns
                    </div>
                    <ul className="mt-2 text-sm text-gray-700 list-disc pl-5 space-y-1">
                      {detailsProfile.ai.likelyConcerns
                        .slice(0, 10)
                        .map((r: any, i: number) => (
                          <li key={i}>{String(r)}</li>
                        ))}
                    </ul>
                  </div>
                )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
