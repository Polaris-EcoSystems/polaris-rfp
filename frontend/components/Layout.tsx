'use client'

import {
  Bars3Icon,
  BellIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  CogIcon,
  DocumentTextIcon,
  FolderIcon,
  UserCircleIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { ReactNode, useEffect, useRef, useState } from 'react'
import api, { extractList, rfpApi, type RFP } from '../lib/api'
import { useAuth } from '../lib/auth'
import GlobalSearch from './GlobalSearch'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [topMenuOpen, setTopMenuOpen] = useState(false)
  const [footerMenuOpen, setFooterMenuOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [backendUp, setBackendUp] = useState<boolean | null>(null)
  const [backendLastCheckedAt, setBackendLastCheckedAt] = useState<Date | null>(
    null,
  )
  const [notificationItems, setNotificationItems] = useState<
    {
      id: string
      title: string
      subtitle: string
      tone: 'danger' | 'warning' | 'info'
    }[]
  >([])
  const [notificationsLoading, setNotificationsLoading] = useState(false)
  const router = useRouter()
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const topMenuRef = useRef<HTMLDivElement | null>(null)
  const footerMenuRef = useRef<HTMLDivElement | null>(null)
  const notificationsRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    function handleDocClick(e: MouseEvent) {
      const target = e.target as Node
      if (topMenuRef.current && !topMenuRef.current.contains(target)) {
        setTopMenuOpen(false)
      }
      if (footerMenuRef.current && !footerMenuRef.current.contains(target)) {
        setFooterMenuOpen(false)
      }
      if (
        notificationsRef.current &&
        !notificationsRef.current.contains(target)
      ) {
        setNotificationsOpen(false)
      }
    }

    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setTopMenuOpen(false)
        setFooterMenuOpen(false)
        setNotificationsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleDocClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleDocClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [])

  // Heartbeat: check backend is reachable every minute.
  useEffect(() => {
    let mounted = true
    let timer: any = null

    const check = async () => {
      try {
        // Backend responds at "/" with JSON health data.
        await api.get('/')
        if (!mounted) return
        setBackendUp(true)
        setBackendLastCheckedAt(new Date())
      } catch (_e) {
        if (!mounted) return
        setBackendUp(false)
        setBackendLastCheckedAt(new Date())
      }
    }

    check()
    timer = window.setInterval(check, 60_000)
    return () => {
      mounted = false
      if (timer) window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (!notificationsOpen) return
    let mounted = true
    const load = async () => {
      try {
        setNotificationsLoading(true)
        const resp = await rfpApi.list()
        const rfps = extractList<RFP>(resp)

        const items: {
          id: string
          title: string
          subtitle: string
          tone: 'danger' | 'warning' | 'info'
        }[] = []

        rfps.forEach((r) => {
          const warnings = Array.isArray(r.dateWarnings) ? r.dateWarnings : []
          const due =
            r.submissionDeadline && r.submissionDeadline !== 'Not available'
              ? r.submissionDeadline
              : null

          // Due soon / past
          const subMeta = (r.dateMeta as any)?.dates?.submissionDeadline
          const daysUntil =
            typeof subMeta?.daysUntil === 'number' ? subMeta.daysUntil : null

          if (typeof daysUntil === 'number') {
            if (daysUntil <= 0) {
              items.push({
                id: `${r._id}:due`,
                title: `${r.title}`,
                subtitle: `Submission deadline appears past (${
                  due || 'unknown'
                })`,
                tone: 'danger',
              })
            } else if (daysUntil <= 7) {
              items.push({
                id: `${r._id}:due`,
                title: `${r.title}`,
                subtitle: `Due in ${daysUntil} days (${due})`,
                tone: 'warning',
              })
            }
          }

          // Date sanity warnings (only show top 1 per RFP)
          const w = warnings.find(
            (x) => typeof x === 'string' && x.trim().length > 0,
          )
          if (w) {
            items.push({
              id: `${r._id}:warn`,
              title: `${r.title}`,
              subtitle: w,
              tone: 'info',
            })
          }
        })

        // Sort: danger, warning, info
        const order = { danger: 0, warning: 1, info: 2 } as const
        items.sort((a, b) => order[a.tone] - order[b.tone])

        if (mounted) setNotificationItems(items.slice(0, 10))
      } catch (_e) {
        if (mounted) setNotificationItems([])
      } finally {
        if (mounted) setNotificationsLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [notificationsOpen])

  // Search moved to GlobalSearch component

  const navigation = [
    {
      name: 'Dashboard',
      href: '/',
      icon: FolderIcon,
      current: pathname === '/',
    },
    {
      name: 'RFPs',
      href: '/rfps',
      icon: DocumentTextIcon,
      current: pathname.startsWith('/rfps'),
    },
    {
      name: 'Finder',
      href: '/finder',
      icon: DocumentTextIcon,
      current: pathname === '/finder',
    },
    {
      name: 'LinkedIn Finder',
      href: '/linkedin-finder',
      icon: UserGroupIcon,
      current: pathname === '/linkedin-finder',
    },
    {
      name: 'Proposals',
      href: '/proposals',
      icon: DocumentTextIcon,
      current: pathname.startsWith('/proposals'),
    },
    {
      name: 'Templates',
      href: '/templates',
      icon: CogIcon,
      current: pathname.startsWith('/templates'),
    },
    {
      name: 'Content Library',
      href: '/content',
      icon: UserGroupIcon,
      current: pathname === '/content',
    },
    {
      name: 'Profile',
      href: '/profile',
      icon: UserCircleIcon,
      current: pathname === '/profile',
    },
    {
      name: 'Integrations',
      href: '/integrations/canva',
      icon: CogIcon,
      current: pathname.startsWith('/integrations'),
    },
    // { name: 'Google Drive', href: '/googledrive', icon: CloudIcon, current: router.pathname === '/googledrive' },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-gray-600 bg-opacity-75 transition-opacity lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-white shadow-xl transform transition-transform duration-300 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 bg-gradient-to-r from-blue-600 to-indigo-600">
          <div className="flex items-center space-x-3">
            <div className="flex-shrink-0">
              {/* <SparklesIcon className="h-8 w-8 text-white" /> */}
            </div>
            <h1 className="text-xl font-bold text-white">RFP System</h1>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden text-white hover:text-gray-200"
          >
            <XMarkIcon className="h-6 w-6" />
          </button>
        </div>

        <nav className="mt-6 px-3 space-y-2">
          {navigation.map((item) => (
            <Link
              key={item.name}
              href={item.href}
              className={`group flex items-center px-3 py-3 text-sm font-medium rounded-xl transition-all duration-200 ${
                item.current
                  ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg transform scale-105'
                  : 'text-gray-700 hover:text-gray-900 hover:bg-gray-100 hover:shadow-md hover:transform hover:scale-105'
              }`}
              onClick={() => setSidebarOpen(false)}
            >
              <item.icon
                className={`mr-4 flex-shrink-0 h-6 w-6 transition-colors ${
                  item.current
                    ? 'text-white'
                    : 'text-gray-400 group-hover:text-gray-600'
                }`}
              />
              <span className="font-medium">{item.name}</span>
              {item.current && (
                <div className="ml-auto w-2 h-2 bg-white rounded-full animate-pulse" />
              )}
            </Link>
          ))}
        </nav>

        {/* Sidebar footer */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200">
          <div className="flex items-center justify-between p-3 bg-gradient-to-r from-gray-50 to-blue-50 rounded-xl">
            <div
              ref={footerMenuRef}
              className="flex items-center space-x-3 relative"
            >
              <UserCircleIcon className="h-8 w-8 text-gray-400" />
              <div>
                {user ? (
                  <>
                    <button
                      onClick={() => setFooterMenuOpen((s) => !s)}
                      className="text-left"
                      aria-expanded={footerMenuOpen}
                    >
                      <p className="text-sm font-medium text-gray-900">
                        {user.username}
                      </p>
                      <p className="text-xs text-gray-500">
                        {user.email || ''}
                      </p>
                    </button>
                    {footerMenuOpen && (
                      <div className="absolute left-0 bottom-full mb-4 w-48 bg-white border border-gray-200 rounded-lg shadow-xl z-50">
                        <div className="py-1.5">
                          <button
                            onClick={async () => {
                              setFooterMenuOpen(false)
                              await logout()
                              router.push('/login')
                            }}
                            className="w-full text-left px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 hover:text-red-700 transition-colors duration-150 flex items-center gap-2 rounded-md"
                          >
                            <svg
                              className="h-4 w-4"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                              />
                            </svg>
                            Logout
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <p className="text-sm font-medium text-gray-900">Guest</p>
                    <Link href="/login" className="text-xs text-blue-600">
                      Sign in
                    </Link>
                  </>
                )}
              </div>
            </div>
            {footerMenuOpen ? (
              <ChevronUpIcon className="h-5 w-5 text-gray-400" />
            ) : (
              <ChevronDownIcon className="h-5 w-5 text-gray-400" />
            )}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Top navigation bar */}
        <header className="bg-white/80 backdrop-blur-sm shadow-sm border-b border-gray-200/50 sticky top-0 z-30">
          <div className="flex items-center justify-between h-16 px-4 sm:px-6 lg:px-8">
            <div className="flex items-center space-x-4">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors"
              >
                <Bars3Icon className="h-6 w-6" />
              </button>
              <div className="hidden sm:block">
                <div className="relative">
                  <GlobalSearch />
                </div>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div
                className="hidden sm:flex items-center gap-2 text-xs text-gray-600"
                title={
                  backendUp === null
                    ? 'Checking backend…'
                    : backendUp
                    ? `Backend reachable${
                        backendLastCheckedAt
                          ? ` (checked ${backendLastCheckedAt.toLocaleTimeString()})`
                          : ''
                      }`
                    : `Backend unreachable${
                        backendLastCheckedAt
                          ? ` (checked ${backendLastCheckedAt.toLocaleTimeString()})`
                          : ''
                      }`
                }
              >
                <span
                  className={`h-2 w-2 rounded-full ${
                    backendUp === null
                      ? 'bg-gray-300'
                      : backendUp
                      ? 'bg-green-500'
                      : 'bg-red-500'
                  }`}
                />
                <span>API</span>
              </div>
              <div ref={notificationsRef} className="relative">
                <button
                  onClick={() => setNotificationsOpen((s) => !s)}
                  className="p-2 rounded-xl text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-all duration-200 relative"
                  aria-expanded={notificationsOpen}
                  aria-label="Notifications"
                  type="button"
                >
                  <BellIcon className="h-6 w-6" />
                </button>
                {notificationsOpen && (
                  <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-xl z-50">
                    <div className="px-4 py-3 border-b border-gray-100">
                      <div className="text-sm font-semibold text-gray-900">
                        Notifications
                      </div>
                      <div className="text-xs text-gray-500">
                        Due date reminders and updates
                      </div>
                    </div>
                    <div className="px-4 py-3 text-sm text-gray-700">
                      {notificationsLoading ? (
                        <div className="py-4 text-gray-600">Loading…</div>
                      ) : notificationItems.length === 0 ? (
                        <div className="py-4 text-gray-600">
                          No notifications yet.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {notificationItems.map((it) => (
                            <button
                              key={it.id}
                              type="button"
                              onClick={() => {
                                setNotificationsOpen(false)
                                // Try to route to the RFP details if we can infer the ID from the composite key
                                const rfpId = it.id.split(':')[0]
                                if (rfpId) router.push(`/rfps/${rfpId}`)
                              }}
                              className="w-full text-left p-2 rounded-md hover:bg-gray-50"
                            >
                              <div className="flex items-start gap-2">
                                <div
                                  className={`mt-1 h-2 w-2 rounded-full ${
                                    it.tone === 'danger'
                                      ? 'bg-red-500'
                                      : it.tone === 'warning'
                                      ? 'bg-amber-500'
                                      : 'bg-blue-500'
                                  }`}
                                />
                                <div className="min-w-0">
                                  <div className="text-sm font-medium text-gray-900 truncate">
                                    {it.title}
                                  </div>
                                  <div className="text-xs text-gray-600 line-clamp-2">
                                    {it.subtitle}
                                  </div>
                                </div>
                              </div>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div ref={topMenuRef} className="relative">
                <button
                  onClick={() => setTopMenuOpen((s) => !s)}
                  className="flex items-center space-x-3 p-2 rounded-xl hover:bg-gray-100 transition-colors"
                  aria-expanded={topMenuOpen}
                >
                  <UserCircleIcon className="h-8 w-8 text-gray-600" />
                  <div className="hidden sm:block text-left">
                    {user ? (
                      <>
                        <p className="text-sm font-medium text-gray-900">
                          {user.username}
                        </p>
                        <p className="text-xs text-gray-500">Online</p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-medium text-gray-900">
                          Guest
                        </p>
                        <p className="text-xs text-gray-500">Offline</p>
                      </>
                    )}
                  </div>
                  {/* chevron indicating menu state */}
                  {topMenuOpen ? (
                    <ChevronUpIcon className="h-4 w-4 text-gray-400" />
                  ) : (
                    <ChevronDownIcon className="h-4 w-4 text-gray-400" />
                  )}
                </button>
                {topMenuOpen && (
                  <div className="absolute right-0 mt-2 w-52 bg-white border border-gray-200 rounded-lg shadow-xl z-50">
                    <div className="py-1.5">
                      <button
                        onClick={async () => {
                          setTopMenuOpen(false)
                          await logout()
                          router.push('/login')
                        }}
                        className="w-full text-left px-4 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 hover:text-red-700 transition-colors duration-150 flex items-center gap-2 rounded-md"
                      >
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                          />
                        </svg>
                        Logout
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Main content area */}
        <main className="min-h-screen">
          <div className="py-8">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
