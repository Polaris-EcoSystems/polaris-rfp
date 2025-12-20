'use client'

import { useEffect, useMemo, useState } from 'react'
import Button from '@/components/ui/Button'
import Card, {
  CardBody,
  CardFooter,
  CardHeader,
} from '@/components/ui/Card'
import { useToast } from '@/components/ui/Toast'
import {
  CognitoProfileAttribute,
  CognitoProfileResponse,
  profileApi,
} from '@/lib/api'

type UserSession = {
  sid: string
  sessionKind: string
  createdAt: number
  lastSeenAt: number
  ipPrefix?: string | null
  userAgent?: string | null
  isCurrent?: boolean
}

function toAttrMap(attrs: CognitoProfileAttribute[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const a of attrs || []) out[a.name] = a.value ?? ''
  return out
}

export default function ProfilePage() {
  const toast = useToast()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [profile, setProfile] = useState<CognitoProfileResponse | null>(null)
  const [sessions, setSessions] = useState<UserSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)

  const [values, setValues] = useState<Record<string, string>>({})
  const originalValues = useMemo(
    () => (profile ? toAttrMap(profile.attributes) : {}),
    [profile],
  )

  const mutableAttributes = useMemo(
    () => (profile?.attributes || []).filter((a) => a.mutable),
    [profile],
  )
  const readOnlyAttributes = useMemo(
    () => (profile?.attributes || []).filter((a) => !a.mutable),
    [profile],
  )

  useEffect(() => {
    let mounted = true
    const load = async () => {
      try {
        setLoading(true)
        const resp = await profileApi.get()
        if (!mounted) return
        setProfile(resp.data)
        setValues(toAttrMap(resp.data.attributes))
      } catch (_e) {
        toast.error('Failed to load profile')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [toast])

  const loadSessions = async () => {
    try {
      setSessionsLoading(true)
      const resp = await fetch('/api/session/sessions', { cache: 'no-store' })
      if (!resp.ok) throw new Error('failed')
      const data = (await resp.json().catch(() => ({ data: [] }))) as any
      setSessions(Array.isArray(data?.data) ? data.data : [])
    } catch {
      toast.error('Failed to load sessions')
    } finally {
      setSessionsLoading(false)
    }
  }

  useEffect(() => {
    void loadSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const revokeSession = async (sid: string) => {
    try {
      const resp = await fetch('/api/session/sessions/revoke', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ sid }),
      })
      if (!resp.ok) throw new Error('failed')
      toast.success('Session revoked')
      await loadSessions()
    } catch {
      toast.error('Failed to revoke session')
    }
  }

  const revokeAllOtherSessions = async () => {
    try {
      const resp = await fetch('/api/session/sessions/revoke-all', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ mode: 'others' }),
      })
      if (!resp.ok) throw new Error('failed')
      toast.success('Other sessions revoked')
      await loadSessions()
    } catch {
      toast.error('Failed to revoke other sessions')
    }
  }

  const revokeAllSessions = async () => {
    try {
      const resp = await fetch('/api/session/sessions/revoke-all', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ mode: 'all' }),
      })
      if (!resp.ok) throw new Error('failed')
      toast.success('Signed out everywhere')
      // Server will clear cookies; page will redirect on next request.
      window.location.href = '/login'
    } catch {
      toast.error('Failed to sign out everywhere')
    }
  }

  const hasChanges = useMemo(() => {
    if (!profile) return false
    for (const a of mutableAttributes) {
      const cur = values[a.name] ?? ''
      const orig = originalValues[a.name] ?? ''
      if (cur !== orig) return true
    }
    return false
  }, [mutableAttributes, originalValues, profile, values])

  const reset = () => {
    if (!profile) return
    setValues(toAttrMap(profile.attributes))
    toast.info('Changes reset')
  }

  const save = async () => {
    if (!profile) return
    try {
      setSaving(true)

      const updates: { name: string; value: string | null }[] = []
      for (const a of mutableAttributes) {
        const cur = values[a.name] ?? ''
        const orig = originalValues[a.name] ?? ''
        if (cur === orig) continue

        // Treat empty string as delete for non-required attributes.
        if (cur.trim() === '' && !a.required) {
          updates.push({ name: a.name, value: null })
        } else {
          updates.push({ name: a.name, value: cur })
        }
      }

      if (updates.length === 0) {
        toast.info('No changes to save')
        return
      }

      const resp = await profileApi.updateAttributes(updates)
      setProfile(resp.data)
      setValues(toAttrMap(resp.data.attributes))
      toast.success('Profile updated')
    } catch (_e) {
      toast.error('Failed to save profile changes')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="text-sm text-gray-600">Loading profile…</div>
  }

  if (!profile) {
    return <div className="text-sm text-gray-600">Profile unavailable.</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">User Profile</h1>
        <p className="text-sm text-gray-600">
          View and edit your Cognito user attributes.
        </p>
      </div>

      <Card gradient>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-900">
            Signed-in user
          </div>
          <div className="text-xs text-gray-600">
            These are derived from your JWT and Cognito user record.
          </div>
        </CardHeader>
        <CardBody>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-xs font-medium text-gray-500">Username</dt>
              <dd className="font-medium text-gray-900">
                {profile.user.username}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-gray-500">Email</dt>
              <dd className="font-medium text-gray-900">
                {profile.user.email || '—'}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium text-gray-500">Sub</dt>
              <dd className="font-mono text-xs text-gray-800 break-all">
                {profile.user.sub}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs font-medium text-gray-500">
                Cognito username
              </dt>
              <dd className="font-mono text-xs text-gray-800 break-all">
                {profile.user.cognito_username}
              </dd>
            </div>
          </dl>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-gray-900">
                Editable attributes
              </div>
              <div className="text-xs text-gray-600">
                Only attributes marked mutable by the Cognito user pool schema
                can be updated here.
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={!hasChanges || saving}
                onClick={reset}
              >
                Reset
              </Button>
              <Button
                variant="primary"
                size="sm"
                gradient
                loading={saving}
                disabled={!hasChanges || saving}
                onClick={save}
              >
                Save changes
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardBody>
          {mutableAttributes.length === 0 ? (
            <div className="text-sm text-gray-600">
              No editable attributes available.
            </div>
          ) : (
            <div className="space-y-4">
              {mutableAttributes.map((a) => (
                <div
                  key={a.name}
                  className="grid grid-cols-1 sm:grid-cols-3 gap-3"
                >
                  <div className="sm:col-span-1">
                    <div className="text-xs font-medium text-gray-700">
                      {a.name}
                    </div>
                    <div className="text-[11px] text-gray-500">
                      {a.required ? 'Required' : 'Optional'}
                    </div>
                  </div>
                  <div className="sm:col-span-2">
                    <input
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={values[a.name] ?? ''}
                      onChange={(e) =>
                        setValues((prev) => ({
                          ...prev,
                          [a.name]: e.target.value,
                        }))
                      }
                      placeholder={
                        a.required ? 'Required' : 'Leave blank to clear'
                      }
                    />
                    <div className="mt-1 text-[11px] text-gray-500">
                      Current:{' '}
                      <span className="font-mono">
                        {(originalValues[a.name] ?? '') || '—'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>

        <CardFooter>
          <div className="text-xs text-gray-600">
            Tip: for optional attributes, setting the value to empty will delete
            the attribute in Cognito.
          </div>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-gray-900">
                Active sessions
              </div>
              <div className="text-xs text-gray-600">
                Manage signed-in devices (max 5 sessions).
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={sessionsLoading}
                onClick={loadSessions}
              >
                Refresh
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={sessionsLoading || sessions.length === 0}
                onClick={revokeAllOtherSessions}
              >
                Revoke others
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={sessionsLoading || sessions.length === 0}
                onClick={revokeAllSessions}
              >
                Sign out everywhere
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardBody>
          {sessionsLoading ? (
            <div className="text-sm text-gray-600">Loading sessions…</div>
          ) : sessions.length === 0 ? (
            <div className="text-sm text-gray-600">No sessions found.</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {sessions.map((s) => (
                <div
                  key={s.sid}
                  className="py-3 flex items-start justify-between gap-4"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-900 flex items-center gap-2">
                      <span>
                        {s.sessionKind === 'remember' ? 'Remembered' : 'Normal'}
                      </span>
                      {s.isCurrent ? (
                        <span className="text-xs text-gray-600">(This device)</span>
                      ) : null}
                    </div>
                    <div className="mt-1 text-xs text-gray-600 space-y-0.5">
                      <div>
                        Last seen:{' '}
                        {s.lastSeenAt
                          ? new Date(s.lastSeenAt * 1000).toLocaleString()
                          : '—'}
                      </div>
                      <div>
                        Created:{' '}
                        {s.createdAt
                          ? new Date(s.createdAt * 1000).toLocaleString()
                          : '—'}
                      </div>
                      {s.ipPrefix ? <div>IP: {s.ipPrefix}</div> : null}
                      {s.userAgent ? (
                        <div className="truncate">UA: {s.userAgent}</div>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={sessionsLoading}
                      onClick={() => revokeSession(s.sid)}
                    >
                      Revoke
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-900">
            Read-only attributes
          </div>
          <div className="text-xs text-gray-600">
            These are present on your user record but are not mutable in the
            pool schema.
          </div>
        </CardHeader>
        <CardBody>
          {readOnlyAttributes.length === 0 ? (
            <div className="text-sm text-gray-600">None</div>
          ) : (
            <div className="divide-y divide-gray-100">
              {readOnlyAttributes.map((a) => (
                <div
                  key={a.name}
                  className="py-2 flex items-start justify-between gap-4"
                >
                  <div className="text-sm text-gray-700">{a.name}</div>
                  <div className="text-xs font-mono text-gray-800 break-all text-right">
                    {a.value || '—'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-900">
            Token claims
          </div>
          <div className="text-xs text-gray-600">
            Raw decoded JWT claims (read-only).
          </div>
        </CardHeader>
        <CardBody>
          <pre className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-auto">
            {JSON.stringify(profile.claims || {}, null, 2)}
          </pre>
        </CardBody>
      </Card>
    </div>
  )
}



