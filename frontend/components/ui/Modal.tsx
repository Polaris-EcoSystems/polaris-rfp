'use client'

import { Dialog, DialogPanel, DialogTitle, Transition } from '@headlessui/react'
import { Fragment, ReactNode, useId, useRef } from 'react'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title?: string
  children?: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}

export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  size = 'sm',
}: ModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const titleId = useId()

  const maxWidth =
    size === 'lg' ? 'max-w-3xl' : size === 'md' ? 'max-w-xl' : 'max-w-sm'

  return (
    <Transition show={isOpen} as={Fragment}>
      <Dialog
        onClose={onClose}
        className="relative z-50"
        initialFocus={closeButtonRef}
        aria-labelledby={
          (title || title === '') && title !== undefined ? titleId : undefined
        }
      >
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200 motion-reduce:transition-none"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150 motion-reduce:transition-none"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-500/75" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200 motion-reduce:transition-none"
              enterFrom="opacity-0 translate-y-2 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-150 motion-reduce:transition-none"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-2 sm:translate-y-0 sm:scale-95"
            >
              <DialogPanel
                className={`relative w-full ${maxWidth} rounded-lg bg-white shadow-xl`}
              >
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={onClose}
                  className="absolute right-3 top-3 inline-flex h-9 w-9 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                  aria-label="Close"
                >
                  <span aria-hidden="true">×</span>
                </button>

                {(title || title === '') && (
                  <div className="px-6 py-5 border-b border-gray-200">
                    <DialogTitle
                      id={titleId}
                      className="text-lg font-semibold text-gray-900 pr-10"
                    >
                      {title}
                    </DialogTitle>
                  </div>
                )}

                <div className="px-6 py-5 max-h-[calc(100vh-12rem)] overflow-auto">
                  {children}
                </div>

                {footer ? (
                  <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-end gap-3">
                    {footer}
                  </div>
                ) : null}
              </DialogPanel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}
