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
    return response
  },
  (error: AxiosError | any) => {
    console.error('Response error:', {
      url: error.config?.url,
      status: error.response?.status,
      data: error.response?.data,
      message: error.message,
    })

    // If the session is invalid/expired, clear server cookie and bounce to login.
    try {
      const status = error.response?.status
      const url = String(error.config?.url || '')
      const isAuthEndpoint = url.includes('/api/session/')

      if (status === 401 && !isAuthEndpoint && typeof window !== 'undefined') {
        // best-effort: clear cookie via BFF
        try {
          void fetch('/api/session/logout', { method: 'POST' })
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
  sections: Record<string, any>
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

export interface Template {
  id: string
  name: string
  projectType: string
  sectionCount: number
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

    const presignResp = await api.post(proxyUrl('/api/rfp/upload/presign'), {
      fileName,
      contentType,
    })

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
}

// Proposal API calls
export const proposalApi = {
  generate: (data: {
    rfpId: string
    templateId: string
    title: string
    companyId?: string
    customContent?: any
  }) => api.post<Proposal>(proxyUrl('/api/proposals/generate'), data),
  generateSections: (proposalId: string) =>
    api.post(
      proxyUrl(
        `/api/proposals/${cleanPathToken(proposalId)}/generate-sections`,
      ),
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
