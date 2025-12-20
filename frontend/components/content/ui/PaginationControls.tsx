'use client'

export default function PaginationControls({
  page,
  totalPages,
  onPrev,
  onNext,
}: {
  page: number
  totalPages: number
  onPrev: () => void
  onNext: () => void
}) {
  if (totalPages <= 1) return null

  const current = Math.min(Math.max(1, page), totalPages)

  return (
    <div className="flex items-center justify-between">
      <button
        type="button"
        onClick={onPrev}
        disabled={current <= 1}
        className="px-3 py-2 text-sm rounded border border-gray-300 bg-white disabled:opacity-50"
      >
        Prev
      </button>
      <div className="text-sm text-gray-600">
        Page {current} / {totalPages}
      </div>
      <button
        type="button"
        onClick={onNext}
        disabled={current >= totalPages}
        className="px-3 py-2 text-sm rounded border border-gray-300 bg-white disabled:opacity-50"
      >
        Next
      </button>
    </div>
  )
}
