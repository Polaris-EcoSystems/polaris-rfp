import { SparklesIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

interface AIModalProps {
  isOpen: boolean
  onClose: () => void
  onApply: (prompt: string) => void
  selectedText?: string
  isLoading?: boolean
}

export default function AIModal({
  isOpen,
  onClose,
  onApply,
  selectedText,
  isLoading = false,
}: AIModalProps) {
  const [aiPrompt, setAiPrompt] = useState('')

  const handleApply = () => {
    if (aiPrompt.trim()) {
      onApply(aiPrompt)
      setAiPrompt('')
    }
  }

  const handleClose = () => {
    setAiPrompt('')
    onClose()
  }

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center "
      onClick={handleClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl border border-gray-200 p-4 w-80 max-w-[90vw] max-h-[90vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-2">
            <SparklesIcon className="h-4 w-4 text-purple-600" />
            <h3 className="text-sm font-semibold text-gray-900">Ask with AI</h3>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        </div>

        {selectedText && (
          <div className="mb-3 p-2 bg-gray-50 rounded text-xs">
            <p className="text-gray-600 mb-1 font-medium">Selected text:</p>
            <p className="text-gray-700 italic">&quot;{selectedText}&quot;</p>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              What would you like AI to do?
            </label>
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="e.g., 'Make this more professional', 'Rewrite this more concisely', 'Add technical details', 'Convert to bullet points'"
              className="w-full p-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
              rows={3}
            />
          </div>

          <div className="flex items-center justify-end space-x-2">
            <button
              onClick={handleClose}
              className="px-3 py-1 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={!aiPrompt.trim() || isLoading}
              className="px-3 py-1 text-xs font-medium text-white bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors flex items-center space-x-1"
            >
              {isLoading ? (
                <>
                  <div className="animate-spin rounded-full h-3 w-3 border-2 border-white border-t-transparent"></div>
                  <span>Processing...</span>
                </>
              ) : (
                <>
                  <SparklesIcon className="h-3 w-3" />
                  <span>Apply</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
