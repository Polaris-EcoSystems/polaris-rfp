import axios from 'axios'

function normalizeApiBaseUrl(input: string): string {
  const raw = String(input || '').trim()
  if (!raw) return ''
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw
  // If a hostname was provided (common for App Runner ServiceUrl), default to https.
  if (raw.includes('localhost')) return `http://${raw}`
  return `https://${raw}`
}

const API_BASE_URL = normalizeApiBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.API_BASE_URL ||
    'https://api.rfp.polariseco.com',
)

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 5 minute timeout for PDF generation
})

// Add request interceptor for debugging
api.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  },
)

// Add response interceptor for debugging
api.interceptors.response.use(
  (response) => {
    console.log(
      `Response received from ${response.config.url}:`,
      response.status,
    )
    return response
  },
  (error) => {
    console.error('Response error:', {
      url: error.config?.url,
      status: error.response?.status,
      data: error.response?.data,
      message: error.message,
    })

    // If the token is invalid/expired, clear it and bounce to login.
    try {
      const status = error.response?.status
      const url = String(error.config?.url || '')
      const isAuthEndpoint =
        url.includes('/api/auth/login') ||
        url.includes('/api/auth/signup') ||
        url.includes('/api/auth/request-password-reset') ||
        url.includes('/api/auth/reset-password')

      if (status === 401 && !isAuthEndpoint && typeof window !== 'undefined') {
        localStorage.removeItem('token')
        sessionStorage.removeItem('token')
        delete api.defaults.headers.common['Authorization']

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

// RFP API calls
export const rfpApi = {
  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/api/rfp/upload', formData)
  },
  analyzeUrl: (url: string) => {
    return api.post('/api/rfp/analyze-url', { url })
  },
  analyzeUrls: (urls: string[]) => api.post('/api/rfp/analyze-urls', { urls }),
  list: () => api.get<{ data: RFP[] }>('/api/rfp'),
  get: (id: string) => api.get<RFP>(`/api/rfp/${id}`),
  update: (id: string, data: any) => api.put<RFP>(`/api/rfp/${id}`, data),
  delete: (id: string) => api.delete(`/api/rfp/${id}`),
  getSectionTitles: (id: string) =>
    api.post<{ titles: string[] }>(`/api/rfp/${id}/ai-section-titles`),
  getProposals: (id: string) =>
    api.get<{ data: Proposal[] }>(`/api/rfp/${id}/proposals`),
  uploadAttachments: (id: string, data: FormData) =>
    api.post(`/api/rfp/${id}/upload-attachments`, data),
  deleteAttachment: (rfpId: string, attachmentId: string) =>
    api.delete(`/api/rfp/${rfpId}/attachments/${attachmentId}`),
}

// Proposal API calls
export const proposalApi = {
  generate: (data: {
    rfpId: string
    templateId: string
    title: string
    companyId?: string
    customContent?: any
  }) => api.post<Proposal>('/api/proposals/generate', data),
  list: () => api.get<{ data: Proposal[] }>('/api/proposals'),
  get: (id: string) => api.get<Proposal>(`/api/proposals/${id}`),
  update: (id: string, data: any) =>
    api.put<Proposal>(`/api/proposals/${id}`, data),
  setCompany: (id: string, companyId: string) =>
    api.put<Proposal>(`/api/proposals/${id}/company`, { companyId }),
  updateReview: (
    id: string,
    data: {
      score?: number | null
      decision?: '' | 'shortlist' | 'reject' | null
      notes?: string
      rubric?: any
    },
  ) => api.put<Proposal>(`/api/proposals/${id}/review`, data),
  delete: (id: string) => api.delete(`/api/proposals/${id}`),
  exportPdf: (id: string) =>
    api.get(`/api/proposals/${id}/export/pdf`, { responseType: 'blob' }),
  exportDocx: (id: string) =>
    api.get(`/api/proposals/${id}/export-docx`, { responseType: 'blob' }),
}

// Canva integration API calls
export const canvaApi = {
  status: () => api.get(`/api/integrations/canva/status`),
  connectUrl: (returnTo: string = '/integrations/canva') =>
    api.get(`/api/integrations/canva/connect-url`, { params: { returnTo } }),
  disconnect: () => api.post(`/api/integrations/canva/disconnect`),
  listBrandTemplates: (query?: string) =>
    api.get(`/api/integrations/canva/brand-templates`, {
      params: query ? { query } : undefined,
    }),
  getDataset: (brandTemplateId: string) =>
    api.get(
      `/api/integrations/canva/brand-templates/${brandTemplateId}/dataset`,
    ),
  listCompanyMappings: () =>
    api.get(`/api/integrations/canva/company-mappings`),
  saveCompanyMapping: (companyId: string, data: any) =>
    api.put(`/api/integrations/canva/company-mappings/${companyId}`, data),
  getCompanyLogoLink: (companyId: string) =>
    api.get(`/api/integrations/canva/companies/${companyId}/logo`),
  uploadCompanyLogoFromUrl: (companyId: string, url: string, name?: string) =>
    api.post(`/api/integrations/canva/companies/${companyId}/logo/upload-url`, {
      url,
      name,
    }),
  getTeamHeadshotLink: (memberId: string) =>
    api.get(`/api/integrations/canva/team/${memberId}/headshot`),
  uploadTeamHeadshotFromUrl: (memberId: string, url: string, name?: string) =>
    api.post(`/api/integrations/canva/team/${memberId}/headshot/upload-url`, {
      url,
      name,
    }),
  createDesignFromProposal: (proposalId: string, opts?: { force?: boolean }) =>
    api.post(
      `/api/integrations/canva/proposals/${proposalId}/create-design`,
      null,
      {
        params: opts?.force ? { force: 1 } : undefined,
      },
    ),
  validateProposal: (proposalId: string) =>
    api.post(`/api/integrations/canva/proposals/${proposalId}/validate`),
  exportProposalPdf: (proposalId: string) =>
    api.get(`/api/integrations/canva/proposals/${proposalId}/export-pdf`, {
      responseType: 'blob',
    }),
}

// Template API calls
export const templateApi = {
  list: () => api.get<{ data: Template[] }>('/api/templates'),
  get: (id: string) => api.get(`/api/templates/${id}`),
  create: (data: any) => api.post('/api/templates', data),
  update: (id: string, data: any) => api.put(`/api/templates/${id}`, data),
  delete: (id: string) => api.delete(`/api/templates/${id}`),
  preview: (id: string, rfpData?: any) =>
    api.get(`/api/templates/${id}/preview`, { params: rfpData }),
}

// Content API calls
export const contentApi = {
  getCompany: () => api.get('/api/content/company'),
  getCompanies: () => api.get('/api/content/companies'),
  getCompanyById: (companyId: string) =>
    api.get(`/api/content/companies/${companyId}`),
  createCompany: (data: any) => api.post('/api/content/companies', data),
  updateCompany: (data: any) => api.put('/api/content/company', data),
  updateCompanyById: (companyId: string, data: any) =>
    api.put(`/api/content/companies/${companyId}`, data),
  deleteCompany: (companyId: string) =>
    api.delete(`/api/content/companies/${companyId}`),
  getTeam: () => api.get('/api/content/team'),
  getTeamMember: (id: string) => api.get(`/api/content/team/${id}`),
  presignTeamHeadshotUpload: (data: {
    fileName: string
    contentType: string
    memberId?: string
  }) => api.post(`/api/content/team/headshot/presign`, data),
  createTeamMember: (data: any) => api.post('/api/content/team', data),
  updateTeamMember: (memberId: string, data: any) =>
    api.put(`/api/content/team/${memberId}`, data),
  deleteTeamMember: (memberId: string) =>
    api.delete(`/api/content/team/${memberId}`),
  getProjects: () => api.get('/api/content/projects'),
  getProjectById: (id: string) => api.get(`/api/content/projects/${id}`),
  createProject: (data: any) => api.post('/api/content/projects', data),
  updateProject: (id: string, data: any) =>
    api.put(`/api/content/projects/${id}`, data),
  deleteProject: (id: string) => api.delete(`/api/content/projects/${id}`),
  getReferences: (projectType?: string) =>
    api.get('/api/content/references', {
      params: { project_type: projectType },
    }),
  getReferenceById: (id: string) => api.get(`/api/content/references/${id}`),
  createReference: (data: any) => api.post('/api/content/references', data),
  updateReference: (id: string, data: any) =>
    api.put(`/api/content/references/${id}`, data),
  deleteReference: (id: string) => api.delete(`/api/content/references/${id}`),
}

// AI API calls
export const aiApi = {
  editText: (data: { text?: string; selectedText?: string; prompt: string }) =>
    api.post('/api/ai/edit-text', data),
  generateContent: (data: {
    prompt: string
    context?: string
    contentType?: string
  }) => api.post('/api/ai/generate-content', data),
}

export const profileApi = {
  get: () => api.get<CognitoProfileResponse>('/api/profile'),
  updateAttributes: (attributes: { name: string; value: string | null }[]) =>
    api.put<CognitoProfileResponse>('/api/profile/attributes', { attributes }),
  deleteAttribute: (name: string) =>
    api.delete<CognitoProfileResponse>(
      `/api/profile/attributes/${encodeURIComponent(name)}`,
    ),
}

export const magicLinkApi = {
  request: (data: { email: string; username?: string; returnTo?: string }) =>
    api.post('/api/auth/magic-link/request', data),
  verify: (data: { magicId: string; code: string }) =>
    api.post<{
      access_token: string
      token_type: string
      expires_in: string
      returnTo?: string
    }>('/api/auth/magic-link/verify', data),
}
export const proposalApiPdf = {
  generate: (data: {
    rfpId: string
    templateId: string
    title: string
    customContent?: any
  }) => api.post<Proposal>('/api/proposals/generate', data),
  list: () => api.get<{ data: Proposal[] }>('/api/proposals'),
  get: (id: string) => api.get<Proposal>(`/api/proposals/${id}`),
  update: (id: string, data: any) =>
    api.put<Proposal>(`/api/proposals/${id}`, data),
  delete: (id: string) => api.delete(`/api/proposals/${id}`),

  // ✅ FIXED ENDPOINT
  exportPdf: (id: string) =>
    api.get(`/api/proposals/${id}/export-pdf`, { responseType: 'blob' }),
  exportDocx: (id: string) =>
    api.get(`/api/proposals/${id}/export-docx`, { responseType: 'blob' }),
}

export default api
