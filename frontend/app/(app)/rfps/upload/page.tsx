'use client'

import { rfpApi } from '@/lib/api'
import {
  CloudArrowUpIcon,
  DocumentIcon,
  DocumentTextIcon,
  LinkIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { useDropzone } from 'react-dropzone'

export default function UploadRFPPage() {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('pdf')
  const [url, setUrl] = useState('')
  const router = useRouter()

  const onDrop = async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0]
    if (!file) return

    const isPdf =
      file.type === 'application/pdf' ||
      file.name.toLowerCase().endsWith('.pdf')
    if (!isPdf) {
      setError('Please upload a PDF file')
      return
    }

    setUploading(true)
    setError('')

    try {
      await rfpApi.upload(file)
      router.push('/')
    } catch (err) {
      setError('Failed to upload and analyze RFP. Please try again.')
      console.error('Upload error:', err)
    } finally {
      setUploading(false)
    }
  }

  const isValidUrl = (value: string): boolean => {
    try {
      new URL(value)
      return true
    } catch {
      return false
    }
  }

  const handleUrlAnalysis = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!url.trim()) {
      setError('Please enter a URL')
      return
    }

    if (!isValidUrl(url)) {
      setError('Please enter a valid URL')
      return
    }

    setUploading(true)
    setError('')

    try {
      await rfpApi.analyzeUrl(url)
      router.push('/')
    } catch (err) {
      setError('Failed to analyze RFP from URL. Please try again.')
      console.error('URL analysis error:', err)
    } finally {
      setUploading(false)
    }
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf', '.PDF'],
      // Some browsers/providers use a non-standard MIME for PDFs
      'application/x-pdf': ['.pdf', '.PDF'],
    },
    maxFiles: 1,
  })

  return (
    <div className="max-w-2xl mx-auto">
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            Add RFP Document
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Upload a PDF file or provide a URL to automatically analyze
            requirements and generate a proposal
          </p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="mt-8">
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('pdf')}
              className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
                activeTab === 'pdf'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
              type="button"
            >
              <DocumentIcon className="h-5 w-5 inline mr-2" />
              Upload PDF
            </button>
            <button
              onClick={() => setActiveTab('url')}
              className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
                activeTab === 'url'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
              type="button"
            >
              <LinkIcon className="h-5 w-5 inline mr-2" />
              Analyze URL
            </button>
          </nav>
        </div>
      </div>

      <div className="mt-6">
        {error && (
          <div className="mb-4 rounded-md bg-red-50 p-4">
            <div className="text-sm text-red-700">{error}</div>
          </div>
        )}

        {/* PDF Upload Tab */}
        {activeTab === 'pdf' && (
          <div
            {...getRootProps()}
            className={`mt-2 flex justify-center px-6 pt-5 pb-6 border-2 border-dashed rounded-md cursor-pointer transition-colors ${
              isDragActive
                ? 'border-primary-400 bg-primary-50'
                : 'border-gray-300 hover:border-gray-400'
            } ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <div className="space-y-1 text-center">
              <input {...getInputProps()} disabled={uploading} />
              {uploading ? (
                <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
              ) : (
                <CloudArrowUpIcon className="mx-auto h-12 w-12 text-gray-400" />
              )}
              <div className="flex text-sm text-gray-600">
                <label className="relative cursor-pointer bg-white rounded-md font-medium text-primary-600 hover:text-primary-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-primary-500">
                  {uploading ? (
                    <span>Analyzing RFP...</span>
                  ) : isDragActive ? (
                    <span>Drop the RFP file here</span>
                  ) : (
                    <span>Upload a file or drag and drop</span>
                  )}
                </label>
              </div>
              <p className="text-xs text-gray-500">
                PDF files only, up to 10MB
              </p>
            </div>
          </div>
        )}

        {/* URL Input Tab */}
        {activeTab === 'url' && (
          <form onSubmit={handleUrlAnalysis} className="space-y-4">
            <div>
              <label
                htmlFor="rfp-url"
                className="block text-sm font-medium text-gray-700"
              >
                RFP Document URL
              </label>
              <div className="mt-1 relative">
                <input
                  type="url"
                  id="rfp-url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/rfp-page or https://example.com/rfp.pdf"
                  disabled={uploading}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm disabled:bg-gray-50 disabled:text-gray-500"
                />
                <div className="absolute inset-y-0 right-0 flex items-center pr-3">
                  <LinkIcon className="h-5 w-5 text-gray-400" />
                </div>
              </div>
              <p className="mt-2 text-sm text-gray-500">
                Provide a direct link to an RFP document (PDF) or webpage
                containing RFP information. Supports any web URL.
              </p>
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={uploading || !url.trim()}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploading ? (
                  <>
                    <div className="animate-spin -ml-1 mr-3 h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <DocumentTextIcon className="-ml-1 mr-2 h-4 w-4" />
                    Analyze RFP
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>

      <div className="mt-8 bg-blue-50 border border-blue-200 rounded-md p-4">
        <div className="flex">
          <DocumentIcon className="flex-shrink-0 h-5 w-5 text-blue-400" />
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">
              What happens after analysis?
            </h3>
            <div className="mt-2 text-sm text-blue-700">
              <ul className="list-disc pl-5 space-y-1">
                <li>The system extracts and analyzes RFP requirements</li>
                <li>Project type is automatically classified</li>
                <li>Key requirements and deadlines are identified</li>
                <li>You can then generate a customized proposal</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}



