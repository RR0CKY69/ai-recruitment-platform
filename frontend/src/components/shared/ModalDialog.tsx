import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface ModalDialogProps {
  open: boolean
  title: string
  description?: string
  onClose: () => void
  children: ReactNode
  role?: 'dialog' | 'alertdialog'
  showCloseButton?: boolean
}

const focusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function ModalDialog({
  open,
  title,
  description,
  onClose,
  children,
  role = 'dialog',
  showCloseButton = true,
}: ModalDialogProps) {
  const titleId = useId()
  const descriptionId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return

    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const firstFocusable = dialogRef.current?.querySelector<HTMLElement>(focusableSelector)
    if (closeRef.current) closeRef.current.focus()
    else firstFocusable?.focus()
    return () => previousFocus?.focus()
  }, [open])

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }

    if (event.key !== 'Tab' || !dialogRef.current) return
    const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(focusableSelector))
    if (focusable.length === 0) {
      event.preventDefault()
      return
    }

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        onKeyDown={handleKeyDown}
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm"
      >
        <section className="panel max-h-[calc(100vh-2rem)] w-full max-w-lg overflow-y-auto p-5 shadow-2xl shadow-black/40 md:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id={titleId} className="text-lg font-semibold text-slate-100">{title}</h2>
              {description && <p id={descriptionId} className="mt-2 text-sm leading-6 text-slate-300">{description}</p>}
            </div>
            {showCloseButton && (
              <button
                ref={closeRef}
                type="button"
                aria-label="Close dialog"
                onClick={onClose}
                className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400"
              >
                <X size={17} aria-hidden="true" />
              </button>
            )}
          </div>
          <div className="mt-5">{children}</div>
        </section>
      </div>
    </div>
  )
}
