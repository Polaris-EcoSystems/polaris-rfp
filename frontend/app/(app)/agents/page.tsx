'use client'

import { useToast } from '@/components/ui/Toast'
import { AgentJob, agentsApi } from '@/lib/api'
import {
  ClockIcon,
  CpuChipIcon,
  FolderIcon,
  PencilIcon,
  PlusIcon,
  ServerIcon,
  TrashIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

type PageTab = 'overview' | 'jobs' | 'activity' | 'metrics'

export default function AgentsPage() {
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<PageTab>('overview')

  // Infrastructure state
  const [infrastructure, setInfrastructure] = useState<any>(null)
  const [infrastructureLoading, setInfrastructureLoading] = useState(false)

  // Jobs state
  const [jobs, setJobs] = useState<AgentJob[]>([])
  const [jobsLoading, setJobsLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [selectedJob, setSelectedJob] = useState<AgentJob | null>(null)
  const [showJobModal, setShowJobModal] = useState(false)
  const [isEditingJob, setIsEditingJob] = useState(false)

  // Activity state
  const [activity, setActivity] = useState<any>(null)
  const [activityLoading, setActivityLoading] = useState(false)
  const [activityHours, setActivityHours] = useState(24)

  // Metrics state
  const [metrics, setMetrics] = useState<any>(null)
  const [metricsLoading, setMetricsLoading] = useState(false)
  const [metricsHours, setMetricsHours] = useState(24)

  // Workers state
  const [workers, setWorkers] = useState<any>(null)

  // Load infrastructure info
  useEffect(() => {
    if (activeTab !== 'overview' && infrastructure) return

    let cancelled = false
    ;(async () => {
      setInfrastructureLoading(true)
      try {
        const resp = await agentsApi.getInfrastructure()
        if (cancelled) return
        setInfrastructure(resp.data)
      } catch (e) {
        console.error('Failed to load infrastructure:', e)
        toast.error('Failed to load infrastructure information')
      } finally {
        if (!cancelled) setInfrastructureLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [activeTab, infrastructure, toast])

  // Load workers
  useEffect(() => {
    if (activeTab !== 'overview' && workers) return

    let cancelled = false
    ;(async () => {
      try {
        const resp = await agentsApi.getWorkers()
        if (cancelled) return
        setWorkers(resp.data)
      } catch (e) {
        console.error('Failed to load workers:', e)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [activeTab, workers])

  // Load jobs
  useEffect(() => {
    if (activeTab !== 'jobs') return

    let cancelled = false
    ;(async () => {
      setJobsLoading(true)
      try {
        const resp = await agentsApi.listJobs({
          limit: 100,
          status: statusFilter || undefined,
        })
        if (cancelled) return
        setJobs(resp.data.jobs)
      } catch (e) {
        console.error('Failed to load jobs:', e)
        toast.error('Failed to load jobs')
      } finally {
        if (!cancelled) setJobsLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [activeTab, statusFilter, toast])

  // Load activity
  useEffect(() => {
    if (activeTab !== 'activity') return

    let cancelled = false
    ;(async () => {
      setActivityLoading(true)
      try {
        const resp = await agentsApi.getActivity({
          hours: activityHours,
          limit: 100,
        })
        if (cancelled) return
        setActivity(resp.data)
      } catch (e) {
        console.error('Failed to load activity:', e)
        toast.error('Failed to load activity')
      } finally {
        if (!cancelled) setActivityLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [activeTab, activityHours, toast])

  // Load metrics
  useEffect(() => {
    if (activeTab !== 'metrics') return

    let cancelled = false
    ;(async () => {
      setMetricsLoading(true)
      try {
        const resp = await agentsApi.getMetrics({
          hours: metricsHours,
        })
        if (cancelled) return
        setMetrics(resp.data)
      } catch (e) {
        console.error('Failed to load metrics:', e)
        toast.error('Failed to load metrics')
      } finally {
        if (!cancelled) setMetricsLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [activeTab, metricsHours, toast])

  const handleCreateJob = () => {
    setSelectedJob(null)
    setIsEditingJob(false)
    setShowJobModal(true)
  }

  const handleEditJob = (job: AgentJob) => {
    setSelectedJob(job)
    setIsEditingJob(true)
    setShowJobModal(true)
  }

  const handleDeleteJob = async (jobId: string) => {
    if (!confirm('Are you sure you want to delete this job?')) return

    try {
      await agentsApi.deleteJob(jobId)
      toast.success('Job deleted successfully')
      // Reload jobs
      const resp = await agentsApi.listJobs({
        limit: 100,
        status: statusFilter || undefined,
      })
      setJobs(resp.data.jobs)
    } catch (e: any) {
      console.error('Failed to delete job:', e)
      toast.error(e?.response?.data?.detail || 'Failed to delete job')
    }
  }

  const handleCancelJob = async (jobId: string) => {
    if (!confirm('Are you sure you want to cancel this job?')) return

    try {
      await agentsApi.cancelJob(jobId)
      toast.success('Job cancelled successfully')
      // Reload jobs
      const resp = await agentsApi.listJobs({
        limit: 100,
        status: statusFilter || undefined,
      })
      setJobs(resp.data.jobs)
    } catch (e: any) {
      console.error('Failed to cancel job:', e)
      toast.error(e?.response?.data?.detail || 'Failed to cancel job')
    }
  }

  const handleSaveJob = async (jobData: {
    jobType: string
    scope: Record<string, any>
    dueAt: string
    payload?: Record<string, any>
    dependsOn?: string[]
  }) => {
    try {
      if (isEditingJob && selectedJob) {
        await agentsApi.updateJob(selectedJob.jobId, jobData)
        toast.success('Job updated successfully')
      } else {
        await agentsApi.createJob(jobData)
        toast.success('Job created successfully')
      }
      setShowJobModal(false)
      // Reload jobs
      const resp = await agentsApi.listJobs({
        limit: 100,
        status: statusFilter || undefined,
      })
      setJobs(resp.data.jobs)
    } catch (e: any) {
      console.error('Failed to save job:', e)
      toast.error(e?.response?.data?.detail || 'Failed to save job')
    }
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'queued':
        return 'bg-yellow-100 text-yellow-800'
      case 'running':
        return 'bg-blue-100 text-blue-800'
      case 'checkpointed':
        return 'bg-purple-100 text-purple-800'
      case 'completed':
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'cancelled':
        return 'bg-gray-100 text-gray-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Agents</h1>
        <p className="mt-1 text-sm text-gray-500">
          Monitor and manage agent infrastructure, jobs, and activity
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('overview')}
            className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
              activeTab === 'overview'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            type="button"
          >
            <ServerIcon className="h-5 w-5 inline mr-2" />
            Overview
          </button>
          <button
            onClick={() => setActiveTab('jobs')}
            className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
              activeTab === 'jobs'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            type="button"
          >
            <FolderIcon className="h-5 w-5 inline mr-2" />
            Jobs
          </button>
          <button
            onClick={() => setActiveTab('activity')}
            className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
              activeTab === 'activity'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            type="button"
          >
            <ClockIcon className="h-5 w-5 inline mr-2" />
            Activity
          </button>
          <button
            onClick={() => setActiveTab('metrics')}
            className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
              activeTab === 'metrics'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            type="button"
          >
            <CpuChipIcon className="h-5 w-5 inline mr-2" />
            Metrics
          </button>
        </nav>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="mt-6 space-y-6">
          {/* Infrastructure Info */}
          <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Infrastructure
              </h2>
            </div>
            <div className="p-6">
              {infrastructureLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
                </div>
              ) : infrastructure ? (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-gray-700">
                      Base Agent Class
                    </h3>
                    <p className="mt-1 text-sm text-gray-500 font-mono">
                      {infrastructure.infrastructure?.baseAgentClass}
                    </p>
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-gray-700">
                      Memory System
                    </h3>
                    <p className="mt-1 text-sm text-gray-500">
                      {infrastructure.infrastructure?.memory?.type}
                    </p>
                    <p className="mt-1 text-xs text-gray-400 font-mono">
                      {infrastructure.infrastructure?.memory?.tableName}
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-500">
                  Failed to load infrastructure
                </p>
              )}
            </div>
          </div>

          {/* Workers */}
          <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Workers</h2>
            </div>
            <div className="p-6">
              {workers ? (
                <div className="space-y-4">
                  {workers.workers?.map((worker: any, idx: number) => (
                    <div
                      key={idx}
                      className="border-b border-gray-100 last:border-0 pb-4 last:pb-0"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-sm font-semibold text-gray-900">
                            {worker.name}
                          </h3>
                          <p className="mt-1 text-sm text-gray-600">
                            {worker.description}
                          </p>
                          <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
                            <span className="font-mono">{worker.schedule}</span>
                            {worker.resources && (
                              <span>
                                {worker.resources.cpu} CPU /{' '}
                                {worker.resources.memory} MB
                              </span>
                            )}
                          </div>
                          {worker.logGroup && (
                            <p className="mt-1 text-xs text-gray-400 font-mono">
                              {worker.logGroup}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                  {workers.note && (
                    <p className="mt-4 text-xs text-gray-500 italic">
                      {workers.note}
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-sm text-gray-500">Loading workers...</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Jobs Tab */}
      {activeTab === 'jobs' && (
        <div className="mt-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
              >
                <option value="">All Statuses</option>
                <option value="queued">Queued</option>
                <option value="running">Running</option>
                <option value="checkpointed">Checkpointed</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
            <button
              onClick={handleCreateJob}
              className="inline-flex items-center gap-2 rounded-md bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
            >
              <PlusIcon className="h-5 w-5" />
              Create Job
            </button>
          </div>

          {jobsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Job ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Type
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Due At
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Scope
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {jobs.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-6 py-8 text-center text-sm text-gray-500"
                      >
                        No jobs found
                      </td>
                    </tr>
                  ) : (
                    jobs.map((job) => (
                      <tr key={job.jobId} className="hover:bg-gray-50">
                        <td className="whitespace-nowrap px-6 py-4 text-sm font-mono text-gray-900">
                          {job.jobId}
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">
                          {job.jobType}
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          <span
                            className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${getStatusColor(
                              job.status,
                            )}`}
                          >
                            {job.status}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                          {new Date(job.dueAt).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-500">
                          {job.scope?.rfpId ? (
                            <span className="font-mono">
                              RFP: {job.scope.rfpId}
                            </span>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium">
                          <div className="flex items-center justify-end gap-2">
                            {(job.status === 'queued' ||
                              job.status === 'checkpointed') && (
                              <>
                                <button
                                  onClick={() => handleEditJob(job)}
                                  className="text-primary-600 hover:text-primary-900"
                                  title="Edit"
                                >
                                  <PencilIcon className="h-5 w-5" />
                                </button>
                                <button
                                  onClick={() => handleCancelJob(job.jobId)}
                                  className="text-yellow-600 hover:text-yellow-900"
                                  title="Cancel"
                                >
                                  <XCircleIcon className="h-5 w-5" />
                                </button>
                              </>
                            )}
                            {(job.status === 'cancelled' ||
                              job.status === 'completed' ||
                              job.status === 'failed') && (
                              <button
                                onClick={() => handleDeleteJob(job.jobId)}
                                className="text-red-600 hover:text-red-900"
                                title="Delete"
                              >
                                <TrashIcon className="h-5 w-5" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Activity Tab */}
      {activeTab === 'activity' && (
        <div className="mt-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700">
                Hours:
              </label>
              <select
                value={activityHours}
                onChange={(e) => setActivityHours(Number(e.target.value))}
                className="rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
              >
                <option value={1}>1 hour</option>
                <option value={6}>6 hours</option>
                <option value={24}>24 hours</option>
                <option value={72}>72 hours</option>
              </select>
            </div>
          </div>

          {activityLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
            </div>
          ) : activity ? (
            <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
              <div className="px-6 py-4 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-gray-900">
                    Recent Activity
                  </h2>
                  <span className="text-sm text-gray-500">
                    {activity.count} events since{' '}
                    {new Date(activity.since).toLocaleString()}
                  </span>
                </div>
              </div>
              <div className="divide-y divide-gray-200">
                {activity.events && activity.events.length > 0 ? (
                  activity.events
                    .slice(0, 100)
                    .map((event: any, idx: number) => (
                      <div key={idx} className="px-6 py-4">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-gray-900">
                                {event.type || 'event'}
                              </span>
                              {event.tool && (
                                <span className="text-xs text-gray-500 font-mono">
                                  {event.tool}
                                </span>
                              )}
                            </div>
                            {event.rfpId && (
                              <p className="mt-1 text-xs text-gray-500">
                                RFP:{' '}
                                <span className="font-mono">{event.rfpId}</span>
                              </p>
                            )}
                            {event.payload &&
                              typeof event.payload === 'object' && (
                                <pre className="mt-2 text-xs text-gray-600 bg-gray-50 p-2 rounded overflow-auto max-h-32">
                                  {JSON.stringify(event.payload, null, 2)}
                                </pre>
                              )}
                          </div>
                          <div className="ml-4 text-xs text-gray-500">
                            {event.createdAt
                              ? new Date(event.createdAt).toLocaleString()
                              : '—'}
                          </div>
                        </div>
                      </div>
                    ))
                ) : (
                  <div className="px-6 py-8 text-center text-sm text-gray-500">
                    No activity found
                  </div>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Failed to load activity</p>
          )}
        </div>
      )}

      {/* Metrics Tab */}
      {activeTab === 'metrics' && (
        <div className="mt-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700">
                Hours:
              </label>
              <select
                value={metricsHours}
                onChange={(e) => setMetricsHours(Number(e.target.value))}
                className="rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
              >
                <option value={1}>1 hour</option>
                <option value={6}>6 hours</option>
                <option value={24}>24 hours</option>
                <option value={168}>1 week</option>
              </select>
            </div>
          </div>

          {metricsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
            </div>
          ) : metrics ? (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-medium text-gray-500">
                  Total Operations
                </h3>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  {metrics.metrics?.count || 0}
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-medium text-gray-500">
                  Avg Duration
                </h3>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  {metrics.metrics?.avg_duration_ms
                    ? `${Math.round(metrics.metrics.avg_duration_ms)}ms`
                    : '0ms'}
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-medium text-gray-500">Avg Steps</h3>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  {metrics.metrics?.avg_steps || 0}
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-medium text-gray-500">
                  Success Rate
                </h3>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  {metrics.metrics?.success_rate
                    ? `${Math.round(metrics.metrics.success_rate * 100)}%`
                    : '0%'}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Failed to load metrics</p>
          )}
        </div>
      )}

      {/* Job Modal - Simplified for now, can be enhanced */}
      {showJobModal && (
        <JobModal
          job={selectedJob}
          isEditing={isEditingJob}
          onSave={handleSaveJob}
          onClose={() => setShowJobModal(false)}
        />
      )}
    </div>
  )
}

// Simple Job Modal Component
function JobModal({
  job,
  isEditing,
  onSave,
  onClose,
}: {
  job: AgentJob | null
  isEditing: boolean
  onSave: (data: {
    jobType: string
    scope: Record<string, any>
    dueAt: string
    payload?: Record<string, any>
    dependsOn?: string[]
  }) => void
  onClose: () => void
}) {
  const [jobType, setJobType] = useState(job?.jobType || '')
  const [scopeRfpId, setScopeRfpId] = useState(job?.scope?.rfpId || '')
  const [dueAt, setDueAt] = useState(
    job?.dueAt
      ? new Date(job.dueAt).toISOString().slice(0, 16)
      : new Date(Date.now() + 3600000).toISOString().slice(0, 16),
  )
  const [payloadJson, setPayloadJson] = useState(
    job?.payload ? JSON.stringify(job.payload, null, 2) : '{}',
  )

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    let payload: Record<string, any> = {}
    try {
      payload = JSON.parse(payloadJson || '{}')
    } catch {
      alert('Invalid JSON in payload')
      return
    }

    onSave({
      jobType,
      scope: scopeRfpId ? { rfpId: scopeRfpId } : {},
      dueAt: new Date(dueAt).toISOString(),
      payload: Object.keys(payload).length > 0 ? payload : undefined,
    })
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        />
        <div className="relative w-full max-w-2xl rounded-lg bg-white shadow-xl">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900">
              {isEditing ? 'Edit Job' : 'Create Job'}
            </h2>
          </div>
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Job Type
              </label>
              <input
                type="text"
                value={jobType}
                onChange={(e) => setJobType(e.target.value)}
                required
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                RFP ID (Scope)
              </label>
              <input
                type="text"
                value={scopeRfpId}
                onChange={(e) => setScopeRfpId(e.target.value)}
                placeholder="Optional"
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Due At
              </label>
              <input
                type="datetime-local"
                value={dueAt}
                onChange={(e) => setDueAt(e.target.value)}
                required
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Payload (JSON)
              </label>
              <textarea
                value={payloadJson}
                onChange={(e) => setPayloadJson(e.target.value)}
                rows={8}
                className="mt-1 block w-full rounded-md border-gray-300 font-mono text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
              />
            </div>
            <div className="flex items-center justify-end gap-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700"
              >
                {isEditing ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
