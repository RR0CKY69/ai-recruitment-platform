import ModalDialog from './ModalDialog'

interface ConfirmationDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  confirmingLabel?: string
  cancelLabel?: string
  confirming?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export default function ConfirmationDialog({
  open,
  title,
  description,
  confirmLabel,
  confirmingLabel = 'Please wait...',
  cancelLabel = 'Cancel',
  confirming = false,
  onCancel,
  onConfirm,
}: ConfirmationDialogProps) {
  const handleCancel = () => {
    if (!confirming) onCancel()
  }

  return (
    <ModalDialog
      open={open}
      title={title}
      description={description}
      onClose={handleCancel}
      role="alertdialog"
      showCloseButton={false}
    >
      <div className="flex flex-wrap justify-end gap-3">
        <button type="button" className="button-ghost" disabled={confirming} onClick={handleCancel}>
          {cancelLabel}
        </button>
        <button type="button" className="button-secondary inline-flex items-center gap-2" disabled={confirming} onClick={onConfirm}>
          {confirming ? confirmingLabel : confirmLabel}
        </button>
      </div>
    </ModalDialog>
  )
}
