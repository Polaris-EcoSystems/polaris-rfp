'use client'

import { useToast } from '@/components/ui/Toast'
import { integrationsApi } from '@/lib/api'
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface IntegrationStatus {
  status: 'green' | 'yellow' | 'red'
  statusMessage: string
  error?: string | null
}

interface GoogleDriveStatus extends IntegrationStatus {
  serviceAccount: {
    configured: boolean
    valid: boolean
    error: string | null
  }
  apiKey: {
    configured: boolean
    valid: boolean
    error: string | null
  }
  overallError: string | null
}

interface CanvaStatus extends IntegrationStatus {
  connected: boolean
  connection?: Record<string, any>
}

interface Activity {
  integration: 'canva' | 'googleDrive'
  type: string
  tool?: string
  createdAt: string
  payload?: Record<string, any>
}

export default function IntegrationsPage() {
  const toast = useToast()
  const [status, setStatus] = useState<{
    googleDrive?: GoogleDriveStatus
    canva?: CanvaStatus
  }>({})
  const [activities, setActivities] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)
  const [activitiesLoading, setActivitiesLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const resp = await integrationsApi.getStatus()
        if (cancelled) return
        setStatus(resp.data.integrations)
      } catch (e: any) {
        console.error('Failed to load integration status:', e)
        toast.error('Failed to load integration status')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [toast])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setActivitiesLoading(true)
      try {
        const resp = await integrationsApi.getActivities(5)
        if (cancelled) return
        setActivities(resp.data.activities)
      } catch (e: any) {
        console.error('Failed to load activities:', e)
        toast.error('Failed to load activities')
      } finally {
        if (!cancelled) setActivitiesLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [toast])

  const getStatusIcon = (status: 'green' | 'yellow' | 'red') => {
    switch (status) {
      case 'green':
        return <CheckCircleIcon className="h-6 w-6 text-green-500" />
      case 'yellow':
        return <ExclamationCircleIcon className="h-6 w-6 text-yellow-500" />
      case 'red':
        return <XCircleIcon className="h-6 w-6 text-red-500" />
    }
  }

  const getStatusColor = (status: 'green' | 'yellow' | 'red') => {
    switch (status) {
      case 'green':
        return 'bg-green-100 text-green-800 border-green-200'
      case 'yellow':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200'
      case 'red':
        return 'bg-red-100 text-red-800 border-red-200'
    }
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Integrations</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage and monitor third-party integrations
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Google Drive Integration */}
          <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900">
                  Google Drive
                </h2>
                {status.googleDrive && getStatusIcon(status.googleDrive.status)}
              </div>
            </div>
            <div className="p-6 space-y-4">
              {status.googleDrive ? (
                <>
                  <div>
                    <div
                      className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium border ${getStatusColor(
                        status.googleDrive.status,
                      )}`}
                    >
                      {status.googleDrive.statusMessage}
                    </div>
                  </div>

                  {/* Service Account Status */}
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium text-gray-700">
                      Service Account Credentials
                    </h3>
                    <div className="space-y-1 text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-600">Configured:</span>
                        <span
                          className={
                            status.googleDrive.serviceAccount.configured
                              ? 'text-green-600 font-medium'
                              : 'text-gray-400'
                          }
                        >
                          {status.googleDrive.serviceAccount.configured
                            ? 'Yes'
                            : 'No'}
                        </span>
                      </div>
                      {status.googleDrive.serviceAccount.configured && (
                        <div className="flex items-center gap-2">
                          <span className="text-gray-600">Valid:</span>
                          <span
                            className={
                              status.googleDrive.serviceAccount.valid
                                ? 'text-green-600 font-medium'
                                : 'text-red-600 font-medium'
                            }
                          >
                            {status.googleDrive.serviceAccount.valid
                              ? 'Yes'
                              : 'No'}
                          </span>
                        </div>
                      )}
                      {status.googleDrive.serviceAccount.error && (
                        <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs font-mono text-red-700 break-all">
                          {status.googleDrive.serviceAccount.error}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* API Key Status */}
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium text-gray-700">
                      API Key Credentials
                    </h3>
                    <div className="space-y-1 text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-600">Configured:</span>
                        <span
                          className={
                            status.googleDrive.apiKey.configured
                              ? 'text-green-600 font-medium'
                              : 'text-gray-400'
                          }
                        >
                          {status.googleDrive.apiKey.configured ? 'Yes' : 'No'}
                        </span>
                      </div>
                      {status.googleDrive.apiKey.configured && (
                        <div className="flex items-center gap-2">
                          <span className="text-gray-600">Valid:</span>
                          <span
                            className={
                              status.googleDrive.apiKey.valid
                                ? 'text-green-600 font-medium'
                                : 'text-red-600 font-medium'
                            }
                          >
                            {status.googleDrive.apiKey.valid ? 'Yes' : 'No'}
                          </span>
                        </div>
                      )}
                      {status.googleDrive.apiKey.error && (
                        <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs font-mono text-red-700 break-all">
                          {status.googleDrive.apiKey.error}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Overall Error */}
                  {status.googleDrive.overallError && (
                    <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded">
                      <h4 className="text-sm font-medium text-red-900 mb-1">
                        Overall Error
                      </h4>
                      <p className="text-xs font-mono text-red-700 break-all">
                        {status.googleDrive.overallError}
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-gray-500">
                  Failed to load Google Drive status
                </p>
              )}
            </div>
          </div>

          {/* Canva Integration */}
          <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900">Canva</h2>
                {status.canva && getStatusIcon(status.canva.status)}
              </div>
            </div>
            <div className="p-6 space-y-4">
              {status.canva ? (
                <>
                  <div>
                    <div
                      className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium border ${getStatusColor(
                        status.canva.status,
                      )}`}
                    >
                      {status.canva.statusMessage}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-gray-600">Connected:</span>
                      <span
                        className={
                          status.canva.connected
                            ? 'text-green-600 font-medium'
                            : 'text-gray-400'
                        }
                      >
                        {status.canva.connected ? 'Yes' : 'No'}
                      </span>
                    </div>
                  </div>

                  {status.canva.error && (
                    <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded">
                      <h4 className="text-sm font-medium text-red-900 mb-1">
                        Error
                      </h4>
                      <p className="text-xs font-mono text-red-700 break-all">
                        {status.canva.error}
                      </p>
                    </div>
                  )}

                  {status.canva.connection && (
                    <div className="mt-4 space-y-1 text-xs text-gray-600">
                      {status.canva.connection.scopes && (
                        <div>
                          <span className="font-medium">Scopes:</span>{' '}
                          {Array.isArray(status.canva.connection.scopes)
                            ? status.canva.connection.scopes.join(', ')
                            : 'N/A'}
                        </div>
                      )}
                      {status.canva.connection.expiresAt && (
                        <div>
                          <span className="font-medium">Expires:</span>{' '}
                          {new Date(
                            status.canva.connection.expiresAt,
                          ).toLocaleString()}
                        </div>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-gray-500">
                  Failed to load Canva status
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Recent Activities */}
      <div className="mt-8 rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">
            Recent Activities
          </h2>
        </div>
        <div className="p-6">
          {activitiesLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            </div>
          ) : activities.length > 0 ? (
            <div className="space-y-4">
              {activities.map((activity, idx) => (
                <div
                  key={idx}
                  className="border-b border-gray-100 last:border-0 pb-4 last:pb-0"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900 capitalize">
                          {activity.integration}
                        </span>
                        <span className="text-xs text-gray-500">
                          {activity.type}
                        </span>
                        {activity.tool && (
                          <span className="text-xs text-gray-400 font-mono">
                            {activity.tool}
                          </span>
                        )}
                      </div>
                      {activity.payload &&
                        typeof activity.payload === 'object' && (
                          <pre className="mt-2 text-xs text-gray-600 bg-gray-50 p-2 rounded overflow-auto max-h-32">
                            {JSON.stringify(activity.payload, null, 2)}
                          </pre>
                        )}
                    </div>
                    <div className="ml-4 text-xs text-gray-500">
                      {new Date(activity.createdAt).toLocaleString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500 text-center py-8">
              No recent activities
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
