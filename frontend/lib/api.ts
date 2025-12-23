import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'

/**
 * Frontend API strategy:
 * - Browser calls same-origin Next.js routes (BFF) under `/api/**`
 * - Next route handlers proxy to the FastAPI backend and attach Authorization
 *   from an httpOnly cookie (set during magic-link verification).
 */
export function proxyUrl(path: string): string {
  const raw = String(path ?? '').trim()
  if (!raw) return '/api/proxy/'

  // Idempotent: if a caller already passed a proxied path, keep it.
  if (raw.startsWith('/api/proxy')) return raw
  if (raw.startsWith('api/proxy')) return `/${raw}`

  // Convenience: allow passing a full URL and proxy its pathname+search.
  if (raw.startsWith('http://') || raw.startsWith('https://')) {
    try {
      const u = new URL(raw)
      return proxyUrl(`${u.pathname}${u.search}`)
    } catch {
      // fall through
    }
  }

  return `/api/proxy${raw.startsWith('/') ? raw : `/${raw}`}`
}

export function cleanPathToken(token: string): string {
  // Defensive: trim whitespace and strip leading/trailing slashes
  // (avoids accidental `/api/rfp/<id>/` 404s and double-segment bugs).
  const t = String(token ?? '')
    .trim()
    .replace(/^\/+/, '')
    .replace(/\/+$/, '')
  return encodeURIComponent(t)
}

// Ensure we only ever have ONE axios instance, even if the module is imported via
// different path aliases (e.g. "@/lib/api" vs "../lib/api") in different bundles.
const _g = globalThis as typeof globalThis & {
  __polaris_api_client?: AxiosInstance
}
const api: AxiosInstance =
  _g.__polaris_api_client ??
  axios.create({
    // Same-origin; calls should use `proxyUrl()` (or other local API routes).
    baseURL: '',
    timeout: 300000, // 5 minute timeout for PDF generation
  })
_g.__polaris_api_client = api

// Add request interceptor for light normalization
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    return config
  },
  (error: AxiosError | any) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  },
)

// Add response interceptor for debugging
api.interceptors.response.use(
  (response: AxiosResponse) => {
    // If server indicates auth refresh recovered, emit global UX signals.
    try {
      const hdr =
        (response.headers &&
          ((response.headers as any)['x-polaris-auth-refresh'] ||
            (response.headers as any)['X-Polaris-Auth-Refresh'])) ||
        null
      if (String(hdr || '').toLowerCase() === 'recovered') {
        const g = globalThis as typeof globalThis & {
          __polaris_auth_refresh_degraded_since?: number | null
        }
        g.__polaris_auth_refresh_degraded_since = null
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('polaris:auth-refresh-recovered'))
        }
      }
    } catch {
      // ignore
    }
    return response
  },
  async (error: AxiosError | any) => {
    const requestId = (() => {
      try {
        const hdr =
          error?.response?.headers?.['x-request-id'] ||
          error?.response?.headers?.['X-Request-Id']
        if (typeof hdr === 'string' && hdr.trim()) return hdr.trim()
        const bodyRid = error?.response?.data?.requestId
        if (typeof bodyRid === 'string' && bodyRid.trim()) return bodyRid.trim()
      } catch {
        // ignore
      }
      return null
    })()

    console.error('Response error:', {
      url: error.config?.url,
      status: error.response?.status,
      data: error.response?.data,
      requestId,
      message: error.message,
    })

    // Surface a correlation id for support when we hit server-side errors.
    try {
      const status = error.response?.status
      if (
        typeof window !== 'undefined' &&
        requestId &&
        typeof status === 'number' &&
        status >= 500
      ) {
        window.dispatchEvent(
          new CustomEvent('polaris:requestId', { detail: { requestId } }),
        )
      }
    } catch {
      // ignore
    }

    // If server indicates auth refresh is temporarily unavailable/recovered, emit global UX signals.
    try {
      const status = error.response?.status
      const hdr =
        (error.response?.headers &&
          (error.response.headers['x-polaris-auth-refresh'] ||
            error.response.headers['X-Polaris-Auth-Refresh'])) ||
        null
      if (status === 503 && String(hdr || '').toLowerCase() === 'unavailable') {
        const g = globalThis as typeof globalThis & {
          __polaris_auth_refresh_degraded_since?: number | null
        }
        if (!g.__polaris_auth_refresh_degraded_since) {
          g.__polaris_auth_refresh_degraded_since = Date.now()
        }
        window.dispatchEvent(new Event('polaris:auth-refresh-unavailable'))
      }
    } catch {
      // ignore
    }

    // If the session is invalid/expired, clear server cookie and bounce to login.
    try {
      const status = error.response?.status
      const url = String(error.config?.url || '')
      const isAuthEndpoint =
        url.includes('/api/session/') || url.includes('/api/auth/session/')
      const cfg = error.config || {}
      const alreadyRetried = Boolean((cfg as any).__polarisRetried)

      if (
        status === 401 &&
        !isAuthEndpoint &&
        typeof window !== 'undefined' &&
        !alreadyRetried
      ) {
        // Attempt a one-time silent refresh, then retry the original request.
        try {
          ;(cfg as any).__polarisRetried = true
          const refreshed = await (async () => {
            const g = globalThis as typeof globalThis & {
              __polaris_refresh_promise?: Promise<boolean> | null
              __polaris_refresh_unavailable_until?: number | null
            }
            const now = Date.now()
            if (
              g.__polaris_refresh_unavailable_until &&
              now < g.__polaris_refresh_unavailable_until
            ) {
              return false
            }
            if (!g.__polaris_refresh_promise) {
              g.__polaris_refresh_promise = fetch('/api/session/refresh', {
                method: 'POST',
              })
                .then((r) => {
                  // If refresh is temporarily unavailable, don't log the user out.
                  // Also set a short cooldown to avoid hammering.
                  if (r.status === 503) {
                    try {
                      const g = globalThis as typeof globalThis & {
                        __polaris_auth_refresh_degraded_since?: number | null
                      }
                      if (!g.__polaris_auth_refresh_degraded_since) {
                        g.__polaris_auth_refresh_degraded_since = Date.now()
                      }
                      window.dispatchEvent(
                        new Event('polaris:auth-refresh-unavailable'),
                      )
                    } catch {
                      // ignore
                    }
                    g.__polaris_refresh_unavailable_until = Date.now() + 10_000
                    return false
                  }
                  return Boolean(r.ok)
                })
                .catch(() => false)
                .finally(() => {
                  g.__polaris_refresh_promise = null
                })
            }
            return await g.__polaris_refresh_promise
          })()

          if (refreshed) {
            try {
              const g = globalThis as typeof globalThis & {
                __polaris_auth_refresh_degraded_since?: number | null
              }
              g.__polaris_auth_refresh_degraded_since = null
              window.dispatchEvent(new Event('polaris:auth-refresh-recovered'))
            } catch {
              // ignore
            }
            return await api.request(cfg)
          }
        } catch {
          // fall through to logout/redirect
        }

        // If refresh is currently unavailable, do NOT bounce to login.
        try {
          const g = globalThis as typeof globalThis & {
            __polaris_refresh_unavailable_until?: number | null
          }
          if (
            g.__polaris_refresh_unavailable_until &&
            Date.now() < g.__polaris_refresh_unavailable_until
          ) {
            return Promise.reject(error)
          }
        } catch {
          // ignore
        }

        const pathname = window.location.pathname || '/'
        const search = window.location.search || ''
        const isPublic =
          pathname === '/login' ||
          pathname === '/signup' ||
          pathname === '/reset-password' ||
          pathname.startsWith('/reset-password/')

        if (!isPublic) {
          // best-effort: clear cookie via BFF
          try {
            void fetch('/api/session/logout', { method: 'POST' })
          } catch {
            // ignore
          }

          const from = encodeURIComponent(`${pathname}${search}`)
          window.location.href = `/login?from=${from}`
        }
      }
    } catch (_e) {
      // ignore
    }

    return Promise.reject(error)
  },
)

export interface RFP {
  _id: string
  title: string
  clientName: string
  submissionDeadline?: string
  projectDeadline?: string
  budgetRange?: string
  projectType: string
  location?: string
  contactInformation?: string
  keyRequirements: string[]
  evaluationCriteria: any[]
  deliverables: string[]
  timeline?: string
  criticalInformation: string[]
  createdAt: string
  questionsDeadline?: string
  bidMeetingDate?: string
  bidRegistrationDate?: string
  isDisqualified?: boolean
  clarificationQuestions?: string[]
  attachments?: any[]
  dateWarnings?: string[]
  dateMeta?: any
  fitScore?: number
  fitReasons?: string[]
  sourceS3Key?: string
  sourceS3Uri?: string
  review?: {
    decision?: '' | 'bid' | 'no_bid' | 'maybe'
    notes?: string
    reasons?: string[]
    updatedAt?: string | null
    updatedBy?: string | null
    blockers?: {
      id?: string
      text: string
      status: 'open' | 'resolved' | 'waived'
    }[]
    requirements?: {
      text: string
      status: 'unknown' | 'ok' | 'risk' | 'gap'
      notes?: string
      mappedSections?: string[]
    }[]
  }
}

export interface Proposal {
  _id: string
  rfpId: string
  companyId?: string | null
  templateId: string
  title: string
  status: string
  contractingCaseId?: string | null
  sections: Record<string, any>
  generationStatus?: 'queued' | 'running' | 'complete' | 'error'
  generationError?: string | null
  generationStartedAt?: string | null
  generationCompletedAt?: string | null
  review?: {
    score?: number | null
    decision?: '' | 'shortlist' | 'reject'
    notes?: string
    rubric?: any
    updatedAt?: string | null
  }
  createdAt: string
  updatedAt: string
}

export type WorkflowTaskStatus = 'open' | 'done' | 'cancelled'

export interface WorkflowTask {
  _id: string
  taskId: string
  rfpId: string
  proposalId?: string | null
  stage: string
  templateId: string
  title: string
  description?: string
  status: WorkflowTaskStatus
  assigneeUserSub?: string | null
  assigneeDisplayName?: string | null
  createdAt: string
  updatedAt: string
  dueAt?: string | null
  completedAt?: string | null
  completedByUserSub?: string | null
}

export interface Template {
  id: string
  name: string
  projectType: string
  sectionCount: number
}

// ---- Contracting types ----
export type ContractingCaseStatus =
  | 'draft'
  | 'in_review'
  | 'ready'
  | 'sent'
  | 'signed'
  | 'archived'

export interface ContractingCase {
  _id: string
  proposalId: string
  rfpId: string
  companyId?: string | null
  status: ContractingCaseStatus
  keyTerms?: Record<string, any>
  keyTermsRawJson?: any
  owners?: Record<string, any>
  notes?: string
  audit?: any[]
  createdAt?: string
  updatedAt?: string
}

export interface ContractTemplate {
  _id: string
  templateId?: string
  name: string
  kind: 'msa' | 'sow' | 'combined' | string
  currentVersionId?: string | null
  createdAt?: string
  updatedAt?: string
}

export interface ContractTemplateVersion {
  _id: string
  templateId: string
  versionId: string
  s3Key: string
  sha256?: string | null
  variablesSchema?: Record<string, any>
  changelog?: string
  createdAt?: string
}

export interface ContractDocumentVersion {
  _id: string
  caseId: string
  versionId: string
  sourceTemplateId?: string | null
  sourceTemplateVersionId?: string | null
  renderInputs?: Record<string, any>
  docxS3Key: string
  pdfS3Key?: string | null
  status?: string
  createdAt?: string
}

export interface BudgetVersion {
  _id: string
  caseId: string
  versionId: string
  budgetModel?: Record<string, any>
  xlsxS3Key: string
  createdAt?: string
}

export interface SupportingDoc {
  _id: string
  caseId: string
  docId: string
  kind: string
  required: boolean
  status: string
  fileName: string
  contentType: string
  s3Key: string
  expiresAt?: string | null
  uploadedAt?: string | null
}

export interface ClientPackage {
  _id: string
  caseId: string
  packageId: string
  name: string
  selectedFiles: Array<{
    id: string
    kind: string
    label: string
    fileName?: string
    contentType?: string
    s3Key?: string
  }>
  publishedAt?: string | null
  revokedAt?: string | null
  portalTokenExpiresAt?: string | null
  createdAt?: string
  updatedAt?: string
}

export interface ESignEnvelope {
  _id: string
  caseId: string
  envelopeId: string
  provider: string
  status: string
  recipients?: any[]
  files?: any[]
  createdAt?: string
  updatedAt?: string
  sentAt?: string | null
  completedAt?: string | null
}

export interface CognitoProfileAttribute {
  name: string
  value: string
  required: boolean
  mutable: boolean
}

export interface CognitoProfileResponse {
  user: {
    sub: string
    username: string
    email?: string | null
    cognito_username: string
  }
  claims: Record<string, any>
  attributes: CognitoProfileAttribute[]
  schema: { name: string; required: boolean; mutable: boolean }[]
}

export interface UserProfile {
  _id: string
  userSub: string
  email?: string | null
  fullName?: string | null
  preferredName?: string | null
  jobTitles?: string[]
  certifications?: string[]
  resumeAssets?: {
    assetId: string
    fileName?: string | null
    contentType?: string | null
    s3Key: string
    s3Uri?: string | null
    uploadedAt?: string | null
  }[]
  profileCompletedAt?: string | null
  onboardingVersion?: number
  linkedTeamMemberId?: string | null
  slackUserId?: string | null
  aiPreferences?: Record<string, any>
  aiMemorySummary?: string | null
  createdAt?: string
  updatedAt?: string
}

export const userProfileApi = {
  get: () =>
    api.get<{
      ok: boolean
      user: { sub: string; email?: string | null; username?: string | null }
      profile: UserProfile
      isComplete: boolean
    }>(proxyUrl('/api/user-profile')),
  update: (data: Partial<UserProfile>) =>
    api.put(proxyUrl('/api/user-profile'), data),
  presignResume: (data: { fileName: string; contentType: string }) =>
    api.post(proxyUrl('/api/user-profile/resume/presign'), data),
  complete: () => api.post(proxyUrl('/api/user-profile/complete'), null),
}

// ---- Response helpers ----
// The backend has returned a few different shapes over time:
// - { data: [...] }
// - { data: { data: [...] } }
// - [...]
// This keeps UI list pages consistent.
export function extractList<T = any>(resp: any): T[] {
  const payload = resp?.data ?? resp
  if (Array.isArray(payload)) return payload as T[]
  if (Array.isArray(payload?.data)) return payload.data as T[]
  if (Array.isArray(payload?.data?.data)) return payload.data.data as T[]
  if (Array.isArray(payload?.items)) return payload.items as T[]
  if (Array.isArray(payload?.results)) return payload.results as T[]
  return []
}

export function extractNextToken(resp: any): string | null {
  const payload = resp?.data ?? resp
  const tok = payload?.nextToken ?? payload?.data?.nextToken
  return typeof tok === 'string' && tok ? tok : null
}

export type CursorListParams = {
  limit?: number
  nextToken?: string
}

// RFP API calls
export const rfpApi = {
  upload: async (file: File) => {
    // Avoid sending large multipart bodies through the Next.js proxy (can trigger 413).
    // Flow:
    // 1) Ask backend for a presigned PUT URL (small JSON through proxy)
    // 2) Upload PDF directly to S3 using that URL
    // 3) Tell backend to analyze the uploaded object (small JSON through proxy)
    const fileName = file?.name || 'upload.pdf'
    const contentType =
      (file?.type || '').toLowerCase() === 'application/pdf'
        ? 'application/pdf'
        : 'application/pdf'

    const sha256Hex = async (f: File): Promise<string> => {
      const buf = await f.arrayBuffer()
      const digest = await crypto.subtle.digest('SHA-256', buf)
      const bytes = new Uint8Array(digest)
      let hex = ''
      for (let i = 0; i < bytes.length; i++) {
        hex += bytes[i].toString(16).padStart(2, '0')
      }
      return hex
    }

    const sha256 = await sha256Hex(file)

    const presignResp = await api.post(proxyUrl('/api/rfp/upload/presign'), {
      fileName,
      contentType,
      sha256,
    })

    const isDup = Boolean(presignResp?.data?.duplicate)
    const dupRfpId = String(presignResp?.data?.rfpId || '')
    if (isDup && dupRfpId) {
      return api.get(proxyUrl(`/api/rfp/${cleanPathToken(dupRfpId)}`))
    }

    const putUrl = String(presignResp?.data?.putUrl || '')
    const key = String(presignResp?.data?.key || '')
    if (!putUrl || !key) {
      throw new Error('Failed to get upload URL')
    }

    const putRes = await fetch(putUrl, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body: file,
    })
    if (!putRes.ok) {
      throw new Error(`Upload failed (${putRes.status})`)
    }

    const jobResp = await api.post(proxyUrl('/api/rfp/upload/from-s3'), {
      key,
      fileName,
      sha256,
    })

    const jobId = String(jobResp?.data?.job?.jobId || '')
    if (!jobId) {
      throw new Error('Upload job was not created')
    }

    const maxMs = 5 * 60 * 1000
    const start = Date.now()
    let delayMs = 750

    // Poll until the backend finishes analysis (or fails).
    // Keep returning an AxiosResponse-compatible Promise at the end (like before).
    while (true) {
      if (Date.now() - start > maxMs) {
        throw new Error('RFP analysis timed out')
      }

      await new Promise((r) => setTimeout(r, delayMs))
      delayMs = Math.min(5000, Math.round(delayMs * 1.4))

      const statusResp = await api.get(
        proxyUrl(`/api/rfp/upload/jobs/${cleanPathToken(jobId)}`),
      )
      const job = statusResp?.data?.job
      const status = String(job?.status || '')

      if (status === 'completed') {
        const rfpId = String(job?.rfpId || '')
        if (!rfpId) {
          throw new Error('RFP job completed but no rfpId returned')
        }
        return api.get(proxyUrl(`/api/rfp/${cleanPathToken(rfpId)}`))
      }

      if (status === 'failed') {
        const err = String(job?.error || 'RFP analysis failed')
        throw new Error(err)
      }
    }
  },
  analyzeUrl: (url: string) => {
    return api.post(proxyUrl('/api/rfp/analyze-url'), { url })
  },
  analyzeUrls: (urls: string[]) =>
    api.post(proxyUrl('/api/rfp/analyze-urls'), { urls }),
  // Backend routes are defined with a trailing slash; avoid 307 redirects.
  list: (params?: CursorListParams) =>
    api.get<{ data: RFP[]; nextToken?: string | null }>(proxyUrl('/api/rfp/'), {
      params: {
        limit: params?.limit,
        nextToken: params?.nextToken,
      },
    }),
  get: (id: string) => api.get<RFP>(proxyUrl(`/api/rfp/${cleanPathToken(id)}`)),
  presignSourcePdf: (id: string) =>
    api.get(proxyUrl(`/api/rfp/${cleanPathToken(id)}/source-pdf/presign`)),
  update: (id: string, data: any) =>
    api.put<RFP>(proxyUrl(`/api/rfp/${cleanPathToken(id)}`), data),
  updateReview: (
    id: string,
    data: {
      decision?: '' | 'bid' | 'no_bid' | 'maybe'
      notes?: string
      reasons?: string[]
      blockers?: {
        id?: string
        text: string
        status: 'open' | 'resolved' | 'waived'
      }[]
      requirements?: {
        text: string
        status: 'unknown' | 'ok' | 'risk' | 'gap'
        notes?: string
        mappedSections?: string[]
      }[]
    },
  ) => api.put<RFP>(proxyUrl(`/api/rfp/${cleanPathToken(id)}/review`), data),
  delete: (id: string) =>
    api.delete(proxyUrl(`/api/rfp/${cleanPathToken(id)}`)),
  getSectionTitles: (id: string) =>
    api.post<{ titles: string[] }>(
      proxyUrl(`/api/rfp/${cleanPathToken(id)}/ai-section-titles`),
    ),
  reanalyze: (id: string) =>
    api.post<RFP>(proxyUrl(`/api/rfp/${cleanPathToken(id)}/ai-reanalyze`)),
  aiRefreshStreamUrl: (id: string) =>
    proxyUrl(`/api/rfp/${cleanPathToken(id)}/ai-refresh/stream`),
  aiSummaryStreamUrl: (id: string) =>
    proxyUrl(`/api/rfp/${cleanPathToken(id)}/ai-summary/stream`),
  aiSectionSummary: (
    id: string,
    data: { sectionId: string; topic?: string; force?: boolean },
  ) =>
    api.post<{
      ok: boolean
      sectionId: string
      topic: string
      summary: string
      updatedAt?: string | null
      cached?: boolean
    }>(proxyUrl(`/api/rfp/${cleanPathToken(id)}/ai-section-summary`), data),
  getProposals: (id: string) =>
    api.get<{ data: Proposal[] }>(
      proxyUrl(`/api/rfp/${cleanPathToken(id)}/proposals`),
    ),
  uploadAttachments: (id: string, data: FormData) =>
    api.post(
      proxyUrl(`/api/rfp/${cleanPathToken(id)}/upload-attachments`),
      data,
    ),
  deleteAttachment: (rfpId: string, attachmentId: string) =>
    api.delete(
      proxyUrl(
        `/api/rfp/${cleanPathToken(rfpId)}/attachments/${cleanPathToken(
          attachmentId,
        )}`,
      ),
    ),
  removeBuyerProfiles: (
    rfpId: string,
    data: { selected?: string[]; clear?: boolean },
  ) =>
    api.post(
      proxyUrl(`/api/rfp/${cleanPathToken(rfpId)}/buyer-profiles/remove`),
      data,
    ),
  getDriveFolder: (id: string) =>
    api.get<{
      ok: boolean
      folderUrl: string | null
      folderId?: string
      folders?: Record<string, string>
      error?: string
    }>(proxyUrl(`/api/rfp/${cleanPathToken(id)}/drive-folder`)),
}

export interface ScraperSource {
  id: string
  name: string
  description: string
  baseUrl: string
  requiresAuth: boolean
  available: boolean
}

export interface ScraperJob {
  id: string
  source: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  searchParams?: Record<string, any>
  candidatesFound?: number
  candidatesImported?: number
  error?: string
  createdAt?: string
  startedAt?: string
  completedAt?: string
}

export interface ScrapedCandidate {
  _id: string
  source: string
  sourceUrl: string
  title: string
  detailUrl?: string
  metadata?: Record<string, any>
  status: 'pending' | 'imported' | 'skipped' | 'failed'
  importedRfpId?: string
  createdAt?: string
}

export const scraperApi = {
  listSources: () =>
    api.get<{ ok: boolean; sources: ScraperSource[] }>(
      proxyUrl('/api/rfp/scrapers/sources'),
    ),
  run: (data: { source: string; searchParams?: Record<string, any> }) =>
    api.post<{ ok: boolean; job: ScraperJob }>(
      proxyUrl('/api/rfp/scrapers/run'),
      data,
    ),
  listJobs: (params: {
    source: string
    status?: string
    limit?: number
    nextToken?: string
  }) =>
    api.get<{ ok: boolean; jobs: ScraperJob[]; nextToken?: string }>(
      proxyUrl('/api/rfp/scrapers/jobs'),
      { params },
    ),
  getJob: (jobId: string) =>
    api.get<{ ok: boolean; job: ScraperJob }>(
      proxyUrl(`/api/rfp/scrapers/jobs/${cleanPathToken(jobId)}`),
    ),
  listCandidates: (params: {
    source: string
    status?: string
    limit?: number
    nextToken?: string
  }) =>
    api.get<{
      ok: boolean
      candidates: ScrapedCandidate[]
      nextToken?: string
    }>(proxyUrl('/api/rfp/scrapers/candidates'), { params }),
  getCandidate: (candidateId: string) =>
    api.get<{ ok: boolean; candidate: ScrapedCandidate }>(
      proxyUrl(
        `/api/rfp/scrapers/candidates/${cleanPathToken(candidateId)}`,
      ),
    ),
  importCandidate: (candidateId: string) =>
    api.post<{ ok: boolean; rfp?: RFP }>(
      proxyUrl(
        `/api/rfp/scrapers/candidates/${cleanPathToken(candidateId)}/import`,
      ),
      null,
    ),
}

export const tasksApi = {
  listForRfp: (rfpId: string) =>
    api.get<{ data: WorkflowTask[] }>(
      proxyUrl(`/api/rfp/${cleanPathToken(rfpId)}/tasks`),
    ),
  seedForRfp: (rfpId: string) =>
    api.post<{ ok: boolean; data: WorkflowTask[] }>(
      proxyUrl(`/api/rfp/${cleanPathToken(rfpId)}/tasks/seed`),
      null,
    ),
  assign: (
    taskId: string,
    data: { assigneeUserSub: string; assigneeDisplayName?: string | null },
  ) =>
    api.post<{ ok: boolean; task: WorkflowTask }>(
      proxyUrl(`/api/tasks/${cleanPathToken(taskId)}/assign`),
      data,
    ),
  complete: (taskId: string) =>
    api.post<{ ok: boolean; task: WorkflowTask }>(
      proxyUrl(`/api/tasks/${cleanPathToken(taskId)}/complete`),
      null,
    ),
  reopen: (taskId: string) =>
    api.post<{ ok: boolean; task: WorkflowTask }>(
      proxyUrl(`/api/tasks/${cleanPathToken(taskId)}/reopen`),
      null,
    ),
}

// ---- Contracting API calls (authenticated; proxied) ----
export const contractingApi = {
  getByProposal: (proposalId: string) =>
    api.get<{ ok: boolean; case: ContractingCase }>(
      proxyUrl(`/api/contracting/by-proposal/${cleanPathToken(proposalId)}`),
    ),
  get: (caseId: string) =>
    api.get<{ ok: boolean; case: ContractingCase }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}`),
    ),
  update: (caseId: string, data: Partial<ContractingCase>) =>
    api.put<{ ok: boolean; case: ContractingCase }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}`),
      data,
    ),
  listContractVersions: (caseId: string) =>
    api.get<{ ok: boolean; data: ContractDocumentVersion[] }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/contract/versions`),
    ),
  presignContractVersion: (caseId: string, versionId: string) =>
    api.get<{ ok: boolean; url: string; expiresIn: number }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(
          caseId,
        )}/contract/versions/${cleanPathToken(versionId)}/presign`,
      ),
    ),
  generateContract: (
    caseId: string,
    data: {
      templateId: string
      templateVersionId?: string | null
      renderInputs?: Record<string, any>
      idempotencyKey: string
    },
  ) =>
    api.post<{
      ok: boolean
      job: any
    }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/contract/generate`),
      data,
    ),
  listBudgetVersions: (caseId: string) =>
    api.get<{ ok: boolean; data: BudgetVersion[] }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/budget/versions`),
    ),
  presignBudgetVersion: (caseId: string, versionId: string) =>
    api.get<{ ok: boolean; url: string; expiresIn: number }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(
          caseId,
        )}/budget/versions/${cleanPathToken(versionId)}/presign`,
      ),
    ),
  generateBudgetXlsx: (
    caseId: string,
    data: { budgetModel?: Record<string, any>; idempotencyKey: string },
  ) =>
    api.post<{
      ok: boolean
      job: any
    }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(caseId)}/budget/generate-xlsx`,
      ),
      data,
    ),
  getJob: (jobId: string) =>
    api.get<{ ok: boolean; job: any }>(
      proxyUrl(`/api/contracting/jobs/${cleanPathToken(jobId)}`),
    ),
  listJobsForCase: (caseId: string, params?: CursorListParams) =>
    api.get<{ ok: boolean; data: any[]; nextToken?: string | null }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/jobs`),
      {
        params: {
          limit: params?.limit,
          nextToken: params?.nextToken,
        },
      },
    ),
  listSupportingDocs: (caseId: string) =>
    api.get<{ ok: boolean; data: SupportingDoc[] }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/supporting-docs`),
    ),
  presignSupportingDoc: (
    caseId: string,
    data: {
      fileName: string
      contentType: string
      kind: string
      required?: boolean
      expiresAt?: string | null
    },
  ) =>
    api.post<{
      ok: boolean
      docId: string
      key: string
      putUrl: string
      kind: string
      required: boolean
      expiresAt?: string | null
      fileName: string
      contentType: string
    }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(caseId)}/supporting-docs/presign`,
      ),
      data,
    ),
  commitSupportingDoc: (
    caseId: string,
    data: {
      docId: string
      key: string
      kind: string
      required?: boolean
      fileName: string
      contentType: string
      expiresAt?: string | null
    },
  ) =>
    api.post<{ ok: boolean; doc: SupportingDoc }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(caseId)}/supporting-docs/commit`,
      ),
      data,
    ),
  listPackages: (caseId: string) =>
    api.get<{ ok: boolean; data: ClientPackage[] }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/packages`),
    ),
  createPackage: (
    caseId: string,
    data: { name?: string | null; selectedFiles?: any[] },
  ) =>
    api.post<{ ok: boolean; package: ClientPackage }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/packages`),
      data,
    ),
  publishPackage: (
    caseId: string,
    packageId: string,
    data?: { ttlDays?: number },
  ) =>
    api.post<{ ok: boolean; package: ClientPackage; portalToken: string }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(caseId)}/packages/${cleanPathToken(
          packageId,
        )}/publish`,
      ),
      data || {},
    ),
  rotatePackage: (
    caseId: string,
    packageId: string,
    data?: { ttlDays?: number },
  ) =>
    api.post<{ ok: boolean; package: ClientPackage; portalToken: string }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(caseId)}/packages/${cleanPathToken(
          packageId,
        )}/rotate`,
      ),
      data || {},
    ),
  revokePackage: (caseId: string, packageId: string) =>
    api.post<{ ok: boolean; package: ClientPackage }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(caseId)}/packages/${cleanPathToken(
          packageId,
        )}/revoke`,
      ),
      null,
    ),
  createPackageZipJob: (
    caseId: string,
    packageId: string,
    data: { idempotencyKey: string },
  ) =>
    api.post<{ ok: boolean; job: any }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(caseId)}/packages/${cleanPathToken(
          packageId,
        )}/zip`,
      ),
      data,
    ),
  presignZipResult: (jobId: string) =>
    api.get<{ ok: boolean; url: string; expiresIn: number }>(
      proxyUrl(`/api/contracting/jobs/${cleanPathToken(jobId)}/zip/presign`),
    ),
  listEnvelopes: (caseId: string) =>
    api.get<{ ok: boolean; data: ESignEnvelope[] }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/esign/envelopes`),
    ),
  createEnvelope: (
    caseId: string,
    data: { provider?: string; recipients?: any[]; files?: any[] },
  ) =>
    api.post<{ ok: boolean; envelope: ESignEnvelope }>(
      proxyUrl(`/api/contracting/${cleanPathToken(caseId)}/esign/envelopes`),
      data,
    ),
  sendEnvelope: (caseId: string, envelopeId: string) =>
    api.post<{ ok: boolean; envelope: ESignEnvelope }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(
          caseId,
        )}/esign/envelopes/${cleanPathToken(envelopeId)}/send`,
      ),
      null,
    ),
  markEnvelopeSigned: (caseId: string, envelopeId: string) =>
    api.post<{ ok: boolean; envelope: ESignEnvelope }>(
      proxyUrl(
        `/api/contracting/${cleanPathToken(
          caseId,
        )}/esign/envelopes/${cleanPathToken(envelopeId)}/mark-signed`,
      ),
      null,
    ),
}

export const contractTemplatesApi = {
  list: (params?: CursorListParams) =>
    api.get<{ data: ContractTemplate[]; nextToken?: string | null }>(
      proxyUrl('/api/contract-templates/'),
      {
        params: { limit: params?.limit, nextToken: params?.nextToken },
      },
    ),
  create: (data: { name: string; kind: 'msa' | 'sow' | 'combined' }) =>
    api.post<{ _id: string } & ContractTemplate>(
      proxyUrl('/api/contract-templates/'),
      data,
    ),
  get: (templateId: string) =>
    api.get<ContractTemplate>(
      proxyUrl(`/api/contract-templates/${cleanPathToken(templateId)}`),
    ),
  update: (templateId: string, data: { currentVersionId: string }) =>
    api.put<{ ok: boolean; template: ContractTemplate }>(
      proxyUrl(`/api/contract-templates/${cleanPathToken(templateId)}`),
      data,
    ),
  listVersions: (templateId: string) =>
    api.get<{ ok: boolean; data: ContractTemplateVersion[] }>(
      proxyUrl(
        `/api/contract-templates/${cleanPathToken(templateId)}/versions`,
      ),
    ),
  presignVersionUpload: (
    templateId: string,
    data: { fileName: string; contentType: string },
  ) =>
    api.post<{
      ok: boolean
      templateId: string
      versionId: string
      key: string
      putUrl: string
    }>(
      proxyUrl(
        `/api/contract-templates/${cleanPathToken(
          templateId,
        )}/versions/presign`,
      ),
      data,
    ),
  commitVersion: (
    templateId: string,
    data: {
      versionId: string
      key: string
      sha256?: string
      changelog?: string
      variablesSchema?: any
    },
  ) =>
    api.post<{ ok: boolean; version: ContractTemplateVersion }>(
      proxyUrl(
        `/api/contract-templates/${cleanPathToken(templateId)}/versions/commit`,
      ),
      data,
    ),
  previewVersion: (
    templateId: string,
    versionId: string,
    data: { keyTerms?: any; renderInputs?: any },
  ) =>
    api.post<{ ok: boolean; key: string; url: string; expiresIn: number }>(
      proxyUrl(
        `/api/contract-templates/${cleanPathToken(
          templateId,
        )}/versions/${cleanPathToken(versionId)}/preview`,
      ),
      data,
    ),
}

// Proposal API calls
export const proposalApi = {
  generate: (data: {
    rfpId: string
    templateId: string
    title: string
    companyId?: string
    customContent?: any
    async?: boolean
  }) => api.post<Proposal>(proxyUrl('/api/proposals/generate'), data),
  generateSections: (proposalId: string) =>
    api.post(
      proxyUrl(
        `/api/proposals/${cleanPathToken(proposalId)}/generate-sections`,
      ),
    ),
  generateSectionsAsync: (proposalId: string) =>
    api.post(
      proxyUrl(
        `/api/proposals/${cleanPathToken(proposalId)}/generate-sections/async`,
      ),
      null,
    ),
  updateContentLibrarySection: (
    proposalId: string,
    sectionName: string,
    data: { type: 'team' | 'references' | 'company'; selectedIds: string[] },
  ) =>
    api.put(
      proxyUrl(
        `/api/proposals/${cleanPathToken(
          proposalId,
        )}/content-library/${encodeURIComponent(sectionName)}`,
      ),
      data,
    ),
  // Backend routes are defined with a trailing slash; avoid 307 redirects.
  list: (params?: CursorListParams) =>
    api.get<{ data: Proposal[]; nextToken?: string | null }>(
      proxyUrl('/api/proposals/'),
      {
        params: {
          limit: params?.limit,
          nextToken: params?.nextToken,
        },
      },
    ),
  get: (id: string) =>
    api.get<Proposal>(proxyUrl(`/api/proposals/${cleanPathToken(id)}`)),
  update: (id: string, data: any) =>
    api.put<Proposal>(proxyUrl(`/api/proposals/${cleanPathToken(id)}`), data),
  setCompany: (id: string, companyId: string) =>
    api.put<Proposal>(
      proxyUrl(`/api/proposals/${cleanPathToken(id)}/company`),
      {
        companyId,
      },
    ),
  updateReview: (
    id: string,
    data: {
      score?: number | null
      decision?: '' | 'shortlist' | 'reject' | null
      notes?: string
      rubric?: any
    },
  ) =>
    api.put<Proposal>(
      proxyUrl(`/api/proposals/${cleanPathToken(id)}/review`),
      data,
    ),
  delete: (id: string) =>
    api.delete(proxyUrl(`/api/proposals/${cleanPathToken(id)}`)),
  exportPdf: (id: string) =>
    api.get(proxyUrl(`/api/proposals/${cleanPathToken(id)}/export/pdf`), {
      responseType: 'blob',
    }),
  exportDocx: (id: string) =>
    api.get(proxyUrl(`/api/proposals/${cleanPathToken(id)}/export-docx`), {
      responseType: 'blob',
    }),
}

// Canva integration API calls
export const canvaApi = {
  status: () => api.get(proxyUrl(`/api/integrations/canva/status`)),
  connectUrl: (returnTo: string = '/templates') =>
    api.get(proxyUrl(`/api/integrations/canva/connect-url`), {
      params: { returnTo },
    }),
  disconnect: () => api.post(proxyUrl(`/api/integrations/canva/disconnect`)),
  listBrandTemplates: (query?: string) =>
    api.get(proxyUrl(`/api/integrations/canva/brand-templates`), {
      params: query ? { query } : undefined,
    }),
  getDataset: (brandTemplateId: string) =>
    api.get(
      proxyUrl(
        `/api/integrations/canva/brand-templates/${cleanPathToken(
          brandTemplateId,
        )}/dataset`,
      ),
    ),
  listCompanyMappings: () =>
    api.get(proxyUrl(`/api/integrations/canva/company-mappings`)),
  saveCompanyMapping: (companyId: string, data: any) =>
    api.put(
      proxyUrl(
        `/api/integrations/canva/company-mappings/${cleanPathToken(companyId)}`,
      ),
      data,
    ),
  getCompanyLogoLink: (companyId: string) =>
    api.get(
      proxyUrl(
        `/api/integrations/canva/companies/${cleanPathToken(companyId)}/logo`,
      ),
    ),
  uploadCompanyLogoFromUrl: (companyId: string, url: string, name?: string) =>
    api.post(
      proxyUrl(
        `/api/integrations/canva/companies/${cleanPathToken(
          companyId,
        )}/logo/upload-url`,
      ),
      { url, name },
    ),
  getTeamHeadshotLink: (memberId: string) =>
    api.get(
      proxyUrl(
        `/api/integrations/canva/team/${cleanPathToken(memberId)}/headshot`,
      ),
    ),
  uploadTeamHeadshotFromUrl: (memberId: string, url: string, name?: string) =>
    api.post(
      proxyUrl(
        `/api/integrations/canva/team/${cleanPathToken(
          memberId,
        )}/headshot/upload-url`,
      ),
      { url, name },
    ),
  createDesignFromProposal: (proposalId: string, opts?: { force?: boolean }) =>
    api.post(
      proxyUrl(
        `/api/integrations/canva/proposals/${cleanPathToken(
          proposalId,
        )}/create-design`,
      ),
      null,
      {
        params: opts?.force ? { force: 1 } : undefined,
      },
    ),
  validateProposal: (proposalId: string) =>
    api.post(
      proxyUrl(
        `/api/integrations/canva/proposals/${cleanPathToken(
          proposalId,
        )}/validate`,
      ),
    ),
  exportProposalPdf: (proposalId: string) =>
    api.get(
      proxyUrl(
        `/api/integrations/canva/proposals/${cleanPathToken(
          proposalId,
        )}/export-pdf`,
      ),
      {
        responseType: 'blob',
      },
    ),
}

// Template API calls
export const templateApi = {
  // Backend routes are defined with a trailing slash; avoid 307 redirects.
  list: () => api.get<{ data: Template[] }>(proxyUrl('/api/templates/')),
  get: (id: string) =>
    api.get(proxyUrl(`/api/templates/${cleanPathToken(id)}`)),
  create: (data: any) => api.post(proxyUrl('/api/templates/'), data),
  update: (id: string, data: any) =>
    api.put(proxyUrl(`/api/templates/${cleanPathToken(id)}`), data),
  delete: (id: string) =>
    api.delete(proxyUrl(`/api/templates/${cleanPathToken(id)}`)),
  preview: (id: string, rfpData?: any) =>
    api.get(proxyUrl(`/api/templates/${cleanPathToken(id)}/preview`), {
      params: rfpData,
    }),
}

// Content API calls
export const contentApi = {
  getCompany: () => api.get(proxyUrl('/api/content/company')),
  getCompanies: () => api.get(proxyUrl('/api/content/companies')),
  getCompanyById: (companyId: string) =>
    api.get(proxyUrl(`/api/content/companies/${cleanPathToken(companyId)}`)),
  regenerateCompanyCapabilities: (companyId: string) =>
    api.post(
      proxyUrl(
        `/api/content/companies/${cleanPathToken(
          companyId,
        )}/capabilities/regenerate`,
      ),
    ),
  createCompany: (data: any) =>
    api.post(proxyUrl('/api/content/companies'), data),
  updateCompany: (data: any) => api.put(proxyUrl('/api/content/company'), data),
  updateCompanyById: (companyId: string, data: any) =>
    api.put(
      proxyUrl(`/api/content/companies/${cleanPathToken(companyId)}`),
      data,
    ),
  deleteCompany: (companyId: string) =>
    api.delete(proxyUrl(`/api/content/companies/${cleanPathToken(companyId)}`)),
  getTeam: () => api.get(proxyUrl('/api/content/team')),
  getTeamMember: (id: string) =>
    api.get(proxyUrl(`/api/content/team/${cleanPathToken(id)}`)),
  presignTeamHeadshotUpload: (data: {
    fileName: string
    contentType: string
    memberId?: string
  }) => api.post(proxyUrl(`/api/content/team/headshot/presign`), data),
  createTeamMember: (data: any) =>
    api.post(proxyUrl('/api/content/team'), data),
  updateTeamMember: (memberId: string, data: any) =>
    api.put(proxyUrl(`/api/content/team/${cleanPathToken(memberId)}`), data),
  deleteTeamMember: (memberId: string) =>
    api.delete(proxyUrl(`/api/content/team/${cleanPathToken(memberId)}`)),
  getProjects: (params?: {
    companyId?: string
    projectType?: string
    industry?: string
    count?: number
  }) => api.get(proxyUrl('/api/content/projects'), { params }),
  getProjectById: (id: string) =>
    api.get(proxyUrl(`/api/content/projects/${cleanPathToken(id)}`)),
  createProject: (data: any) =>
    api.post(proxyUrl('/api/content/projects'), data),
  updateProject: (id: string, data: any) =>
    api.put(proxyUrl(`/api/content/projects/${cleanPathToken(id)}`), data),
  deleteProject: (id: string) =>
    api.delete(proxyUrl(`/api/content/projects/${cleanPathToken(id)}`)),
  getReferences: (params?: {
    projectType?: string
    companyId?: string
    count?: number
  }) =>
    api.get(proxyUrl('/api/content/references'), {
      params: {
        project_type: params?.projectType,
        companyId: params?.companyId,
        count: params?.count,
      },
    }),
  getReferenceById: (id: string) =>
    api.get(proxyUrl(`/api/content/references/${cleanPathToken(id)}`)),
  createReference: (data: any) =>
    api.post(proxyUrl('/api/content/references'), data),
  updateReference: (id: string, data: any) =>
    api.put(proxyUrl(`/api/content/references/${cleanPathToken(id)}`), data),
  deleteReference: (id: string) =>
    api.delete(proxyUrl(`/api/content/references/${cleanPathToken(id)}`)),
}

// AI API calls
export const aiApi = {
  editText: (data: { text?: string; selectedText?: string; prompt: string }) =>
    api.post(proxyUrl('/api/ai/edit-text'), data),
  generateContent: (data: {
    prompt: string
    context?: string
    contentType?: string
  }) => api.post(proxyUrl('/api/ai/generate-content'), data),
}

export const aiJobsApi = {
  get: (jobId: string) =>
    api.get(proxyUrl(`/api/ai/jobs/${cleanPathToken(jobId)}`)),
}

// Finder (LinkedIn) API calls
export const finderApi = {
  getStorageStateStatus: () =>
    api.get<{ connected: boolean }>(
      proxyUrl('/api/finder/linkedin/storage-state/status'),
    ),
  validateSession: () =>
    api.get(proxyUrl('/api/finder/linkedin/session/validate')),
  uploadStorageState: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(proxyUrl('/api/finder/linkedin/storage-state'), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  startRun: (data: {
    rfpId: string
    companyName?: string
    companyLinkedInUrl?: string
    maxPeople?: number
    targetTitles?: string[]
  }) => api.post(proxyUrl('/api/finder/runs'), data),
  getRun: (runId: string) =>
    api.get(proxyUrl(`/api/finder/runs/${cleanPathToken(runId)}`)),
  listProfiles: (runId: string, limit: number = 200) =>
    api.get(proxyUrl(`/api/finder/runs/${cleanPathToken(runId)}/profiles`), {
      params: { limit },
    }),
  saveTopToRfp: (
    runId: string,
    data: {
      rfpId: string
      topN?: number
      mode?: 'merge' | 'overwrite'
      selected?: string[]
    },
  ) =>
    api.post(
      proxyUrl(`/api/finder/runs/${cleanPathToken(runId)}/save-to-rfp`),
      data,
    ),
}

export const profileApi = {
  get: () => api.get<CognitoProfileResponse>(proxyUrl('/api/profile')),
  updateAttributes: (attributes: { name: string; value: string | null }[]) =>
    api.put<CognitoProfileResponse>(proxyUrl('/api/profile/attributes'), {
      attributes,
    }),
  deleteAttribute: (name: string) =>
    api.delete<CognitoProfileResponse>(
      proxyUrl(`/api/profile/attributes/${encodeURIComponent(name)}`),
    ),
}

export const magicLinkApi = {
  request: (data: { email: string; username?: string; returnTo?: string }) =>
    api.post('/api/session/magic-link/request', data),
  verify: (data: { magicId: string; code: string }) =>
    api.post<{
      ok: boolean
      returnTo?: string | null
    }>('/api/session/magic-link/verify', data),
}

export interface AgentJob {
  _id?: string
  jobId: string
  jobType: string
  status:
    | 'queued'
    | 'running'
    | 'checkpointed'
    | 'completed'
    | 'failed'
    | 'cancelled'
  scope: Record<string, any>
  payload?: Record<string, any>
  dueAt: string
  createdAt: string
  updatedAt: string
  startedAt?: string
  finishedAt?: string
  requestedByUserSub?: string
  dependsOn?: string[]
  checkpointId?: string
  result?: Record<string, any>
  error?: string
}

export const integrationsApi = {
  getStatus: () =>
    api.get<{
      ok: boolean
      integrations: {
        googleDrive?: {
          status: 'green' | 'yellow' | 'red'
          statusMessage: string
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
        canva?: {
          status: 'green' | 'yellow' | 'red'
          statusMessage: string
          connected: boolean
          error: string | null
          connection?: Record<string, any>
        }
      }
    }>(proxyUrl('/api/integrations/status')),
  getActivities: (limit?: number) =>
    api.get<{
      ok: boolean
      activities: Array<{
        integration: 'canva' | 'googleDrive' | 'slack' | 'github'
        type: string
        tool?: string
        createdAt: string
        payload?: Record<string, any>
      }>
      count: number
    }>(proxyUrl('/api/integrations/activities'), {
      params: limit ? { limit } : undefined,
    }),
}

export const agentsApi = {
  getInfrastructure: () =>
    api.get<{
      ok: boolean
      infrastructure: {
        baseAgentClass: string
        workers: Array<{
          name: string
          description: string
          schedule: string
        }>
        memory: {
          type: string
          tableName: string
        }
      }
    }>(proxyUrl('/api/agents/infrastructure')),
  listJobs: (params?: {
    limit?: number
    status?: string
    jobType?: string
    rfpId?: string
  }) =>
    api.get<{
      ok: boolean
      jobs: AgentJob[]
      count: number
      statusCounts: Record<string, number>
    }>(proxyUrl('/api/agents/jobs'), { params }),
  getJob: (jobId: string) =>
    api.get<{ ok: boolean; job: AgentJob }>(
      proxyUrl(`/api/agents/jobs/${cleanPathToken(jobId)}`),
    ),
  createJob: (data: {
    jobType: string
    scope: Record<string, any>
    dueAt: string
    payload?: Record<string, any>
    dependsOn?: string[]
  }) =>
    api.post<{ ok: boolean; job: AgentJob }>(
      proxyUrl('/api/agents/jobs'),
      data,
    ),
  updateJob: (
    jobId: string,
    data: {
      dueAt?: string
      payload?: Record<string, any>
      scope?: Record<string, any>
      dependsOn?: string[]
    },
  ) =>
    api.put<{ ok: boolean; job: AgentJob }>(
      proxyUrl(`/api/agents/jobs/${cleanPathToken(jobId)}`),
      data,
    ),
  cancelJob: (jobId: string) =>
    api.post<{ ok: boolean; job: AgentJob }>(
      proxyUrl(`/api/agents/jobs/${cleanPathToken(jobId)}/cancel`),
    ),
  deleteJob: (jobId: string) =>
    api.delete<{ ok: boolean; message: string }>(
      proxyUrl(`/api/agents/jobs/${cleanPathToken(jobId)}`),
    ),
  getActivity: (params?: {
    hours?: number
    limit?: number
    rfpId?: string
    userSubFilter?: string
  }) =>
    api.get<{
      ok: boolean
      since: string
      count: number
      events: Array<any>
    }>(proxyUrl('/api/agents/activity'), { params }),
  getMetrics: (params?: { hours?: number; operationType?: string }) =>
    api.get<{
      ok: boolean
      since: string
      hours: number
      operationType?: string
      metrics: {
        count: number
        avg_duration_ms: number
        avg_steps: number
        success_rate: number
        p50_duration_ms?: number
        p95_duration_ms?: number
        p99_duration_ms?: number
      }
    }>(proxyUrl('/api/agents/metrics'), { params }),
  getDiagnostics: (params?: {
    hours?: number
    rfpId?: string
    userSub?: string
    channelId?: string
  }) =>
    api.get<{
      ok: boolean
      window: {
        start: string
        end: string
        hours: number
      }
      metrics: any
      recentJobs: any[]
      recentActivities: any[]
      [key: string]: any
    }>(proxyUrl('/api/agents/diagnostics'), { params }),
  getWorkers: () =>
    api.get<{
      ok: boolean
      workers: Array<{
        name: string
        schedule: string
        description: string
        logGroup?: string
        resources?: {
          cpu?: string
          memory?: string
        }
      }>
      note: string
    }>(proxyUrl('/api/agents/workers')),
}

export const proposalApiPdf = {
  generate: (data: {
    rfpId: string
    templateId: string
    title: string
    customContent?: any
  }) => api.post<Proposal>(proxyUrl('/api/proposals/generate'), data),
  list: (params?: CursorListParams) =>
    api.get<{ data: Proposal[]; nextToken?: string | null }>(
      proxyUrl('/api/proposals/'),
      {
        params: {
          limit: params?.limit,
          nextToken: params?.nextToken,
        },
      },
    ),
  get: (id: string) =>
    api.get<Proposal>(proxyUrl(`/api/proposals/${cleanPathToken(id)}`)),
  update: (id: string, data: any) =>
    api.put<Proposal>(proxyUrl(`/api/proposals/${cleanPathToken(id)}`), data),
  delete: (id: string) =>
    api.delete(proxyUrl(`/api/proposals/${cleanPathToken(id)}`)),

  // ✅ FIXED ENDPOINT
  exportPdf: (id: string) =>
    api.get(proxyUrl(`/api/proposals/${cleanPathToken(id)}/export-pdf`), {
      responseType: 'blob',
    }),
  exportDocx: (id: string) =>
    api.get(proxyUrl(`/api/proposals/${cleanPathToken(id)}/export-docx`), {
      responseType: 'blob',
    }),
}

export default api
