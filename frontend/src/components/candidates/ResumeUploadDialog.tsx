import { useRef, useState } from 'react'
import { FileText, Upload, X } from 'lucide-react'
import { uploadCandidateResume, type ResumeCandidateDraft } from '../../features/candidates/api'
import { getApiErrorMessage } from '../../lib/apiErrors'
import ModalDialog from '../shared/ModalDialog'

export const MAX_RESUME_SIZE_BYTES = 10 * 1024 * 1024

export function validateResumeFile(file: File): string | null {
  const extension = file.name.split('.').pop()?.toLocaleLowerCase()
  const typeMatches = file.type === ''
    || (extension === 'pdf' && file.type === 'application/pdf')
    || (extension === 'docx' && file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
  if (!['pdf', 'docx'].includes(extension ?? '') || !typeMatches) {
    return 'Choose a PDF or DOCX resume.'
  }
  if (file.size === 0) return 'The selected file is empty.'
  if (file.size > MAX_RESUME_SIZE_BYTES) return 'Resume files must be 10 MB or smaller.'
  return null
}

export default function ResumeUploadDialog({
  open,
  workspaceId,
  onClose,
  onReview,
}: {
  open: boolean
  workspaceId: string
  onClose: () => void
  onReview: (draft: ResumeCandidateDraft) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploaded, setUploaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const chooseFile = (selected?: File) => {
    setError(null)
    setMessage(null)
    setUploaded(false)
    if (!selected) {
      setFile(null)
      return
    }
    const validationError = validateResumeFile(selected)
    if (validationError) {
      setFile(null)
      setError(validationError)
      return
    }
    setFile(selected)
  }

  const submit = async () => {
    if (!file || uploading) return
    setUploading(true)
    setError(null)
    setMessage(null)
    try {
      const response = await uploadCandidateResume(workspaceId, file)
      setUploaded(true)
      if (response.parsed_candidate) {
        onReview(response.parsed_candidate)
        setFile(null)
        setUploaded(false)
        if (inputRef.current) inputRef.current.value = ''
        onClose()
      } else {
        setMessage('The upload completed, but no parsed candidate information was returned. No profile has been saved.')
      }
    } catch (uploadError) {
      setError(getApiErrorMessage(uploadError, 'Resume upload failed.'))
    } finally {
      setUploading(false)
    }
  }

  const close = () => {
    if (uploading) return
    setFile(null)
    setUploaded(false)
    setError(null)
    setMessage(null)
    if (inputRef.current) inputRef.current.value = ''
    onClose()
  }

  return (
    <ModalDialog open={open} title="Upload candidate resume" description="PDF and DOCX files up to 10 MB. Parsed information must be reviewed before a profile is saved." onClose={close}>
      <div className="space-y-4">
        <label className="flex min-h-36 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-600 bg-slate-900/50 px-4 py-6 text-center transition hover:border-indigo-400/70 hover:bg-indigo-500/5">
          <Upload size={23} className="text-indigo-300" aria-hidden="true" />
          <span className="font-medium text-slate-100">{file ? 'Replace selected resume' : 'Choose a resume file'}</span>
          <span className="text-xs text-slate-400">PDF or DOCX · maximum 10 MB</span>
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            aria-label="Choose a PDF or DOCX resume"
            onChange={event => {
              chooseFile(event.target.files?.[0])
              event.target.value = ''
            }}
          />
        </label>

        {file && (
          <div className="flex min-w-0 items-center gap-3 rounded-xl border border-slate-700 bg-slate-900/70 p-3">
            <FileText size={19} className="shrink-0 text-cyan-300" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="break-all text-sm font-medium text-slate-100">{file.name}</p>
              <p className="mt-1 text-xs text-slate-400">{(file.size / (1024 * 1024)).toFixed(2)} MB · {uploading ? 'Uploading...' : uploaded ? 'Uploaded' : 'Ready to upload'}</p>
            </div>
            <button type="button" className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white" aria-label="Remove selected resume" disabled={uploading} onClick={() => chooseFile(undefined)}>
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        )}
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        {message && <p role="status" className="text-sm text-amber-200">{message}</p>}
        <div className="flex flex-wrap justify-end gap-3">
          <button type="button" className="button-ghost" disabled={uploading} onClick={close}>Cancel</button>
          <button type="button" className="button-primary" disabled={!file || uploading || uploaded} onClick={() => void submit()}>
            {uploading ? 'Uploading...' : uploaded ? 'Uploaded' : 'Upload resume'}
          </button>
        </div>
      </div>
    </ModalDialog>
  )
}
