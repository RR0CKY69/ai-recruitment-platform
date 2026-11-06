import { beforeEach, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ResumeUploadDialog, { MAX_RESUME_SIZE_BYTES, validateResumeFile } from './ResumeUploadDialog'

vi.mock('../../features/candidates/api', () => ({
  uploadCandidateResume: vi.fn(),
}))

import { uploadCandidateResume } from '../../features/candidates/api'

beforeEach(() => vi.clearAllMocks())

test('accepts PDF and DOCX resumes within the configured size limit', () => {
  expect(validateResumeFile(new File(['pdf'], 'resume.pdf', { type: 'application/pdf' }))).toBeNull()
  expect(validateResumeFile(new File(['docx'], 'resume.docx', {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  }))).toBeNull()
  expect(validateResumeFile(new File([new Uint8Array(MAX_RESUME_SIZE_BYTES)], 'resume.pdf', {
    type: 'application/pdf',
  }))).toBeNull()
})

test('rejects unsupported, mismatched and oversized files', () => {
  expect(validateResumeFile(new File(['text'], 'resume.txt', { type: 'text/plain' }))).toMatch(/PDF or DOCX/)
  expect(validateResumeFile(new File(['docx'], 'resume.pdf', { type: 'text/plain' }))).toMatch(/PDF or DOCX/)
  expect(validateResumeFile(new File([new Uint8Array(MAX_RESUME_SIZE_BYTES + 1)], 'resume.pdf', {
    type: 'application/pdf',
  }))).toMatch(/10 MB/)
})

test('shows filename, supports removal, and prevents upload without a selected file', () => {
  render(<ResumeUploadDialog open workspaceId="workspace-1" onClose={vi.fn()} onReview={vi.fn()} />)
  const input = screen.getByLabelText('Choose a PDF or DOCX resume') as HTMLInputElement
  fireEvent.change(input, { target: { files: [new File(['pdf'], 'candidate.pdf', { type: 'application/pdf' })] } })

  expect(screen.getByText('candidate.pdf')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Upload resume' })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Remove selected resume' }))
  expect(screen.queryByText('candidate.pdf')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Upload resume' })).toBeDisabled()
  expect(uploadCandidateResume).not.toHaveBeenCalled()
})

test('shows upload API failures and does not provide parsed-profile success', async () => {
  vi.mocked(uploadCandidateResume).mockRejectedValueOnce(new Error('API unavailable'))
  render(<ResumeUploadDialog open workspaceId="workspace-1" onClose={vi.fn()} onReview={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Choose a PDF or DOCX resume'), {
    target: { files: [new File(['pdf'], 'candidate.pdf', { type: 'application/pdf' })] },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Upload resume' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable')
  expect(screen.queryByText(/parsed candidate information/i)).not.toBeInTheDocument()
})

test('returns backend parsed draft for review without saving it', async () => {
  const draft = { full_name: 'Parsed Candidate', email: 'parsed@example.test' }
  const onClose = vi.fn()
  const onReview = vi.fn()
  vi.mocked(uploadCandidateResume).mockResolvedValueOnce({ parsed_candidate: draft })
  render(<ResumeUploadDialog open workspaceId="workspace-1" onClose={onClose} onReview={onReview} />)
  fireEvent.change(screen.getByLabelText('Choose a PDF or DOCX resume'), {
    target: { files: [new File(['pdf'], 'candidate.pdf', { type: 'application/pdf' })] },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Upload resume' }))

  await waitFor(() => expect(onReview).toHaveBeenCalledWith(draft))
  expect(onClose).toHaveBeenCalledOnce()
})
