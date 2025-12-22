'use client'

import {
  Dialog,
  DialogPanel,
  DialogTitle,
  Menu,
  MenuButton,
  MenuItem,
  MenuItems,
  Transition,
} from '@headlessui/react'
import {
  Bars3Icon,
  BellIcon,
  ChartBarIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  CogIcon,
  CpuChipIcon,
  DocumentTextIcon,
  FolderIcon,
  MagnifyingGlassIcon,
  UserCircleIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useLocale, useTranslations } from 'next-intl'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  Fragment,
  ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import api, { extractList, proxyUrl, rfpApi, type RFP } from '../lib/api'
import { useAuth } from '../lib/auth'
import AuthRefreshStatus from './AuthRefreshStatus'
import GlobalSearch from './GlobalSearch'
import Modal from './ui/Modal'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const t = useTranslations()
  const locale = useLocale()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [searchModalOpen, setSearchModalOpen] = useState(false)
  // Legacy notification popover wiring (kept for compatibility with older header markup)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const notificationsRef = useRef<HTMLDivElement | null>(null)
  const [notificationsRequestedAt, setNotificationsRequestedAt] = useState(0)
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

  useEffect(() => {
    if (!notificationsOpen) return
    const onPointerDown = (e: MouseEvent) => {
      const el = notificationsRef.current
      if (!el) return
      if (e.target && el.contains(e.target as Node)) return
      setNotificationsOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNotificationsOpen(false)
    }
    window.addEventListener('mousedown', onPointerDown)
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('mousedown', onPointerDown)
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [notificationsOpen])

  // Heartbeat: check backend is reachable every minute.
  useEffect(() => {
    let mounted = true
    let timer: any = null

    const check = async () => {
      try {
        // Backend responds at "/" with JSON health data.
        await api.get(proxyUrl(''))
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
    if (!notificationsRequestedAt) return
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
  }, [notificationsRequestedAt])

  // Search moved to GlobalSearch component

  type NavItem = {
    id: string
    label: string
    href: string
    icon: any
    current: boolean
  }

  const primaryNav: NavItem[] = useMemo(
    () => [
      {
        id: 'pipeline',
        label: t('nav.pipeline'),
        href: '/pipeline',
        icon: ChartBarIcon,
        current: pathname.startsWith('/pipeline'),
      },
      {
        id: 'rfps',
        label: t('nav.rfps'),
        href: '/rfps',
        icon: DocumentTextIcon,
        current: pathname.startsWith('/rfps'),
      },
      {
        id: 'proposals',
        label: t('nav.proposals'),
        href: '/proposals',
        icon: DocumentTextIcon,
        current: pathname.startsWith('/proposals'),
      },
    ],
    [pathname, t],
  )

  const resourcesNav: NavItem[] = useMemo(
    () => [
      {
        id: 'templates',
        label: t('nav.templates'),
        href: '/templates',
        icon: CogIcon,
        current: pathname.startsWith('/templates'),
      },
      {
        id: 'contract-templates',
        label: t('nav.contractTemplates'),
        href: '/contract-templates',
        icon: CogIcon,
        current: pathname.startsWith('/contract-templates'),
      },
      {
        id: 'content',
        label: t('nav.contentLibrary'),
        href: '/content',
        icon: UserGroupIcon,
        current: pathname === '/content',
      },
    ],
    [pathname, t],
  )

  const toolsNav: NavItem[] = useMemo(
    () => [
      {
        id: 'agents',
        label: t('nav.agents'),
        href: '/agents',
        icon: CpuChipIcon,
        current: pathname.startsWith('/agents'),
      },
      {
        id: 'finder',
        label: t('nav.rfpFinder'),
        href: '/finder',
        icon: FolderIcon,
        current: pathname === '/finder',
      },
      {
        id: 'linkedin-finder',
        label: t('nav.buyerProfiles'),
        href: '/linkedin-finder',
        icon: UserGroupIcon,
        current: pathname === '/linkedin-finder',
      },
      {
        id: 'googledrive',
        label: t('nav.googleDrive'),
        href: '/googledrive',
        icon: FolderIcon,
        current: pathname.startsWith('/googledrive'),
      },
      {
        id: 'canva',
        label: t('nav.canva'),
        href: '/integrations/canva',
        icon: CogIcon,
        current: pathname.startsWith('/integrations/canva'),
      },
    ],
    [pathname, t],
  )

  const accountNav: NavItem[] = useMemo(() => [], [pathname, t])

  const toolsHasCurrent = toolsNav.some((x) => x.current)
  const toolsVisible = toolsOpen || toolsHasCurrent

  const NavLink = ({ item }: { item: NavItem }) => (
    <Link
      key={item.id}
      href={item.href}
      // Avoid scale transforms here: they can overlap neighboring links and "steal" clicks.
      className={`group flex items-center px-3 py-3 text-sm font-medium rounded-xl transition-colors duration-200 ${
        item.current
          ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg'
          : 'text-gray-700 hover:text-gray-900 hover:bg-gray-100 hover:shadow-md'
      }`}
      onClick={() => setSidebarOpen(false)}
    >
      <item.icon
        className={`mr-4 flex-shrink-0 h-6 w-6 transition-colors ${
          item.current
            ? 'text-white'
            : 'text-gray-400 group-hover:text-gray-600'
        }`}
        aria-hidden="true"
      />
      <span className="font-medium">{item.label}</span>
      {item.current && (
        <div className="ml-auto w-2 h-2 bg-white rounded-full animate-pulse" />
      )}
    </Link>
  )

  const displayName = user?.display_name || user?.username || 'Guest'
  const toolsPanelId = 'sidebar-tools-panel'

  const SidebarFooter = () => (
    <div className="p-4 border-t border-gray-200">
      <div className="flex items-center justify-between p-3 bg-gradient-to-r from-gray-50 to-blue-50 rounded-xl">
        <div className="flex items-center gap-3 min-w-0">
          <UserCircleIcon
            className="h-8 w-8 text-gray-400"
            aria-hidden="true"
          />
          <div className="min-w-0">
            {user ? (
              <>
                <div className="text-sm font-medium text-gray-900 truncate">
                  {displayName}
                </div>
                <div className="text-xs text-gray-500 truncate">
                  {user.email || ''}
                </div>
              </>
            ) : (
              <>
                <div className="text-sm font-medium text-gray-900">
                  {t('header.guest')}
                </div>
                <Link href="/login" className="text-xs text-blue-600">
                  {t('header.signIn')}
                </Link>
              </>
            )}
          </div>
        </div>
        {user ? (
          <Menu as="div" className="relative">
            <MenuButton
              type="button"
              className="inline-flex items-center justify-center rounded-md p-2 text-gray-600 hover:bg-gray-100 hover:text-gray-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              aria-label={t('header.openUserMenu')}
            >
              <ChevronDownIcon className="h-5 w-5" aria-hidden="true" />
            </MenuButton>
            <Transition
              as={Fragment}
              enter="ease-out duration-150 motion-reduce:transition-none"
              enterFrom="opacity-0 translate-y-1"
              enterTo="opacity-100 translate-y-0"
              leave="ease-in duration-100 motion-reduce:transition-none"
              leaveFrom="opacity-100 translate-y-0"
              leaveTo="opacity-0 translate-y-1"
            >
              <MenuItems className="absolute right-0 bottom-full mb-2 w-48 bg-white border border-gray-200 rounded-lg shadow-xl z-50 focus:outline-none">
                <div className="py-1.5">
                  <MenuItem>
                    {({ active }) => (
                      <Link
                        href="/profile"
                        className={`w-full text-left px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors duration-150 flex items-center gap-2 rounded-md ${
                          active ? 'bg-gray-50 text-gray-900' : ''
                        }`}
                        onClick={() => setSidebarOpen(false)}
                      >
                        <UserCircleIcon
                          className="h-4 w-4"
                          aria-hidden="true"
                        />
                        {t('nav.profile')}
                      </Link>
                    )}
                  </MenuItem>
                  <MenuItem>
                    {({ active }) => (
                      <button
                        onClick={async () => {
                          await logout()
                          router.push('/login')
                        }}
                        className={`w-full text-left px-4 py-2.5 text-sm font-medium text-red-600 transition-colors duration-150 flex items-center gap-2 rounded-md ${
                          active ? 'bg-red-50 text-red-700' : ''
                        }`}
                        type="button"
                      >
                        {t('header.logout')}
                      </button>
                    )}
                  </MenuItem>
                </div>
              </MenuItems>
            </Transition>
          </Menu>
        ) : null}
      </div>
    </div>
  )

  const SidebarNav = () => (
    <div className="flex h-full flex-col">
      <nav className="mt-4 px-3 space-y-6 flex-1 overflow-y-auto pb-4">
        <div className="space-y-2">
          <div className="px-3 text-[11px] font-semibold tracking-wider text-gray-400 uppercase">
            {t('nav.primary')}
          </div>
          {primaryNav.map((item) => (
            <NavLink key={item.id} item={item} />
          ))}
        </div>

        <div className="space-y-2">
          <div className="px-3 text-[11px] font-semibold tracking-wider text-gray-400 uppercase">
            {t('nav.resources')}
          </div>
          {resourcesNav.map((item) => (
            <NavLink key={item.id} item={item} />
          ))}
        </div>

        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setToolsOpen((s) => !s)}
            className="w-full flex items-center justify-between px-3 py-2 text-[11px] font-semibold tracking-wider text-gray-400 uppercase hover:text-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 rounded-md"
            aria-expanded={toolsVisible}
            aria-controls={toolsPanelId}
          >
            <span>{t('nav.tools')}</span>
            {toolsVisible ? (
              <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
          {toolsVisible ? (
            <div id={toolsPanelId} className="space-y-2">
              {toolsNav.map((item) => (
                <NavLink key={item.id} item={item} />
              ))}
            </div>
          ) : null}
        </div>
      </nav>

      <SidebarFooter />
    </div>
  )

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      {/* Global top navigation bar (spans above sidebar + content) */}
      <header className="bg-white/80 backdrop-blur-sm shadow-sm border-b border-gray-200/50 sticky top-0 z-40">
        <div className="flex items-center justify-between h-16 px-4 sm:px-6 lg:px-8">
          <div className="flex items-center space-x-4 min-w-0">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              aria-label={t('header.openSidebar')}
              type="button"
            >
              <Bars3Icon className="h-6 w-6" aria-hidden="true" />
            </button>

            <Link
              href="/pipeline"
              className="font-bold text-gray-900 tracking-tight whitespace-nowrap"
            >
              {t('app.name')}
            </Link>

            <div className="hidden sm:block">
              <div className="relative">
                <GlobalSearch />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-4">
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
              <span>{t('header.api')}</span>
            </div>

            <button
              type="button"
              onClick={() => setSearchModalOpen(true)}
              className="sm:hidden p-2 rounded-xl text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              aria-label={t('search.open')}
            >
              <MagnifyingGlassIcon className="h-6 w-6" aria-hidden="true" />
            </button>

            <Menu as="div" className="relative">
              <MenuButton
                onClick={() => setNotificationsRequestedAt(Date.now())}
                className="p-2 rounded-xl text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-all duration-200 relative focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                aria-label={t('header.notifications')}
                type="button"
              >
                <BellIcon className="h-6 w-6" aria-hidden="true" />
              </MenuButton>
              <Transition
                as={Fragment}
                enter="ease-out duration-150 motion-reduce:transition-none"
                enterFrom="opacity-0 translate-y-1"
                enterTo="opacity-100 translate-y-0"
                leave="ease-in duration-100 motion-reduce:transition-none"
                leaveFrom="opacity-100 translate-y-0"
                leaveTo="opacity-0 translate-y-1"
              >
                <MenuItems className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-xl z-50 focus:outline-none">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <div className="text-sm font-semibold text-gray-900">
                      {t('header.notificationsTitle')}
                    </div>
                    <div className="text-xs text-gray-500">
                      {t('header.notificationsSubtitle')}
                    </div>
                  </div>
                  <div className="px-4 py-3 text-sm text-gray-700">
                    {notificationsLoading ? (
                      <div className="py-4 text-gray-600">
                        {t('header.notificationsLoading')}
                      </div>
                    ) : notificationItems.length === 0 ? (
                      <div className="py-4 text-gray-600">
                        {t('header.notificationsEmpty')}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {notificationItems.map((it) => (
                          <MenuItem key={it.id}>
                            {({ active }) => (
                              <button
                                type="button"
                                onClick={() => {
                                  const rfpId = it.id.split(':')[0]
                                  if (rfpId) router.push(`/rfps/${rfpId}`)
                                }}
                                className={`w-full text-left p-2 rounded-md ${
                                  active ? 'bg-gray-50' : ''
                                }`}
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
                                    aria-hidden="true"
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
                            )}
                          </MenuItem>
                        ))}
                      </div>
                    )}
                  </div>
                </MenuItems>
              </Transition>
            </Menu>
          </div>
        </div>
      </header>

      <Modal
        isOpen={searchModalOpen}
        onClose={() => setSearchModalOpen(false)}
        title={t('search.open')}
        size="md"
      >
        <GlobalSearch
          autoFocus
          containerClassName="w-full"
          inputClassName="w-full pl-4 pr-10 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-gray-50 transition-all duration-200"
          dropdownClassName="absolute mt-2 w-full max-h-96 overflow-auto rounded-xl border border-gray-200 bg-white shadow-lg z-40"
        />
      </Modal>

      {/* Mobile sidebar */}
      <Transition show={sidebarOpen} as={Fragment}>
        <Dialog
          as="div"
          className="relative z-50 lg:hidden"
          onClose={setSidebarOpen}
        >
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-200 motion-reduce:transition-none"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150 motion-reduce:transition-none"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-gray-600/75 top-16" />
          </Transition.Child>

          <div className="fixed inset-0 top-16 flex">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200 motion-reduce:transition-none"
              enterFrom="-translate-x-full"
              enterTo="translate-x-0"
              leave="ease-in duration-150 motion-reduce:transition-none"
              leaveFrom="translate-x-0"
              leaveTo="-translate-x-full"
            >
              <DialogPanel className="relative w-64 bg-white shadow-xl flex flex-col">
                <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
                  <DialogTitle className="sr-only">Navigation</DialogTitle>
                  <button
                    onClick={() => setSidebarOpen(false)}
                    className="p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                    aria-label={t('header.closeSidebar')}
                    type="button"
                  >
                    <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                  </button>
                </div>
                <SidebarNav />
              </DialogPanel>
            </Transition.Child>
          </div>
        </Dialog>
      </Transition>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:left-0 lg:top-16 lg:bottom-0 lg:z-30 lg:w-64 lg:bg-white lg:shadow-xl lg:block">
        <SidebarNav />
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Main content area */}
        <main className="min-h-screen">
          <div className="py-8">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <AuthRefreshStatus />
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
