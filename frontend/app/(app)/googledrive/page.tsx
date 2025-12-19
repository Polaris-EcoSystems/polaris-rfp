'use client'

import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card, { CardBody, CardHeader } from '@/components/ui/Card'
import { LoadingScreen } from '@/components/ui/LoadingSpinner'
import PipelineContextBanner from '@/components/ui/PipelineContextBanner'
import StepsPanel from '@/components/ui/StepsPanel'
import api, { proxyUrl } from '@/lib/api'
import {
  ArrowDownTrayIcon,
  CheckCircleIcon,
  CloudArrowUpIcon,
  DocumentIcon,
  FolderIcon,
  ListBulletIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  ShareIcon,
  Squares2X2Icon,
  TrashIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useEffect, useState } from 'react'

interface DriveFile {
  id: string
  name: string
  mimeType: string
  size?: string
  createdTime: string
  modifiedTime: string
  webViewLink: string
  parents?: string[]
}

interface DriveStatus {
  initialized: boolean
  message: string
}

export default function GoogleDrivePage() {
  const [files, setFiles] = useState<DriveFile[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [status, setStatus] = useState<DriveStatus | null>(null)
  const [proposalsFolderId, setProposalsFolderId] = useState<string | null>(
    null,
  )
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [shareEmail, setShareEmail] = useState('')
  const [sharingFileId, setSharingFileId] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    checkStatus()
    loadFiles()
    setupProposalsFolder()
  }, [])

  const checkStatus = async () => {
    try {
      const response = await api.get(proxyUrl('/googledrive/status'))
      setStatus(response.data)
    } catch (error) {
      console.error('Failed to check Google Drive status:', error)
      setStatus({ initialized: false, message: 'Failed to check status' })
    }
  }

  const setupProposalsFolder = async () => {
    try {
      const response = await api.post(proxyUrl('/googledrive/folder/proposals'))
      setProposalsFolderId(response.data.folderId)
    } catch (error) {
      console.error('Failed to setup proposals folder:', error)
    }
  }

  const loadFiles = async () => {
    setLoading(true)
    try {
      const response = await api.get(proxyUrl('/googledrive/files'))
      setFiles(response.data.files)
    } catch (error) {
      console.error('Failed to load files:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      setSelectedFile(file)
    }
  }

  const uploadFile = async () => {
    if (!selectedFile) return

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      if (proposalsFolderId) {
        formData.append('parentFolderId', proposalsFolderId)
      }

      await api.post(proxyUrl('/googledrive/upload'), formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      setSelectedFile(null)
      // Reset file input
      const fileInput = document.getElementById(
        'file-upload',
      ) as HTMLInputElement
      if (fileInput) fileInput.value = ''

      await loadFiles()
    } catch (error) {
      console.error('Failed to upload file:', error)
      alert('Failed to upload file. Please try again.')
    } finally {
      setUploading(false)
    }
  }

  const deleteFile = async (fileId: string) => {
    if (!confirm('Are you sure you want to delete this file?')) return

    try {
      await api.delete(proxyUrl(`/googledrive/files/${fileId}`))
      await loadFiles()
    } catch (error) {
      console.error('Failed to delete file:', error)
      alert('Failed to delete file. Please try again.')
    }
  }

  const downloadFile = async (fileId: string, fileName: string) => {
    try {
      const response = await api.get(
        proxyUrl(`/googledrive/download/${fileId}?fileName=${fileName}`),
        {
          responseType: 'blob',
        },
      )

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', fileName)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to download file:', error)
      alert('Failed to download file. Please try again.')
    }
  }

  const shareFile = async (fileId: string) => {
    try {
      await api.post(proxyUrl(`/googledrive/files/${fileId}/share`), {
        email: shareEmail || undefined,
        role: 'reader',
      })

      setShareEmail('')
      setSharingFileId(null)
      alert('File shared successfully!')
    } catch (error) {
      console.error('Failed to share file:', error)
      alert('Failed to share file. Please try again.')
    }
  }

  const formatFileSize = (sizeStr?: string) => {
    if (!sizeStr) return 'Unknown'
    const size = parseInt(sizeStr)
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    if (size < 1024 * 1024 * 1024)
      return `${(size / (1024 * 1024)).toFixed(1)} MB`
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const getFileIcon = (mimeType: string) => {
    if (mimeType.includes('folder')) return FolderIcon
    if (mimeType.includes('image')) return DocumentIcon
    return DocumentIcon
  }

  const filteredFiles = files.filter((file) =>
    file.name.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  if (!status) {
    return <LoadingScreen message="Initializing Google Drive..." />
  }

  return (
    <div className="space-y-8">
      <PipelineContextBanner
        variant="tool"
        title="This is a supporting mini-workflow."
        description="Use it to upload/share proposal artifacts, then continue work in Pipeline."
        rightSlot={
          <Button as={Link} href="/proposals" variant="ghost" size="sm">
            View Proposals
          </Button>
        }
      />

      <StepsPanel
        title="Quick flow"
        tone="slate"
        columns={3}
        steps={[
          {
            title: 'Verify setup',
            description: 'Confirm Drive integration is initialized.',
          },
          {
            title: 'Upload + share',
            description: 'Store proposal artifacts and share with reviewers.',
          },
          {
            title: 'Continue in Pipeline',
            description:
              'Return to Pipeline to advance the RFP/proposal stage.',
          },
        ]}
      />
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
        <div className="space-y-2">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
            Google Drive
          </h1>
          <p className="text-lg text-gray-600">
            Upload proposals and manage files seamlessly
          </p>
        </div>

        <div className="flex items-center space-x-4">
          <Badge
            variant={status.initialized ? 'success' : 'danger'}
            size="md"
            pulse={!status.initialized}
          >
            <div className="flex items-center space-x-2">
              {status.initialized ? (
                <CheckCircleIcon className="h-4 w-4" />
              ) : (
                <XCircleIcon className="h-4 w-4" />
              )}
              <span>{status.initialized ? 'Connected' : 'Disconnected'}</span>
            </div>
          </Badge>
        </div>
      </div>

      {/* Status Card */}
      {!status.initialized && (
        <Card className="border-red-200 bg-gradient-to-r from-red-50 to-rose-50">
          <CardBody>
            <div className="flex items-center space-x-3">
              <div className="flex-shrink-0">
                <XCircleIcon className="h-8 w-8 text-red-500" />
              </div>
              <div className="space-y-2">
                <h3 className="text-lg font-semibold text-red-900">
                  Google Drive Not Connected
                </h3>
                <p className="text-red-700">{status.message}</p>
                <p className="text-sm text-red-600">
                  Please configure Google Drive credentials in your environment
                  variables to enable file management.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Upload Section */}
      {status.initialized && (
        <Card gradient hover>
          <CardHeader>
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-lg">
                <CloudArrowUpIcon className="h-6 w-6 text-white" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900">
                  Upload Files
                </h2>
                <p className="text-sm text-gray-600">
                  Add documents to your Google Drive
                </p>
              </div>
            </div>
          </CardHeader>
          <CardBody>
            <div className="space-y-4">
              <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 hover:border-blue-400 hover:bg-blue-50/30 transition-all duration-300">
                <div className="text-center">
                  <CloudArrowUpIcon className="mx-auto h-12 w-12 text-gray-400 mb-4" />
                  <input
                    id="file-upload"
                    type="file"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                  <label
                    htmlFor="file-upload"
                    className="cursor-pointer inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-xl text-blue-700 bg-blue-100 hover:bg-blue-200 transition-colors"
                  >
                    <PlusIcon className="h-5 w-5 mr-2" />
                    Choose File
                  </label>
                  <p className="mt-2 text-sm text-gray-500">
                    or drag and drop files here
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    PDF, DOC, DOCX, TXT, JSON up to 50MB
                  </p>
                </div>
              </div>

              {selectedFile && (
                <div className="flex items-center justify-between p-4 bg-blue-50 rounded-xl border border-blue-200">
                  <div className="flex items-center space-x-3">
                    <DocumentIcon className="h-8 w-8 text-blue-600" />
                    <div>
                      <p className="font-medium text-gray-900">
                        {selectedFile.name}
                      </p>
                      <p className="text-sm text-gray-600">
                        {Math.round(selectedFile.size / 1024)} KB
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button
                      onClick={uploadFile}
                      disabled={uploading}
                      loading={uploading}
                      variant="success"
                      gradient
                      icon={<CloudArrowUpIcon className="h-4 w-4" />}
                    >
                      {uploading ? 'Uploading...' : 'Upload'}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Files List */}
      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg">
                <FolderIcon className="h-6 w-6 text-white" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900">
                  Your Files
                </h2>
                <p className="text-sm text-gray-600">
                  {filteredFiles.length} files
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              {/* Search */}
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search files..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 pr-4 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent w-64"
                />
              </div>

              {/* View Toggle */}
              <div className="flex items-center bg-gray-100 rounded-lg p-1">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === 'grid'
                      ? 'bg-white text-blue-600 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  <Squares2X2Icon className="h-4 w-4" />
                </button>
                <button
                  onClick={() => setViewMode('list')}
                  className={`p-2 rounded-md transition-colors ${
                    viewMode === 'list'
                      ? 'bg-white text-blue-600 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  <ListBulletIcon className="h-4 w-4" />
                </button>
              </div>

              {/* Refresh Button */}
              <Button
                onClick={loadFiles}
                loading={loading}
                variant="ghost"
                size="sm"
              >
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardBody>
          {loading ? (
            <LoadingScreen message="Loading files..." />
          ) : filteredFiles.length === 0 ? (
            <div className="text-center py-16">
              <div className="relative">
                <DocumentIcon className="mx-auto h-16 w-16 text-gray-300" />
                <div className="absolute top-0 right-0 w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center">
                  <PlusIcon className="w-4 h-4 text-white" />
                </div>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-gray-900">
                No files found
              </h3>
              <p className="mt-2 text-gray-600">
                {searchQuery
                  ? 'Try adjusting your search terms'
                  : 'Upload your first file to get started'}
              </p>
              {!searchQuery && (
                <Button
                  onClick={() =>
                    document.getElementById('file-upload')?.click()
                  }
                  className="mt-4"
                  variant="primary"
                  gradient
                  icon={<CloudArrowUpIcon className="h-4 w-4" />}
                >
                  Upload Files
                </Button>
              )}
            </div>
          ) : viewMode === 'grid' ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {filteredFiles.map((file) => {
                const FileIcon = getFileIcon(file.mimeType)
                return (
                  <Card key={file.id} hover className="group">
                    <CardBody>
                      <div className="flex flex-col items-center text-center space-y-4">
                        <div className="relative">
                          <div className="w-16 h-16 bg-gradient-to-br from-blue-100 to-indigo-100 rounded-xl flex items-center justify-center group-hover:from-blue-200 group-hover:to-indigo-200 transition-colors">
                            <FileIcon className="h-8 w-8 text-blue-600" />
                          </div>
                          <Badge
                            variant="primary"
                            size="sm"
                            className="absolute -top-2 -right-2"
                          >
                            {file.mimeType.includes('folder')
                              ? 'Folder'
                              : 'File'}
                          </Badge>
                        </div>

                        <div className="w-full space-y-2">
                          <h3
                            className="font-semibold text-gray-900 truncate"
                            title={file.name}
                          >
                            {file.name}
                          </h3>
                          <p className="text-sm text-gray-500">
                            {formatFileSize(file.size)}
                          </p>
                          <p className="text-xs text-gray-400">
                            {new Date(file.modifiedTime).toLocaleDateString()}
                          </p>
                        </div>

                        <div className="flex items-center space-x-2 w-full">
                          <Button
                            onClick={() => downloadFile(file.id, file.name)}
                            variant="ghost"
                            size="sm"
                            className="flex-1"
                            icon={<ArrowDownTrayIcon className="h-4 w-4" />}
                          >
                            Download
                          </Button>
                          <Button
                            onClick={() => setSharingFileId(file.id)}
                            variant="ghost"
                            size="sm"
                            icon={<ShareIcon className="h-4 w-4" />}
                          >
                            <span className="sr-only">Share</span>
                          </Button>
                          <Button
                            onClick={() => deleteFile(file.id)}
                            variant="ghost"
                            size="sm"
                            className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            icon={<TrashIcon className="h-4 w-4" />}
                          >
                            <span className="sr-only">Delete</span>
                          </Button>
                        </div>
                      </div>
                    </CardBody>
                  </Card>
                )
              })}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="px-6 py-4 text-left text-sm font-semibold text-gray-900">
                      Name
                    </th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-gray-900">
                      Type
                    </th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-gray-900">
                      Size
                    </th>
                    <th className="px-6 py-4 text-left text-sm font-semibold text-gray-900">
                      Modified
                    </th>
                    <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredFiles.map((file) => {
                    const FileIcon = getFileIcon(file.mimeType)
                    return (
                      <tr
                        key={file.id}
                        className="hover:bg-gradient-to-r hover:from-blue-50/30 hover:to-indigo-50/30 transition-colors group"
                      >
                        <td className="px-6 py-4">
                          <div className="flex items-center space-x-3">
                            <div className="w-10 h-10 bg-gradient-to-br from-blue-100 to-indigo-100 rounded-lg flex items-center justify-center group-hover:from-blue-200 group-hover:to-indigo-200 transition-colors">
                              <FileIcon className="h-5 w-5 text-blue-600" />
                            </div>
                            <div>
                              <p className="font-medium text-gray-900">
                                {file.name}
                              </p>
                              <p className="text-sm text-gray-500">
                                {file.mimeType}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <Badge
                            variant={
                              file.mimeType.includes('folder')
                                ? 'info'
                                : 'secondary'
                            }
                            size="sm"
                          >
                            {file.mimeType.includes('folder')
                              ? 'Folder'
                              : 'File'}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600">
                          {formatFileSize(file.size)}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600">
                          {new Date(file.modifiedTime).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center justify-end space-x-2">
                            <Button
                              onClick={() => downloadFile(file.id, file.name)}
                              variant="ghost"
                              size="sm"
                              icon={<ArrowDownTrayIcon className="h-4 w-4" />}
                            >
                              <span className="sr-only">Download</span>
                            </Button>
                            <Button
                              onClick={() => setSharingFileId(file.id)}
                              variant="ghost"
                              size="sm"
                              className="text-green-600 hover:text-green-700 hover:bg-green-50"
                              icon={<ShareIcon className="h-4 w-4" />}
                            >
                              <span className="sr-only">Share</span>
                            </Button>
                            <Button
                              onClick={() => deleteFile(file.id)}
                              variant="ghost"
                              size="sm"
                              className="text-red-600 hover:text-red-700 hover:bg-red-50"
                              icon={<TrashIcon className="h-4 w-4" />}
                            >
                              <span className="sr-only">Delete</span>
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Share Modal */}
      {sharingFileId && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm overflow-y-auto h-full w-full z-50 flex items-center justify-center p-4">
          <div className="relative w-full max-w-md">
            <Card className="animate-in fade-in zoom-in duration-300">
              <CardHeader>
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-gradient-to-r from-green-500 to-emerald-500 rounded-lg">
                    <ShareIcon className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold text-gray-900">
                      Share File
                    </h3>
                    <p className="text-sm text-gray-600">
                      Control file access and permissions
                    </p>
                  </div>
                </div>
              </CardHeader>
              <CardBody>
                <div className="space-y-6">
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-3">
                      Share with specific person
                    </label>
                    <input
                      type="email"
                      value={shareEmail}
                      onChange={(e) => setShareEmail(e.target.value)}
                      className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all duration-200"
                      placeholder="Enter email address (optional)"
                    />
                    <p className="mt-2 text-xs text-gray-500">
                      Leave empty to create a public link that anyone can access
                    </p>
                  </div>

                  <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl p-4 border border-green-200">
                    <div className="flex items-center space-x-3">
                      <CheckCircleIcon className="h-5 w-5 text-green-600" />
                      <div>
                        <p className="text-sm font-medium text-green-900">
                          Read-only access
                        </p>
                        <p className="text-xs text-green-700">
                          Recipients can view and download the file
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </CardBody>
              <div className="px-6 py-4 border-t border-gray-200/50 bg-gray-50/50 flex justify-end space-x-3">
                <Button
                  onClick={() => {
                    setSharingFileId(null)
                    setShareEmail('')
                  }}
                  variant="secondary"
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => shareFile(sharingFileId)}
                  variant="success"
                  gradient
                  icon={<ShareIcon className="h-4 w-4" />}
                >
                  Share File
                </Button>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
