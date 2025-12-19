export interface TeamMember {
  _id: string
  memberId: string
  nameWithCredentials: string
  position: string
  email?: string
  companyId?: string
  biography: string
  headshotUrl?: string
  bioProfiles?: Array<{
    id: string
    label: string
    projectTypes: string[]
    bio: string
    experience?: string
  }>
  isActive: boolean
  company?: {
    companyId: string
    name: string
    sharedInfo?: string
  }
}

export interface ProjectReference {
  _id: string
  companyId?: string
  organizationName: string
  timePeriod?: string
  contactName: string
  contactTitle?: string
  additionalTitle?: string
  scopeOfWork: string
  contactEmail: string
  contactPhone?: string
}

export interface Company {
  _id: string
  companyId: string
  name: string
  description: string
  email?: string
  phone?: string
  coverLetter?: string
  capabilitiesStatement?: string
  capabilitiesStatementMeta?: {
    generatedAt?: string
    generator?: string
    model?: string
    projectIds?: string[]
    referenceIds?: string[]
    capabilities?: string[]
    limitations?: string[]
    evidenceItems?: Array<{
      type: 'project' | 'reference'
      id: string
      label: string
    }>
  }
}

export interface ContentLibraryModalProps {
  isOpen: boolean
  onClose: () => void
  onApply: (selectedIds: string[]) => void
  type: 'team' | 'references' | 'company'
  currentSelectedIds?: string[]
  isLoading?: boolean
}
