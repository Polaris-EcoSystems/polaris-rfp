'use client'

import React from 'react'

type Props = {
  children: React.ReactNode
}

type State = {
  hasError: boolean
  errorMessage: string
}

export default class AppErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, errorMessage: '' }

  static getDerivedStateFromError(error: unknown): State {
    const msg =
      error instanceof Error ? error.message : String(error || 'Unknown error')
    return { hasError: true, errorMessage: msg }
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    // Keep this as console.error so it shows up in prod logs/DevTools.
    // eslint-disable-next-line no-console
    console.error('[AppErrorBoundary] Uncaught render error', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
        <div className="w-full max-w-xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="text-lg font-semibold text-gray-900">
            Something went wrong
          </div>
          <div className="mt-2 text-sm text-gray-700">
            The app hit an unexpected error while rendering this page.
          </div>
          <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700 font-mono break-words">
            {this.state.errorMessage}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
            <a
              className="px-4 py-2 rounded-lg bg-gray-100 text-gray-800 text-sm hover:bg-gray-200"
              href="/login/"
            >
              Go to login
            </a>
          </div>
          <div className="mt-3 text-xs text-gray-500">
            If this keeps happening, open DevTools and check the console for
            “AppErrorBoundary”.
          </div>
        </div>
      </div>
    )
  }
}
