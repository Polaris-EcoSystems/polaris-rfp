'use client'

import {
  BuildingOfficeIcon,
  ClipboardDocumentListIcon,
  FolderIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'
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
import DeleteConfirmationModal from '@/components/ui/DeleteConfirmationModal'
import Modal from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { contentApi } from '@/lib/api'

export default function ContentLibraryPage() {
  const toast = useToast()
  const [companies, setCompanies] = useState<any[]>([])
  const [selectedCompany, setSelectedCompany] = useState<any>(null)
  const [team, setTeam] = useState<any[]>([])
  const [selectedMember, setSelectedMember] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<
    'company' | 'team' | 'projects' | 'references'
  >('company')
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

  useEffect(() => {
    loadContent()
  }, [])

  const loadContent = async () => {
    try {
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
    } finally {
      setLoading(false)
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
          toast.success('Reference deleted successfully!')
          break
        case 'member':
          await contentApi.deleteTeamMember(deleteTarget.item.memberId)
          setTeam(
            team.filter((m: any) => m.memberId !== deleteTarget.item.memberId),
          )
          toast.success('Team member deleted successfully!')
          break
        // Add other cases for project deletion here
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

  const openAddMemberModal = () => {
    // Reset the form to empty state
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
      const { data } = await contentApi.createProject(projectForm)
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
      })
      setShowAddProject(false)
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
      const { data } = await contentApi.updateProject(id, projectForm)
      setProjects(projects.map((p) => (p._id === id ? data : p)))
      setSelectedProject(data)
      setEditingProject(null)
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

  const handleDeleteProject = (projectToDelete: any) => {
    setDeleteTarget({ type: 'project', item: projectToDelete })
    setShowDeleteModal(true)
  }

  // Reference handlers
  const handleAddReference = async () => {
    try {
      const { data } = await contentApi.createReference(referenceForm)
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
      })
      setShowAddReference(false)
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
      const { data } = await contentApi.updateReference(id, referenceForm)
      setReferences(references.map((r) => (r._id === id ? data : r)))
      setSelectedReference(data)
      setEditingReference(null)
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

  const handleDeleteReference = (referenceToDelete: any) => {
    setDeleteTarget({ type: 'reference', item: referenceToDelete })
    setShowDeleteModal(true)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  return (
    <div>
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Content Library
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Manage company information and team member profiles
          </p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="mt-8">
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('company')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'company'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <BuildingOfficeIcon className="h-4 w-4 mr-2 inline" />
              Company Information
            </button>
            <button
              onClick={() => setActiveTab('team')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'team'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <UserGroupIcon className="h-4 w-4 mr-2 inline" />
              Team Members ({team.length})
            </button>
            <button
              onClick={() => setActiveTab('projects')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'projects'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <FolderIcon className="h-4 w-4 mr-2 inline" />
              Past Projects ({projects.length})
            </button>
            <button
              onClick={() => setActiveTab('references')}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === 'references'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <ClipboardDocumentListIcon className="h-4 w-4 mr-2 inline" />
              References ({references.length})
            </button>
          </nav>
        </div>
      </div>

      <div className="mt-8">
        {activeTab === 'company' && (
          <CompanySection
            ctx={{
              companies,
              selectedCompany,
              setSelectedCompany,
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
        )}

        {activeTab === 'team' && (
          <TeamSection
            ctx={{
              team,
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
        )}

        {activeTab === 'projects' && (
          <ProjectsSection
            ctx={{
              projects,
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
        )}

        {activeTab === 'references' && (
          <ReferencesSection
            ctx={{
              references,
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
        )}
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
        projectForm={projectForm}
        setProjectForm={setProjectForm}
        addArrayItem={addArrayItem}
        updateArrayItem={updateArrayItem}
        removeArrayItem={removeArrayItem}
        onAdd={handleAddProject}
        onClose={() => setShowAddProject(false)}
      />

      <EditProjectModal
        open={Boolean(editingProject)}
        projectForm={projectForm}
        setProjectForm={setProjectForm}
        onSave={handleSaveProject}
        onClose={() => setEditingProject(null)}
      />

      <AddReferenceModal
        open={showAddReference}
        referenceForm={referenceForm}
        setReferenceForm={setReferenceForm}
        addArrayItem={addArrayItem}
        updateArrayItem={updateArrayItem}
        removeArrayItem={removeArrayItem}
        onAdd={handleAddReference}
        onClose={() => setShowAddReference(false)}
      />

      <EditReferenceModal
        open={Boolean(editingReference)}
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
          deleteTarget?.item?.clientName ||
          deleteTarget?.item?.title
        }
        isDeleting={isDeleting}
      />
    </div>
  )
}

