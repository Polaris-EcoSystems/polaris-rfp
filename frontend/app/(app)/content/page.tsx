'use client'

import CompanySection from '@/components/content/CompanySection'
import AddMemberModal from '@/components/content/modals/AddMemberModal'
import AddProjectModal from '@/components/content/modals/AddProjectModal'
import AddReferenceModal from '@/components/content/modals/AddReferenceModal'
import EditMemberModal from '@/components/content/modals/EditMemberModal'
import EditProjectModal from '@/components/content/modals/EditProjectModal'
import EditReferenceModal from '@/components/content/modals/EditReferenceModal'
import ProjectsSection from '@/components/content/ProjectsSection'
import ReferencesSection from '@/components/content/ReferencesSection'
import TeamSection from '@/components/content/TeamSection'
import Button from '@/components/ui/Button'
import DeleteConfirmationModal from '@/components/ui/DeleteConfirmationModal'
import Modal from '@/components/ui/Modal'
import PipelineContextBanner from '@/components/ui/PipelineContextBanner'
import StepsPanel from '@/components/ui/StepsPanel'
import { useToast } from '@/components/ui/Toast'
import { contentApi } from '@/lib/api'
import {
  ClipboardDocumentListIcon,
  FolderIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'

export default function ContentLibraryPage() {
  const toast = useToast()
  const [activeTab, setActiveTab] = useState<
    'company' | 'team' | 'projects' | 'references'
  >('company')
  const [globalQuery, setGlobalQuery] = useState('')
  const [projectsProjectTypeFilter, setProjectsProjectTypeFilter] = useState('')
  const [projectsIndustryFilter, setProjectsIndustryFilter] = useState('')
  const [referencesProjectTypeFilter, setReferencesProjectTypeFilter] =
    useState('')
  const [showDataHealth, setShowDataHealth] = useState(true)
  const [qualityFilter, setQualityFilter] = useState<{
    tab: 'team' | 'projects' | 'references'
    label: string
    ids: string[]
  } | null>(null)
  const [companies, setCompanies] = useState<any[]>([])
  const [selectedCompany, setSelectedCompany] = useState<any>(null)
  const [team, setTeam] = useState<any[]>([])
  const [selectedMember, setSelectedMember] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string>('')
  const [editingCompany, setEditingCompany] = useState(false)
  const [editingMember, setEditingMember] = useState<any>(null)
  const [showAddMember, setShowAddMember] = useState(false)
  const [showAddCompany, setShowAddCompany] = useState(false)
  const [companyForm, setCompanyForm] = useState<any>({})
  const [memberForm, setMemberForm] = useState<any>({
    nameWithCredentials: '',
    position: '',
    email: '',
    companyId: null,
    biography: '',
    headshotUrl: '',
    headshotS3Key: null,
    headshotS3Uri: null,
    bioProfiles: [],
  })
  const [projects, setProjects] = useState<any[]>([])
  const [references, setReferences] = useState<any[]>([])
  const [selectedProject, setSelectedProject] = useState<any>(null)
  const [selectedReference, setSelectedReference] = useState<any>(null)
  const [showViewReference, setShowViewReference] = useState(false)
  const [showAddProject, setShowAddProject] = useState(false)
  const [showAddReference, setShowAddReference] = useState(false)
  const [editingProject, setEditingProject] = useState<any>(null)
  const [editingReference, setEditingReference] = useState<any>(null)
  const [projectForm, setProjectForm] = useState<any>({
    title: '',
    clientName: '',
    description: '',
    industry: '',
    projectType: '',
    duration: '',
    budget: '',
    keyOutcomes: [''],
    technologies: [''],
    challenges: [''],
    solutions: [''],
    files: [],
  })
  const [referenceForm, setReferenceForm] = useState<any>({
    organizationName: '',
    timePeriod: '',
    contactName: '',
    contactTitle: '',
    additionalTitle: '',
    contactEmail: '',
    contactPhone: '',
    scopeOfWork: '',
    isPublic: true,
  })

  // Delete confirmation modal state
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{
    type: 'company' | 'member' | 'project' | 'reference'
    item: any
  } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const loadContent = useCallback(async () => {
    try {
      setLoadError('')
      const [
        companiesResponse,
        teamResponse,
        projectsResponse,
        referencesResponse,
      ] = await Promise.all([
        contentApi.getCompanies(),
        contentApi.getTeam(),
        contentApi.getProjects?.() || Promise.resolve({ data: [] }),
        contentApi.getReferences(),
      ])
      const companiesData = Array.isArray(companiesResponse.data)
        ? companiesResponse.data
        : []
      setCompanies(companiesData)
      if (companiesData.length > 0) {
        setSelectedCompany(companiesData[0])
      }
      setTeam(Array.isArray(teamResponse.data) ? teamResponse.data : [])
      setProjects(
        Array.isArray(projectsResponse.data) ? projectsResponse.data : [],
      )
      setReferences(
        Array.isArray(referencesResponse.data) ? referencesResponse.data : [],
      )
    } catch (error) {
      console.error('Error loading content:', error)
      setLoadError('Failed to load Content Library.')
      toast.error('Failed to load Content Library')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    loadContent()
  }, [loadContent])

  const selectedCompanyId = selectedCompany?.companyId || null
  const [teamScope, setTeamScope] = useState<'company' | 'unassigned' | 'all'>(
    selectedCompanyId ? 'company' : 'all',
  )
  const [projectsScope, setProjectsScope] = useState<
    'company' | 'unassigned' | 'all'
  >(selectedCompanyId ? 'company' : 'all')
  const [referencesScope, setReferencesScope] = useState<
    'company' | 'unassigned' | 'all'
  >(selectedCompanyId ? 'company' : 'all')

  useEffect(() => {
    // If no company is selected, "company" scope makes no sense.
    if (!selectedCompanyId) {
      setTeamScope((s) => (s === 'company' ? 'all' : s))
      setProjectsScope((s) => (s === 'company' ? 'all' : s))
      setReferencesScope((s) => (s === 'company' ? 'all' : s))
    }
  }, [selectedCompanyId])

  const unassignedTeam = Array.isArray(team)
    ? team.filter((m: any) => !String(m?.companyId || '').trim())
    : []
  const unassignedProjects = Array.isArray(projects)
    ? projects.filter((p: any) => !String(p?.companyId || '').trim())
    : []
  const unassignedReferences = Array.isArray(references)
    ? references.filter((r: any) => !String(r?.companyId || '').trim())
    : []
  const teamForCompany = Array.isArray(team)
    ? team.filter(
        (m: any) =>
          String(m?.companyId || '') === String(selectedCompanyId || ''),
      )
    : []
  const projectsForCompany = Array.isArray(projects)
    ? projects.filter(
        (p: any) =>
          String(p?.companyId || '') === String(selectedCompanyId || ''),
      )
    : []
  const referencesForCompany = Array.isArray(references)
    ? references.filter(
        (r: any) =>
          String(r?.companyId || '') === String(selectedCompanyId || ''),
      )
    : []

  const normalize = (v: any) =>
    String(v || '')
      .toLowerCase()
      .trim()

  const projectTypeOptions = useMemo(() => {
    const set = new Set<string>()
    ;(Array.isArray(projects) ? projects : []).forEach((p: any) => {
      const v = String(p?.projectType || '').trim()
      if (v) set.add(v)
    })
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [projects])

  const industryOptions = useMemo(() => {
    const set = new Set<string>()
    ;(Array.isArray(projects) ? projects : []).forEach((p: any) => {
      const v = String(p?.industry || '').trim()
      if (v) set.add(v)
    })
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [projects])

  const referenceProjectTypeOptions = useMemo(() => {
    const set = new Set<string>()
    ;(Array.isArray(references) ? references : []).forEach((r: any) => {
      const v = String(r?.projectType || '').trim()
      if (v) set.add(v)
    })
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [references])

  const teamMissingEmailIds = useMemo(() => {
    return (Array.isArray(team) ? team : [])
      .filter((m: any) => !String(m?.email || '').trim())
      .map((m: any) => String(m?.memberId || m?._id || '').trim())
      .filter(Boolean)
  }, [team])

  const teamMissingCompanyIds = useMemo(() => {
    return (Array.isArray(team) ? team : [])
      .filter((m: any) => !String(m?.companyId || '').trim())
      .map((m: any) => String(m?.memberId || m?._id || '').trim())
      .filter(Boolean)
  }, [team])

  const projectMissingIndustryIds = useMemo(() => {
    return (Array.isArray(projects) ? projects : [])
      .filter((p: any) => !String(p?.industry || '').trim())
      .map((p: any) => String(p?._id || p?.projectId || '').trim())
      .filter(Boolean)
  }, [projects])

  const projectMissingProjectTypeIds = useMemo(() => {
    return (Array.isArray(projects) ? projects : [])
      .filter((p: any) => !String(p?.projectType || '').trim())
      .map((p: any) => String(p?._id || p?.projectId || '').trim())
      .filter(Boolean)
  }, [projects])

  const referenceMissingEmailIds = useMemo(() => {
    return (Array.isArray(references) ? references : [])
      .filter((r: any) => !String(r?.contactEmail || '').trim())
      .map((r: any) => String(r?._id || r?.referenceId || '').trim())
      .filter(Boolean)
  }, [references])

  const dupTeamEmailIds = useMemo(() => {
    const by = new Map<string, string[]>()
    ;(Array.isArray(team) ? team : []).forEach((m: any) => {
      const email = normalize(m?.email)
      const id = String(m?.memberId || m?._id || '').trim()
      if (!email || !id) return
      const arr = by.get(email) || []
      arr.push(id)
      by.set(email, arr)
    })
    const out: string[] = []
    Array.from(by.values()).forEach((ids) => {
      if (ids.length > 1) out.push(...ids)
    })
    return Array.from(new Set(out))
  }, [team])

  const dupProjectTitleClientIds = useMemo(() => {
    const by = new Map<string, string[]>()
    ;(Array.isArray(projects) ? projects : []).forEach((p: any) => {
      const key = `${normalize(p?.title)}|${normalize(p?.clientName)}`
      const id = String(p?._id || p?.projectId || '').trim()
      if (!normalize(p?.title) || !normalize(p?.clientName) || !id) return
      const arr = by.get(key) || []
      arr.push(id)
      by.set(key, arr)
    })
    const out: string[] = []
    Array.from(by.values()).forEach((ids) => {
      if (ids.length > 1) out.push(...ids)
    })
    return Array.from(new Set(out))
  }, [projects])

  const dupReferenceOrgEmailIds = useMemo(() => {
    const by = new Map<string, string[]>()
    ;(Array.isArray(references) ? references : []).forEach((r: any) => {
      const key = `${normalize(r?.organizationName)}|${normalize(
        r?.contactEmail,
      )}`
      const id = String(r?._id || r?.referenceId || '').trim()
      if (!normalize(r?.organizationName) || !normalize(r?.contactEmail) || !id)
        return
      const arr = by.get(key) || []
      arr.push(id)
      by.set(key, arr)
    })
    const out: string[] = []
    Array.from(by.values()).forEach((ids) => {
      if (ids.length > 1) out.push(...ids)
    })
    return Array.from(new Set(out))
  }, [references])

  const clearQualityFilter = () => setQualityFilter(null)

  const tabCounts = {
    company: Array.isArray(companies) ? companies.length : 0,
    team: selectedCompanyId ? teamForCompany.length : team.length,
    projects: selectedCompanyId ? projectsForCompany.length : projects.length,
    references: selectedCompanyId
      ? referencesForCompany.length
      : references.length,
  }

  const renderTab = (
    id: 'company' | 'team' | 'projects' | 'references',
    label: string,
    count: number,
  ) => {
    const isActive = activeTab === id
    return (
      <button
        key={id}
        type="button"
        onClick={() => setActiveTab(id)}
        className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
          isActive
            ? 'bg-primary-50 border-primary-200 text-primary-700'
            : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
        }`}
      >
        <span>{label}</span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            isActive
              ? 'bg-primary-100 text-primary-800'
              : 'bg-gray-100 text-gray-700'
          }`}
        >
          {count}
        </span>
      </button>
    )
  }

  const refreshCompanyById = async (companyId: string) => {
    if (!companyId) return
    try {
      const latestResp = await contentApi.getCompanyById(companyId)
      const latest = latestResp.data
      setCompanies((prev) =>
        (Array.isArray(prev) ? prev : []).map((c: any) =>
          c.companyId === companyId ? latest : c,
        ),
      )
      if (selectedCompany?.companyId === companyId) {
        setSelectedCompany(latest)
      }
    } catch (e) {
      // ignore
    }
  }

  const handleEditCompany = () => {
    setCompanyForm({
      ...selectedCompany,
      companyName: selectedCompany?.name || selectedCompany?.companyName || '',
    })
    setEditingCompany(true)
  }

  const handleSaveCompany = async () => {
    try {
      const payload: any = {
        ...selectedCompany,
        name: companyForm.companyName ?? selectedCompany?.name,
        description: companyForm.description ?? selectedCompany?.description,
        founded: companyForm.founded ?? selectedCompany?.founded,
        location: companyForm.location ?? selectedCompany?.location,
        website: companyForm.website ?? selectedCompany?.website,
        email: companyForm.email ?? selectedCompany?.email,
        phone: companyForm.phone ?? selectedCompany?.phone,
        coreCapabilities:
          companyForm.coreCapabilities ?? selectedCompany?.coreCapabilities,
        certifications:
          companyForm.certifications ?? selectedCompany?.certifications,
        industryFocus:
          companyForm.industryFocus ?? selectedCompany?.industryFocus,
        missionStatement:
          companyForm.missionStatement ?? selectedCompany?.missionStatement,
        visionStatement:
          companyForm.visionStatement ?? selectedCompany?.visionStatement,
        values: companyForm.values ?? selectedCompany?.values,
        statistics: companyForm.statistics ?? selectedCompany?.statistics,
        socialMedia: companyForm.socialMedia ?? selectedCompany?.socialMedia,
      }
      const { data } = await contentApi.updateCompanyById(
        selectedCompany.companyId,
        payload,
      )

      // Handle response - could be just a company object or an object with affectedCompanies
      const updatedCompany = (data as any).company || data
      const affectedCompanies = (data as any).affectedCompanies || [
        updatedCompany,
      ]

      // Update all affected companies in the state
      setCompanies(
        companies.map((c) => {
          const updated = affectedCompanies.find(
            (ac: any) => ac.companyId === c.companyId,
          )
          return updated || c
        }),
      )

      setSelectedCompany(updatedCompany)
      setEditingCompany(false)
      toast.success('Company information updated successfully!')
    } catch (error) {
      console.error('Error updating company:', error)
      const status = (error as any)?.response?.status
      if (status === 409 && selectedCompany?.companyId) {
        toast.error('This company was changed elsewhere. Reloading latest…')
        try {
          const latestResp = await contentApi.getCompanyById(
            selectedCompany.companyId,
          )
          const latest = latestResp.data
          setCompanies(
            companies.map((c) =>
              c.companyId === selectedCompany.companyId ? latest : c,
            ),
          )
          setSelectedCompany(latest)
          setCompanyForm({
            ...latest,
            companyName: latest?.name || latest?.companyName || '',
          })
        } catch (_e) {
          // ignore
        }
        return
      }
      toast.error('Failed to update company information')
    }
  }

  const handleCancelCompanyEdit = () => {
    setCompanyForm({})
    setEditingCompany(false)
  }

  const handleAddCompany = async () => {
    try {
      const { data } = await contentApi.createCompany(companyForm)
      setCompanies([...companies, data])
      setSelectedCompany(data)
      setCompanyForm({})
      setShowAddCompany(false)
      toast.success('Company added successfully!')
    } catch (error) {
      console.error('Error adding company:', error)
      toast.error('Failed to add company')
    }
  }

  const handleDeleteCompany = (companyToDelete: any) => {
    setDeleteTarget({ type: 'company', item: companyToDelete })
    setShowDeleteModal(true)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return

    setIsDeleting(true)
    try {
      switch (deleteTarget.type) {
        case 'company':
          await contentApi.deleteCompany(deleteTarget.item.companyId)
          setCompanies(
            companies.filter(
              (c) => c.companyId !== deleteTarget.item.companyId,
            ),
          )
          if (selectedCompany?.companyId === deleteTarget.item.companyId) {
            setSelectedCompany(
              companies.length > 1
                ? companies.find(
                    (c) => c.companyId !== deleteTarget.item.companyId,
                  )
                : null,
            )
          }
          toast.success('Company deleted successfully!')
          break
        case 'reference':
          await contentApi.deleteReference(deleteTarget.item._id)
          setReferences(
            references.filter((r) => r._id !== deleteTarget.item._id),
          )
          if (deleteTarget.item?.companyId) {
            await refreshCompanyById(String(deleteTarget.item.companyId))
          }
          toast.success('Reference deleted successfully!')
          break
        case 'member':
          await contentApi.deleteTeamMember(deleteTarget.item.memberId)
          setTeam(
            team.filter((m: any) => m.memberId !== deleteTarget.item.memberId),
          )
          toast.success('Team member deleted successfully!')
          break
        case 'project':
          await contentApi.deleteProject(deleteTarget.item._id)
          setProjects(projects.filter((p) => p._id !== deleteTarget.item._id))
          if (deleteTarget.item?.companyId) {
            await refreshCompanyById(String(deleteTarget.item.companyId))
          }
          toast.success('Project deleted successfully!')
          break
      }

      setShowDeleteModal(false)
      setDeleteTarget(null)
    } catch (error) {
      console.error('Error deleting:', error)
      toast.error(`Failed to delete ${deleteTarget.type}`)
    } finally {
      setIsDeleting(false)
    }
  }

  const cancelDelete = () => {
    setShowDeleteModal(false)
    setDeleteTarget(null)
    setIsDeleting(false)
  }

  const handleEditMember = (member: any) => {
    setMemberForm({ ...member })
    setEditingMember(member)
    setSelectedMember(member)
  }

  const handleSaveMember = async () => {
    try {
      const memberId = editingMember?.memberId || memberForm.memberId
      if (!memberId) throw new Error('Missing memberId')
      const { data } = await contentApi.updateTeamMember(memberId, memberForm)
      setTeam(team.map((m) => (m.memberId === memberId ? data : m)))
      setSelectedMember(data)
      setEditingMember(null)
      toast.success('Team member updated successfully!')
    } catch (error) {
      console.error('Error updating member:', error)
      const status = (error as any)?.response?.status
      const memberId = editingMember?.memberId || memberForm.memberId
      if (status === 409 && memberId) {
        toast.error('This member was changed elsewhere. Reloading latest…')
        try {
          const latestResp = await contentApi.getTeamMember(memberId)
          const latest = latestResp.data
          setTeam(team.map((m) => (m.memberId === memberId ? latest : m)))
          setSelectedMember(latest)
          setMemberForm({ ...latest })
        } catch (_e) {
          // ignore
        }
        return
      }
      toast.error('Failed to update team member')
    }
  }

  const assignMemberToSelectedCompany = async (member: any) => {
    if (!selectedCompanyId) return
    try {
      const memberId = member?.memberId
      if (!memberId) return
      const payload = { ...member, companyId: selectedCompanyId }
      const { data } = await contentApi.updateTeamMember(memberId, payload)
      setTeam(team.map((m) => (m.memberId === memberId ? data : m)))
      toast.success('Assigned team member to selected company')
    } catch (e) {
      console.error('Error assigning member to company:', e)
      toast.error('Failed to assign team member')
    }
  }

  const openAddMemberModal = () => {
    // Reset the form to empty state
    setMemberForm({
      nameWithCredentials: '',
      position: '',
      email: '',
      companyId: selectedCompanyId,
      biography: '',
      headshotUrl: '',
      headshotS3Key: null,
      headshotS3Uri: null,
      bioProfiles: [],
    })
    setShowAddMember(true)
  }

  const handleAddMember = async () => {
    try {
      const { data } = await contentApi.createTeamMember(memberForm)
      setTeam([...team, data])
      setMemberForm({
        nameWithCredentials: '',
        position: '',
        email: '',
        companyId: null,
        biography: '',
        headshotUrl: '',
        headshotS3Key: null,
        headshotS3Uri: null,
        bioProfiles: [],
      })
      setShowAddMember(false)
      toast.success('Team member added successfully!')
    } catch (error) {
      console.error('Error adding member:', error)
      toast.error('Failed to add team member')
    }
  }

  const handleDeleteMember = (memberToDelete: any) => {
    setDeleteTarget({ type: 'member', item: memberToDelete })
    setShowDeleteModal(true)
  }

  const addArrayItem = (field: string, setState: any, state: any) => {
    setState({
      ...state,
      [field]: [...state[field], ''],
    })
  }

  const updateArrayItem = (
    field: string,
    index: number,
    value: string,
    setState: any,
    state: any,
  ) => {
    const updated = [...state[field]]
    updated[index] = value
    setState({
      ...state,
      [field]: updated,
    })
  }

  const removeArrayItem = (
    field: string,
    index: number,
    setState: any,
    state: any,
  ) => {
    setState({
      ...state,
      [field]: state[field].filter((_: any, i: number) => i !== index),
    })
  }

  // Project handlers
  const handleAddProject = async () => {
    try {
      const payload = {
        ...projectForm,
        companyId: projectForm.companyId ?? selectedCompanyId,
      }
      const { data } = await contentApi.createProject(payload)
      setProjects([...projects, data])
      setProjectForm({
        title: '',
        clientName: '',
        description: '',
        industry: '',
        projectType: '',
        duration: '',
        budget: '',
        keyOutcomes: [''],
        technologies: [''],
        challenges: [''],
        solutions: [''],
        files: [],
        companyId: selectedCompanyId,
      })
      setShowAddProject(false)
      if (payload.companyId) await refreshCompanyById(String(payload.companyId))
      toast.success('Project added successfully!')
    } catch (error) {
      console.error('Error adding project:', error)
      toast.error('Failed to add project')
    }
  }

  const handleEditProject = (project: any) => {
    setProjectForm({ ...project })
    setEditingProject(project)
    setSelectedProject(project)
  }

  const handleSaveProject = async () => {
    try {
      const id = editingProject?._id || projectForm?._id || editingProject?.id
      if (!id) throw new Error('Missing project id')
      const payload = {
        ...projectForm,
        companyId: projectForm.companyId ?? selectedCompanyId,
      }
      const { data } = await contentApi.updateProject(id, payload)
      setProjects(projects.map((p) => (p._id === id ? data : p)))
      setSelectedProject(data)
      setEditingProject(null)
      if (payload.companyId) await refreshCompanyById(String(payload.companyId))
      toast.success('Project updated successfully!')
    } catch (error) {
      console.error('Error updating project:', error)
      const status = (error as any)?.response?.status
      const id = editingProject?._id || projectForm?._id || editingProject?.id
      if (status === 409 && id) {
        toast.error('This project was changed elsewhere. Reloading latest…')
        try {
          const latestResp = await contentApi.getProjectById(id)
          const latest = latestResp.data
          setProjects(projects.map((p) => (p._id === id ? latest : p)))
          setSelectedProject(latest)
          setProjectForm({ ...latest })
        } catch (_e) {
          // ignore
        }
        return
      }
      toast.error('Failed to update project')
    }
  }

  const assignProjectToSelectedCompany = async (project: any) => {
    if (!selectedCompanyId) return
    try {
      const id = project?._id || project?.projectId
      if (!id) return
      const payload = { ...project, companyId: selectedCompanyId }
      const { data } = await contentApi.updateProject(id, payload)
      setProjects(projects.map((p) => (p._id === id ? data : p)))
      setSelectedProject(data)
      await refreshCompanyById(String(selectedCompanyId))
      toast.success('Assigned project to selected company')
    } catch (e) {
      console.error('Error assigning project to company:', e)
      toast.error('Failed to assign project')
    }
  }

  const handleDeleteProject = (projectToDelete: any) => {
    setDeleteTarget({ type: 'project', item: projectToDelete })
    setShowDeleteModal(true)
  }

  // Reference handlers
  const handleAddReference = async () => {
    try {
      const payload = {
        ...referenceForm,
        companyId: referenceForm.companyId ?? selectedCompanyId,
      }
      const { data } = await contentApi.createReference(payload)
      setReferences([...references, data])
      setReferenceForm({
        organizationName: '',
        timePeriod: '',
        contactName: '',
        contactTitle: '',
        additionalTitle: '',
        contactEmail: '',
        contactPhone: '',
        scopeOfWork: '',
        isPublic: true,
        companyId: selectedCompanyId,
      })
      setShowAddReference(false)
      if (payload.companyId) await refreshCompanyById(String(payload.companyId))
      toast.success('Reference added successfully!')
    } catch (error) {
      console.error('Error adding reference:', error)
      toast.error('Failed to add reference')
    }
  }

  const handleEditReference = (reference: any) => {
    setReferenceForm({ ...reference })
    setEditingReference(reference)
    setSelectedReference(reference)
  }

  const handleViewReference = (reference: any) => {
    setSelectedReference(reference)
    setShowViewReference(true)
  }

  const handleSaveReference = async () => {
    try {
      const id =
        editingReference?._id || referenceForm?._id || editingReference?.id
      if (!id) throw new Error('Missing reference id')
      const payload = {
        ...referenceForm,
        companyId: referenceForm.companyId ?? selectedCompanyId,
      }
      const { data } = await contentApi.updateReference(id, payload)
      setReferences(references.map((r) => (r._id === id ? data : r)))
      setSelectedReference(data)
      setEditingReference(null)
      if (payload.companyId) await refreshCompanyById(String(payload.companyId))
      toast.success('Reference updated successfully!')
    } catch (error) {
      console.error('Error updating reference:', error)
      const status = (error as any)?.response?.status
      const id =
        editingReference?._id || referenceForm?._id || editingReference?.id
      if (status === 409 && id) {
        toast.error('This reference was changed elsewhere. Reloading latest…')
        try {
          const latestResp = await contentApi.getReferenceById(id)
          const latest = latestResp.data
          setReferences(references.map((r) => (r._id === id ? latest : r)))
          setSelectedReference(latest)
          setReferenceForm({ ...latest })
        } catch (_e) {
          // ignore
        }
        return
      }
      toast.error('Failed to update reference')
    }
  }

  const assignReferenceToSelectedCompany = async (reference: any) => {
    if (!selectedCompanyId) return
    try {
      const id = reference?._id || reference?.referenceId
      if (!id) return
      const payload = { ...reference, companyId: selectedCompanyId }
      const { data } = await contentApi.updateReference(id, payload)
      setReferences(references.map((r) => (r._id === id ? data : r)))
      setSelectedReference(data)
      await refreshCompanyById(String(selectedCompanyId))
      toast.success('Assigned reference to selected company')
    } catch (e) {
      console.error('Error assigning reference to company:', e)
      toast.error('Failed to assign reference')
    }
  }

  const handleDeleteReference = (referenceToDelete: any) => {
    setDeleteTarget({ type: 'reference', item: referenceToDelete })
    setShowDeleteModal(true)
  }

  async function runWithConcurrency<T>(
    items: T[],
    concurrency: number,
    worker: (item: T) => Promise<void>,
  ) {
    const limit = Math.max(1, Math.min(10, Number(concurrency) || 5))
    const queue = [...items]
    const runners = Array.from({ length: Math.min(limit, queue.length) }).map(
      async () => {
        while (queue.length) {
          const next = queue.shift()
          if (typeof next === 'undefined') break
          await worker(next)
        }
      },
    )
    await Promise.all(runners)
  }

  type BulkResult = { total: number; done: number; failed: number }

  const assignManyMembersToSelectedCompany = async (
    members: any[],
    opts?: { onProgress?: (r: BulkResult) => void; suppressToast?: boolean },
  ): Promise<BulkResult> => {
    if (!selectedCompanyId) {
      return { total: 0, done: 0, failed: 0 }
    }
    const list = Array.isArray(members) ? members : []
    if (list.length === 0) {
      return { total: 0, done: 0, failed: 0 }
    }
    const res: BulkResult = { total: list.length, done: 0, failed: 0 }
    try {
      await runWithConcurrency(list, 5, async (m) => {
        try {
          const memberId = m?.memberId
          if (!memberId) {
            res.failed += 1
            return
          }
          const payload = { ...m, companyId: selectedCompanyId }
          const { data } = await contentApi.updateTeamMember(memberId, payload)
          setTeam((prev) =>
            (Array.isArray(prev) ? prev : []).map((x: any) =>
              x.memberId === memberId ? data : x,
            ),
          )
          res.done += 1
        } catch (_e) {
          res.failed += 1
        } finally {
          opts?.onProgress?.({ ...res })
        }
      })
      if (!opts?.suppressToast) {
        toast.success(`Assigned ${res.done} team members`)
      }
      return res
    } catch (e) {
      console.error('Bulk assign members failed:', e)
      if (!opts?.suppressToast) {
        toast.error('Failed to bulk-assign team members')
      }
      return res
    }
  }

  const assignManyProjectsToSelectedCompany = async (
    items: any[],
    opts?: { onProgress?: (r: BulkResult) => void; suppressToast?: boolean },
  ): Promise<BulkResult> => {
    if (!selectedCompanyId) {
      return { total: 0, done: 0, failed: 0 }
    }
    const list = Array.isArray(items) ? items : []
    if (list.length === 0) {
      return { total: 0, done: 0, failed: 0 }
    }
    const res: BulkResult = { total: list.length, done: 0, failed: 0 }
    try {
      await runWithConcurrency(list, 5, async (p) => {
        try {
          const id = p?._id || p?.projectId
          if (!id) {
            res.failed += 1
            return
          }
          const payload = { ...p, companyId: selectedCompanyId }
          const { data } = await contentApi.updateProject(id, payload)
          setProjects((prev) =>
            (Array.isArray(prev) ? prev : []).map((x: any) =>
              x._id === id ? data : x,
            ),
          )
          res.done += 1
        } catch (_e) {
          res.failed += 1
        } finally {
          opts?.onProgress?.({ ...res })
        }
      })
      await refreshCompanyById(String(selectedCompanyId))
      if (!opts?.suppressToast) {
        toast.success(`Assigned ${res.done} projects`)
      }
      return res
    } catch (e) {
      console.error('Bulk assign projects failed:', e)
      if (!opts?.suppressToast) {
        toast.error('Failed to bulk-assign projects')
      }
      return res
    }
  }

  const assignManyReferencesToSelectedCompany = async (
    items: any[],
    opts?: { onProgress?: (r: BulkResult) => void; suppressToast?: boolean },
  ): Promise<BulkResult> => {
    if (!selectedCompanyId) {
      return { total: 0, done: 0, failed: 0 }
    }
    const list = Array.isArray(items) ? items : []
    if (list.length === 0) {
      return { total: 0, done: 0, failed: 0 }
    }
    const res: BulkResult = { total: list.length, done: 0, failed: 0 }
    try {
      await runWithConcurrency(list, 5, async (r) => {
        try {
          const id = r?._id || r?.referenceId
          if (!id) {
            res.failed += 1
            return
          }
          const payload = { ...r, companyId: selectedCompanyId }
          const { data } = await contentApi.updateReference(id, payload)
          setReferences((prev) =>
            (Array.isArray(prev) ? prev : []).map((x: any) =>
              x._id === id ? data : x,
            ),
          )
          res.done += 1
        } catch (_e) {
          res.failed += 1
        } finally {
          opts?.onProgress?.({ ...res })
        }
      })
      await refreshCompanyById(String(selectedCompanyId))
      if (!opts?.suppressToast) {
        toast.success(`Assigned ${res.done} references`)
      }
      return res
    } catch (e) {
      console.error('Bulk assign references failed:', e)
      if (!opts?.suppressToast) {
        toast.error('Failed to bulk-assign references')
      }
      return res
    }
  }

  const [inboxBulk, setInboxBulk] = useState<{
    type: 'team' | 'projects' | 'references' | 'all' | null
    phase?: 'team' | 'projects' | 'references' | null
    running: boolean
    total: number
    done: number
    failed: number
  }>({ type: null, running: false, total: 0, done: 0, failed: 0 })
  const [showRemaining, setShowRemaining] = useState(false)

  const runAssignEverything = async () => {
    if (!selectedCompanyId) return
    const total =
      (unassignedTeam?.length || 0) +
      (unassignedProjects?.length || 0) +
      (unassignedReferences?.length || 0)
    if (!total) return

    if (
      !confirm(
        `Assign all unassigned items to the selected company?\n\nTeam: ${unassignedTeam.length}\nProjects: ${unassignedProjects.length}\nReferences: ${unassignedReferences.length}`,
      )
    )
      return

    setInboxBulk({
      type: 'all',
      phase: 'team',
      running: true,
      total,
      done: 0,
      failed: 0,
    })

    let baseDone = 0
    let baseFailed = 0

    const runStep = async (
      phase: 'team' | 'projects' | 'references',
      fn: (items: any[], opts?: any) => Promise<BulkResult>,
      items: any[],
    ) => {
      if (!Array.isArray(items) || items.length === 0) return
      setInboxBulk((prev) => ({ ...prev, type: 'all', phase }))
      const r = await fn(items, {
        suppressToast: true,
        onProgress: (p: BulkResult) =>
          setInboxBulk((prev) => ({
            ...prev,
            type: 'all',
            phase,
            running: true,
            total,
            done: baseDone + p.done,
            failed: baseFailed + p.failed,
          })),
      })
      baseDone += r.done
      baseFailed += r.failed
      setInboxBulk((prev) => ({
        ...prev,
        type: 'all',
        phase,
        running: true,
        total,
        done: baseDone,
        failed: baseFailed,
      }))
    }

    try {
      await runStep('team', assignManyMembersToSelectedCompany, unassignedTeam)
      await runStep(
        'projects',
        assignManyProjectsToSelectedCompany,
        unassignedProjects,
      )
      await runStep(
        'references',
        assignManyReferencesToSelectedCompany,
        unassignedReferences,
      )

      setInboxBulk((prev) => ({ ...prev, running: false }))
      if (baseFailed) setShowRemaining(true)
      toast.success(
        `Assigned ${baseDone}/${total} items${
          baseFailed ? ` (failed: ${baseFailed})` : ''
        }`,
      )
    } catch (e) {
      console.error('Assign everything failed:', e)
      setInboxBulk((prev) => ({ ...prev, running: false }))
      toast.error('Failed to assign all unassigned items')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        <div className="text-sm font-semibold text-gray-900">{loadError}</div>
        <div className="mt-1 text-sm text-gray-600">
          Please try again. If this persists, your session may have expired.
        </div>
        <div className="mt-4">
          <Button
            variant="secondary"
            onClick={async () => {
              setLoading(true)
              await loadContent()
            }}
          >
            Retry
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6">
        <PipelineContextBanner
          variant="secondary"
          title="Content Library powers proposals and templates."
          description="This is a structured library for team, projects, and references."
          rightSlot={
            <Button as={Link} href="/proposals" variant="ghost" size="sm">
              View Proposals
            </Button>
          }
        />
      </div>

      <StepsPanel
        title="How it fits into Pipeline"
        tone="blue"
        columns={3}
        steps={[
          {
            title: 'Curate',
            description: 'Keep team, projects, and references accurate.',
          },
          {
            title: 'Assign',
            description: 'Tie items to a company so they roll up correctly.',
          },
          {
            title: 'Generate',
            description:
              'Use this library when generating proposals and templates.',
          },
        ]}
      />
      <div className="mt-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
              Content Library
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Company is the top-level container. Team, projects, and references
              roll up to it.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-gray-600">
                Company
              </span>
              <select
                value={selectedCompanyId || ''}
                onChange={(e) => {
                  const id = e.target.value
                  const next =
                    (Array.isArray(companies) ? companies : []).find(
                      (c: any) =>
                        String(c?.companyId || '') === String(id || ''),
                    ) || null
                  setSelectedCompany(next)
                }}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
              >
                <option value="">None selected</option>
                {(Array.isArray(companies) ? companies : []).map((c: any) => (
                  <option key={c.companyId} value={c.companyId}>
                    {c.name || c.companyName || c.companyId}
                  </option>
                ))}
              </select>
            </div>
            <Button
              as={Link}
              href="/proposals"
              variant="secondary"
              size="sm"
              className="!rounded-lg"
            >
              View Proposals
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {renderTab('company', 'Company', tabCounts.company)}
          {renderTab('team', 'Team', tabCounts.team)}
          {renderTab('projects', 'Projects', tabCounts.projects)}
          {renderTab('references', 'References', tabCounts.references)}
        </div>

        {/* Global search + type filters */}
        <div className="mt-4 sticky top-4 z-10">
          <div className="rounded-xl border border-gray-200 bg-white/90 backdrop-blur p-3 shadow-sm">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex-1">
                <input
                  value={globalQuery}
                  onChange={(e) => setGlobalQuery(e.target.value)}
                  placeholder={
                    activeTab === 'team'
                      ? 'Search team (name, role, email, company)…'
                      : activeTab === 'projects'
                      ? 'Search projects (title, client, industry, duration)…'
                      : activeTab === 'references'
                      ? 'Search references (org, contact, email, time)…'
                      : 'Search…'
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {activeTab === 'projects' ? (
                  <>
                    <select
                      value={projectsProjectTypeFilter}
                      onChange={(e) =>
                        setProjectsProjectTypeFilter(e.target.value)
                      }
                      className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
                      title="Filter by project type"
                    >
                      <option value="">All project types</option>
                      {projectTypeOptions.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                    <select
                      value={projectsIndustryFilter}
                      onChange={(e) =>
                        setProjectsIndustryFilter(e.target.value)
                      }
                      className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
                      title="Filter by industry"
                    >
                      <option value="">All industries</option>
                      {industryOptions.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </>
                ) : null}

                {activeTab === 'references' ? (
                  <select
                    value={referencesProjectTypeFilter}
                    onChange={(e) =>
                      setReferencesProjectTypeFilter(e.target.value)
                    }
                    className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
                    title="Filter by project type"
                  >
                    <option value="">All project types</option>
                    {referenceProjectTypeOptions.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                ) : null}

                {globalQuery ||
                projectsProjectTypeFilter ||
                projectsIndustryFilter ||
                referencesProjectTypeFilter ? (
                  <button
                    type="button"
                    onClick={() => {
                      setGlobalQuery('')
                      setProjectsProjectTypeFilter('')
                      setProjectsIndustryFilter('')
                      setReferencesProjectTypeFilter('')
                      clearQualityFilter()
                    }}
                    className="px-3 py-2 text-sm rounded-lg border border-gray-300 bg-white hover:bg-gray-50"
                    title="Clear search and filters"
                  >
                    Clear
                  </button>
                ) : (
                  <div className="text-xs text-gray-500">Search + filters</div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Data health */}
        <div className="mt-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-gray-900">
                Data health
              </div>
              <div className="text-xs text-gray-500">
                Quick triage for unassigned items, missing fields, and likely
                duplicates.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowDataHealth((v) => !v)}
              className="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50"
            >
              {showDataHealth ? 'Hide' : 'Show'}
            </button>
          </div>

          {showDataHealth ? (
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                  Unassigned
                </div>
                <div className="mt-2 space-y-2 text-sm text-gray-800">
                  <div className="flex items-center justify-between">
                    <span>Team</span>
                    <button
                      type="button"
                      onClick={() => {
                        setQualityFilter(null)
                        setGlobalQuery('')
                        setActiveTab('team')
                        setTeamScope('unassigned')
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({unassignedTeam.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Projects</span>
                    <button
                      type="button"
                      onClick={() => {
                        setQualityFilter(null)
                        setGlobalQuery('')
                        setActiveTab('projects')
                        setProjectsScope('unassigned')
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({unassignedProjects.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>References</span>
                    <button
                      type="button"
                      onClick={() => {
                        setQualityFilter(null)
                        setGlobalQuery('')
                        setActiveTab('references')
                        setReferencesScope('unassigned')
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({unassignedReferences.length})
                    </button>
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                  Missing fields
                </div>
                <div className="mt-2 space-y-2 text-sm text-gray-800">
                  <div className="flex items-center justify-between">
                    <span>Team: missing email</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('team')
                        setTeamScope('all')
                        setQualityFilter({
                          tab: 'team',
                          label: 'Missing email',
                          ids: teamMissingEmailIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({teamMissingEmailIds.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Team: unassigned</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('team')
                        setTeamScope('all')
                        setQualityFilter({
                          tab: 'team',
                          label: 'Missing company assignment',
                          ids: teamMissingCompanyIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({teamMissingCompanyIds.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Projects: missing industry</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('projects')
                        setProjectsScope('all')
                        setQualityFilter({
                          tab: 'projects',
                          label: 'Missing industry',
                          ids: projectMissingIndustryIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({projectMissingIndustryIds.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Projects: missing project type</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('projects')
                        setProjectsScope('all')
                        setQualityFilter({
                          tab: 'projects',
                          label: 'Missing project type',
                          ids: projectMissingProjectTypeIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({projectMissingProjectTypeIds.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>References: missing email</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('references')
                        setReferencesScope('all')
                        setQualityFilter({
                          tab: 'references',
                          label: 'Missing contact email',
                          ids: referenceMissingEmailIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({referenceMissingEmailIds.length})
                    </button>
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                  Likely duplicates
                </div>
                <div className="mt-2 space-y-2 text-sm text-gray-800">
                  <div className="flex items-center justify-between">
                    <span>Team: duplicate email</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('team')
                        setTeamScope('all')
                        setQualityFilter({
                          tab: 'team',
                          label: 'Duplicate email',
                          ids: dupTeamEmailIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({dupTeamEmailIds.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Projects: duplicate title + client</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('projects')
                        setProjectsScope('all')
                        setQualityFilter({
                          tab: 'projects',
                          label: 'Duplicate title + client',
                          ids: dupProjectTitleClientIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({dupProjectTitleClientIds.length})
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>References: duplicate org + email</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGlobalQuery('')
                        setActiveTab('references')
                        setReferencesScope('all')
                        setQualityFilter({
                          tab: 'references',
                          label: 'Duplicate org + email',
                          ids: dupReferenceOrgEmailIds,
                        })
                      }}
                      className="px-2 py-1 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                    >
                      View ({dupReferenceOrgEmailIds.length})
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {qualityFilter ? (
            <div className="mt-4 rounded-lg border border-primary-200 bg-primary-50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm text-primary-800">
                  <span className="font-semibold">
                    Active data-health filter:
                  </span>{' '}
                  {qualityFilter.label} ({qualityFilter.ids.length})
                </div>
                <button
                  type="button"
                  onClick={clearQualityFilter}
                  className="px-2 py-1 text-xs rounded bg-white border border-primary-200 hover:bg-primary-100 text-primary-700"
                >
                  Clear filter
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Unassigned Inbox */}
      <div className="mt-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900">
              Unassigned inbox
            </div>
            <div className="text-xs text-gray-500">
              Items not tied to a company won’t inform capabilities until
              assigned.
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-600">
            <span className="rounded bg-gray-100 px-2 py-1">
              Team: {unassignedTeam.length}
            </span>
            <span className="rounded bg-gray-100 px-2 py-1">
              Projects: {unassignedProjects.length}
            </span>
            <span className="rounded bg-gray-100 px-2 py-1">
              References: {unassignedReferences.length}
            </span>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            className="!rounded-lg"
            onClick={() => {
              setTeamScope('unassigned')
              setProjectsScope('unassigned')
              setReferencesScope('unassigned')
              setActiveTab('team')
            }}
          >
            Review unassigned
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="!rounded-lg"
            onClick={() => {
              setTeamScope(selectedCompanyId ? 'company' : 'all')
              setProjectsScope(selectedCompanyId ? 'company' : 'all')
              setReferencesScope(selectedCompanyId ? 'company' : 'all')
            }}
          >
            Back to company-first view
          </Button>

          {unassignedTeam.length +
            unassignedProjects.length +
            unassignedReferences.length >
          0 ? (
            <Button
              variant="secondary"
              size="sm"
              className="!rounded-lg"
              onClick={() => setShowRemaining((v) => !v)}
            >
              {showRemaining ? 'Hide remaining' : 'Show remaining'}
            </Button>
          ) : null}
        </div>

        {selectedCompanyId ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={
                inboxBulk.running ||
                (!unassignedTeam.length &&
                  !unassignedProjects.length &&
                  !unassignedReferences.length)
              }
              onClick={runAssignEverything}
              className="px-3 py-2 text-sm rounded border border-primary-200 bg-primary-50 hover:bg-primary-100 text-primary-700 disabled:opacity-60"
              title="Assign all unassigned items to the selected company"
            >
              Assign everything
            </button>
            <button
              type="button"
              disabled={
                inboxBulk.running ||
                (!unassignedTeam.length &&
                  !unassignedProjects.length &&
                  !unassignedReferences.length)
              }
              onClick={async () => {
                // Retry remaining simply re-runs the full pass on whatever is still unassigned.
                await runAssignEverything()
              }}
              className="px-3 py-2 text-sm rounded border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-60"
              title="Retry assigning items that are still unassigned"
            >
              Retry remaining
            </button>
            <button
              type="button"
              disabled={
                inboxBulk.running ||
                !unassignedTeam.length ||
                !selectedCompanyId
              }
              onClick={async () => {
                if (
                  !confirm(
                    `Assign ${unassignedTeam.length} unassigned team member(s) to the selected company?`,
                  )
                )
                  return
                setInboxBulk({
                  type: 'team',
                  phase: null,
                  running: true,
                  total: unassignedTeam.length,
                  done: 0,
                  failed: 0,
                })
                const r = await assignManyMembersToSelectedCompany(
                  unassignedTeam,
                  {
                    suppressToast: true,
                    onProgress: (p) =>
                      setInboxBulk((prev) => ({ ...prev, ...p })),
                  },
                )
                setInboxBulk((prev) => ({ ...prev, running: false, ...r }))
                if (r.failed) setShowRemaining(true)
                toast.success(
                  `Assigned ${r.done}/${r.total} team members${
                    r.failed ? ` (failed: ${r.failed})` : ''
                  }`,
                )
              }}
              className="px-3 py-2 text-sm rounded border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-60"
            >
              Assign all team
            </button>
            <button
              type="button"
              disabled={
                inboxBulk.running ||
                !unassignedProjects.length ||
                !selectedCompanyId
              }
              onClick={async () => {
                if (
                  !confirm(
                    `Assign ${unassignedProjects.length} unassigned project(s) to the selected company?`,
                  )
                )
                  return
                setInboxBulk({
                  type: 'projects',
                  phase: null,
                  running: true,
                  total: unassignedProjects.length,
                  done: 0,
                  failed: 0,
                })
                const r = await assignManyProjectsToSelectedCompany(
                  unassignedProjects,
                  {
                    suppressToast: true,
                    onProgress: (p) =>
                      setInboxBulk((prev) => ({ ...prev, ...p })),
                  },
                )
                setInboxBulk((prev) => ({ ...prev, running: false, ...r }))
                if (r.failed) setShowRemaining(true)
                toast.success(
                  `Assigned ${r.done}/${r.total} projects${
                    r.failed ? ` (failed: ${r.failed})` : ''
                  }`,
                )
              }}
              className="px-3 py-2 text-sm rounded border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-60"
            >
              Assign all projects
            </button>
            <button
              type="button"
              disabled={
                inboxBulk.running ||
                !unassignedReferences.length ||
                !selectedCompanyId
              }
              onClick={async () => {
                if (
                  !confirm(
                    `Assign ${unassignedReferences.length} unassigned reference(s) to the selected company?`,
                  )
                )
                  return
                setInboxBulk({
                  type: 'references',
                  phase: null,
                  running: true,
                  total: unassignedReferences.length,
                  done: 0,
                  failed: 0,
                })
                const r = await assignManyReferencesToSelectedCompany(
                  unassignedReferences,
                  {
                    suppressToast: true,
                    onProgress: (p) =>
                      setInboxBulk((prev) => ({ ...prev, ...p })),
                  },
                )
                setInboxBulk((prev) => ({ ...prev, running: false, ...r }))
                if (r.failed) setShowRemaining(true)
                toast.success(
                  `Assigned ${r.done}/${r.total} references${
                    r.failed ? ` (failed: ${r.failed})` : ''
                  }`,
                )
              }}
              className="px-3 py-2 text-sm rounded border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-60"
            >
              Assign all references
            </button>
          </div>
        ) : null}

        {inboxBulk.running ? (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-gray-600">
              <div>
                Assigning{' '}
                {inboxBulk.type === 'all'
                  ? inboxBulk.phase
                    ? `all (${inboxBulk.phase})`
                    : 'all'
                  : inboxBulk.type}
                : {inboxBulk.done}/{inboxBulk.total}
                {inboxBulk.failed ? ` (failed: ${inboxBulk.failed})` : ''}
              </div>
              <div>
                {inboxBulk.total
                  ? Math.round((inboxBulk.done / inboxBulk.total) * 100)
                  : 0}
                %
              </div>
            </div>
            <div className="mt-2 h-2 w-full rounded bg-gray-100 overflow-hidden">
              <div
                className="h-2 bg-primary-600"
                style={{
                  width: `${
                    inboxBulk.total
                      ? Math.round((inboxBulk.done / inboxBulk.total) * 100)
                      : 0
                  }%`,
                }}
              />
            </div>
          </div>
        ) : null}

        {showRemaining &&
        (unassignedTeam.length ||
          unassignedProjects.length ||
          unassignedReferences.length) ? (
          <div className="mt-4 rounded border border-gray-200 bg-gray-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-semibold text-gray-900">
                Remaining unassigned (
                {unassignedTeam.length +
                  unassignedProjects.length +
                  unassignedReferences.length}
                )
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setTeamScope('unassigned')
                    setActiveTab('team')
                  }}
                  className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                >
                  Show Team list
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setProjectsScope('unassigned')
                    setActiveTab('projects')
                  }}
                  className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                >
                  Show Projects list
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setReferencesScope('unassigned')
                    setActiveTab('references')
                  }}
                  className="px-3 py-1.5 text-xs rounded bg-white border border-gray-200 hover:bg-gray-50"
                >
                  Show References list
                </button>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="rounded border border-gray-200 bg-white p-3">
                <div className="text-xs font-semibold text-gray-700">
                  Team (up to 10)
                </div>
                {(unassignedTeam || []).slice(0, 10).map((m: any) => (
                  <div
                    key={m.memberId}
                    className="mt-2 flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0">
                      <div className="text-sm text-gray-900 truncate">
                        {m.nameWithCredentials || m.name}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {m.position || m.title || ''}
                      </div>
                    </div>
                    {selectedCompanyId ? (
                      <button
                        type="button"
                        onClick={() => assignMemberToSelectedCompany(m)}
                        className="px-2 py-1 text-xs rounded bg-gray-100 hover:bg-gray-200"
                      >
                        Retry
                      </button>
                    ) : null}
                  </div>
                ))}
                {!unassignedTeam.length ? (
                  <div className="mt-2 text-xs text-gray-500">None</div>
                ) : null}
              </div>

              <div className="rounded border border-gray-200 bg-white p-3">
                <div className="text-xs font-semibold text-gray-700">
                  Projects (up to 10)
                </div>
                {(unassignedProjects || []).slice(0, 10).map((p: any) => (
                  <div
                    key={p._id}
                    className="mt-2 flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0">
                      <div className="text-sm text-gray-900 truncate">
                        {p.title}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {p.clientName || ''}
                      </div>
                    </div>
                    {selectedCompanyId ? (
                      <button
                        type="button"
                        onClick={() => assignProjectToSelectedCompany(p)}
                        className="px-2 py-1 text-xs rounded bg-gray-100 hover:bg-gray-200"
                      >
                        Retry
                      </button>
                    ) : null}
                  </div>
                ))}
                {!unassignedProjects.length ? (
                  <div className="mt-2 text-xs text-gray-500">None</div>
                ) : null}
              </div>

              <div className="rounded border border-gray-200 bg-white p-3">
                <div className="text-xs font-semibold text-gray-700">
                  References (up to 10)
                </div>
                {(unassignedReferences || []).slice(0, 10).map((r: any) => (
                  <div
                    key={r._id}
                    className="mt-2 flex items-center justify-between gap-2"
                  >
                    <div className="min-w-0">
                      <div className="text-sm text-gray-900 truncate">
                        {r.organizationName}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {r.contactName || ''}
                      </div>
                    </div>
                    {selectedCompanyId ? (
                      <button
                        type="button"
                        onClick={() => assignReferenceToSelectedCompany(r)}
                        className="px-2 py-1 text-xs rounded bg-gray-100 hover:bg-gray-200"
                      >
                        Retry
                      </button>
                    ) : null}
                  </div>
                ))}
                {!unassignedReferences.length ? (
                  <div className="mt-2 text-xs text-gray-500">None</div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        {!selectedCompanyId ? (
          <div className="mt-4 text-sm text-gray-600">
            Select a company above to enable one-click assignment.
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="rounded border border-gray-200 p-3">
              <div className="text-xs font-semibold text-gray-700">
                Team (top 3)
              </div>
              {(unassignedTeam || []).slice(0, 3).map((m: any) => (
                <div
                  key={m.memberId}
                  className="mt-2 flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm text-gray-900 truncate">
                      {m.nameWithCredentials || m.name}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {m.position || m.title || ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => assignMemberToSelectedCompany(m)}
                    className="px-2 py-1 text-xs rounded bg-gray-100 hover:bg-gray-200"
                  >
                    Assign
                  </button>
                </div>
              ))}
              {unassignedTeam.length === 0 ? (
                <div className="mt-2 text-xs text-gray-500">None</div>
              ) : null}
            </div>

            <div className="rounded border border-gray-200 p-3">
              <div className="text-xs font-semibold text-gray-700">
                Projects (top 3)
              </div>
              {(unassignedProjects || []).slice(0, 3).map((p: any) => (
                <div
                  key={p._id}
                  className="mt-2 flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm text-gray-900 truncate">
                      {p.title}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {p.clientName || ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => assignProjectToSelectedCompany(p)}
                    className="px-2 py-1 text-xs rounded bg-gray-100 hover:bg-gray-200"
                  >
                    Assign
                  </button>
                </div>
              ))}
              {unassignedProjects.length === 0 ? (
                <div className="mt-2 text-xs text-gray-500">None</div>
              ) : null}
            </div>

            <div className="rounded border border-gray-200 p-3">
              <div className="text-xs font-semibold text-gray-700">
                References (top 3)
              </div>
              {(unassignedReferences || []).slice(0, 3).map((r: any) => (
                <div
                  key={r._id}
                  className="mt-2 flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm text-gray-900 truncate">
                      {r.organizationName}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {r.contactName || ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => assignReferenceToSelectedCompany(r)}
                    className="px-2 py-1 text-xs rounded bg-gray-100 hover:bg-gray-200"
                  >
                    Assign
                  </button>
                </div>
              ))}
              {unassignedReferences.length === 0 ? (
                <div className="mt-2 text-xs text-gray-500">None</div>
              ) : null}
            </div>
          </div>
        )}
      </div>

      <div className="mt-8">
        <section
          id="section-company"
          className={`scroll-mt-24 ${activeTab === 'company' ? '' : 'hidden'}`}
        >
          <CompanySection
            ctx={{
              companies,
              setCompanies,
              selectedCompany,
              setSelectedCompany,
              projects: selectedCompanyId ? projectsForCompany : projects,
              references: selectedCompanyId ? referencesForCompany : references,
              setSelectedProject,
              setSelectedReference,
              editingCompany,
              companyForm,
              setCompanyForm,
              showAddCompany,
              setShowAddCompany,
              handleEditCompany,
              handleSaveCompany,
              handleCancelCompanyEdit,
              handleAddCompany,
              handleDeleteCompany,
            }}
          />
        </section>

        <section
          id="section-team"
          className={`scroll-mt-24 ${activeTab === 'team' ? '' : 'hidden'}`}
        >
          <div className="flex items-center gap-2 mb-4">
            <UserGroupIcon className="h-5 w-5 text-gray-400" />
            <h3 className="text-lg font-semibold text-gray-900">Team</h3>
          </div>
          <TeamSection
            ctx={{
              teamForCompany,
              unassignedTeam,
              allTeam: team,
              selectedCompanyId,
              searchQuery: globalQuery,
              setSearchQuery: setGlobalQuery,
              qualityFilterLabel:
                qualityFilter?.tab === 'team' ? qualityFilter.label : null,
              qualityFilterIds:
                qualityFilter?.tab === 'team' ? qualityFilter.ids : null,
              clearQualityFilter,
              assignMemberToSelectedCompany,
              scope: teamScope,
              setScope: setTeamScope,
              assignManyToSelectedCompany: assignManyMembersToSelectedCompany,
              team: selectedCompanyId ? teamForCompany : team,
              selectedMember,
              setSelectedMember,
              showAddMember,
              setShowAddMember,
              openAddMemberModal,
              memberForm,
              setMemberForm,
              addArrayItem,
              updateArrayItem,
              removeArrayItem,
              handleAddMember,
              handleEditMember,
              editingMember,
              setEditingMember,
              handleSaveMember,
              handleDeleteMember,
            }}
          />
        </section>

        <section
          id="section-projects"
          className={`scroll-mt-24 ${activeTab === 'projects' ? '' : 'hidden'}`}
        >
          <div className="flex items-center gap-2 mb-4">
            <FolderIcon className="h-5 w-5 text-gray-400" />
            <h3 className="text-lg font-semibold text-gray-900">
              Past Projects
            </h3>
          </div>
          <ProjectsSection
            ctx={{
              projectsForCompany,
              unassignedProjects,
              allProjects: projects,
              selectedCompanyId,
              searchQuery: globalQuery,
              setSearchQuery: setGlobalQuery,
              projectTypeFilter: projectsProjectTypeFilter,
              industryFilter: projectsIndustryFilter,
              qualityFilterLabel:
                qualityFilter?.tab === 'projects' ? qualityFilter.label : null,
              qualityFilterIds:
                qualityFilter?.tab === 'projects' ? qualityFilter.ids : null,
              clearQualityFilter,
              assignProjectToSelectedCompany,
              scope: projectsScope,
              setScope: setProjectsScope,
              assignManyToSelectedCompany: assignManyProjectsToSelectedCompany,
              projects: selectedCompanyId ? projectsForCompany : projects,
              selectedProject,
              setSelectedProject,
              showAddProject,
              setShowAddProject,
              projectForm,
              setProjectForm,
              addArrayItem,
              updateArrayItem,
              removeArrayItem,
              handleAddProject,
              handleEditProject,
              editingProject,
              setEditingProject,
              handleSaveProject,
              handleDeleteProject,
            }}
          />
        </section>

        <section
          id="section-references"
          className={`scroll-mt-24 ${
            activeTab === 'references' ? '' : 'hidden'
          }`}
        >
          <div className="flex items-center gap-2 mb-4">
            <ClipboardDocumentListIcon className="h-5 w-5 text-gray-400" />
            <h3 className="text-lg font-semibold text-gray-900">References</h3>
          </div>
          <ReferencesSection
            ctx={{
              referencesForCompany,
              unassignedReferences,
              allReferences: references,
              selectedCompanyId,
              searchQuery: globalQuery,
              setSearchQuery: setGlobalQuery,
              projectTypeFilter: referencesProjectTypeFilter,
              qualityFilterLabel:
                qualityFilter?.tab === 'references'
                  ? qualityFilter.label
                  : null,
              qualityFilterIds:
                qualityFilter?.tab === 'references' ? qualityFilter.ids : null,
              clearQualityFilter,
              assignReferenceToSelectedCompany,
              scope: referencesScope,
              setScope: setReferencesScope,
              assignManyToSelectedCompany:
                assignManyReferencesToSelectedCompany,
              references: selectedCompanyId ? referencesForCompany : references,
              selectedReference,
              setSelectedReference,
              handleViewReference,
              showAddReference,
              setShowAddReference,
              referenceForm,
              setReferenceForm,
              addArrayItem,
              updateArrayItem,
              removeArrayItem,
              handleAddReference,
              handleEditReference,
              editingReference,
              setEditingReference,
              handleSaveReference,
              handleDeleteReference,
            }}
          />
        </section>
      </div>

      <Modal
        isOpen={showViewReference}
        onClose={() => setShowViewReference(false)}
        title="Reference Details"
        size="md"
        footer={
          <button
            className="px-4 py-2 rounded-lg text-gray-700 bg-gray-100 hover:bg-gray-200"
            onClick={() => setShowViewReference(false)}
          >
            Close
          </button>
        }
      >
        {selectedReference ? (
          <div className="space-y-4">
            <div>
              <div className="text-sm font-semibold text-gray-900">
                {selectedReference.organizationName}
              </div>
              {selectedReference.timePeriod ? (
                <div className="text-xs text-gray-500">
                  {selectedReference.timePeriod}
                </div>
              ) : null}
            </div>

            <div className="space-y-1">
              <div className="text-xs font-semibold text-gray-700">Contact</div>
              <div className="text-sm text-gray-800">
                {selectedReference.contactName}
              </div>
              {selectedReference.contactTitle ? (
                <div className="text-xs text-gray-600">
                  {selectedReference.contactTitle}
                </div>
              ) : null}
              {selectedReference.additionalTitle ? (
                <div className="text-xs text-gray-500 italic">
                  {selectedReference.additionalTitle}
                </div>
              ) : null}
              {selectedReference.contactEmail ? (
                <div className="text-xs text-gray-600">
                  {selectedReference.contactEmail}
                </div>
              ) : null}
              {selectedReference.contactPhone ? (
                <div className="text-xs text-gray-600">
                  {selectedReference.contactPhone}
                </div>
              ) : null}
            </div>

            {selectedReference.scopeOfWork ? (
              <div className="space-y-1">
                <div className="text-xs font-semibold text-gray-700">
                  Scope of Work
                </div>
                <div className="text-sm text-gray-700 whitespace-pre-wrap">
                  {selectedReference.scopeOfWork}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="text-sm text-gray-600">No reference selected.</div>
        )}
      </Modal>

      <AddMemberModal
        open={showAddMember}
        memberForm={memberForm}
        setMemberForm={setMemberForm}
        addArrayItem={addArrayItem}
        updateArrayItem={updateArrayItem}
        removeArrayItem={removeArrayItem}
        onAdd={handleAddMember}
        onClose={() => {
          setShowAddMember(false)
          setMemberForm({
            nameWithCredentials: '',
            position: '',
            email: '',
            companyId: null,
            biography: '',
            headshotUrl: '',
            headshotS3Key: null,
            headshotS3Uri: null,
            bioProfiles: [],
          })
        }}
      />

      <EditMemberModal
        open={Boolean(editingMember)}
        memberForm={memberForm}
        setMemberForm={setMemberForm}
        onSave={handleSaveMember}
        onClose={() => setEditingMember(null)}
      />

      <AddProjectModal
        open={showAddProject}
        companies={companies}
        projectForm={{
          ...projectForm,
          companyId: projectForm.companyId ?? selectedCompanyId,
        }}
        setProjectForm={setProjectForm}
        addArrayItem={addArrayItem}
        updateArrayItem={updateArrayItem}
        removeArrayItem={removeArrayItem}
        onAdd={handleAddProject}
        onClose={() => setShowAddProject(false)}
      />

      <EditProjectModal
        open={Boolean(editingProject)}
        companies={companies}
        projectForm={projectForm}
        setProjectForm={setProjectForm}
        onSave={handleSaveProject}
        onClose={() => setEditingProject(null)}
      />

      <AddReferenceModal
        open={showAddReference}
        companies={companies}
        referenceForm={{
          ...referenceForm,
          companyId: referenceForm.companyId ?? selectedCompanyId,
        }}
        setReferenceForm={setReferenceForm}
        addArrayItem={addArrayItem}
        updateArrayItem={updateArrayItem}
        removeArrayItem={removeArrayItem}
        onAdd={handleAddReference}
        onClose={() => setShowAddReference(false)}
      />

      <EditReferenceModal
        open={Boolean(editingReference)}
        companies={companies}
        referenceForm={referenceForm}
        setReferenceForm={setReferenceForm}
        onSave={handleSaveReference}
        onClose={() => setEditingReference(null)}
      />

      <DeleteConfirmationModal
        isOpen={showDeleteModal}
        onClose={cancelDelete}
        onConfirm={confirmDelete}
        title={
          deleteTarget
            ? `Delete ${
                deleteTarget.type === 'company'
                  ? 'Company'
                  : deleteTarget.type === 'member'
                  ? 'Team Member'
                  : deleteTarget.type === 'project'
                  ? 'Project'
                  : 'Reference'
              }`
            : 'Delete Item'
        }
        message={
          deleteTarget
            ? `Are you sure you want to delete this ${deleteTarget.type}?`
            : 'Are you sure you want to delete this item?'
        }
        itemName={
          deleteTarget?.item?.name ||
          deleteTarget?.item?.organizationName ||
          deleteTarget?.item?.clientName ||
          deleteTarget?.item?.title
        }
        isDeleting={isDeleting}
      />
    </div>
  )
}

