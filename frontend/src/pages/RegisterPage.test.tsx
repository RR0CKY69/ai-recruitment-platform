import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, vi } from 'vitest'
import RegisterPage from './RegisterPage'

vi.mock('../features/auth/api', () => ({
  registerUser: vi.fn(),
}))

import { registerUser } from '../features/auth/api'

beforeEach(() => {
  vi.mocked(registerUser).mockReset()
})

function renderPage() {
  return render(<MemoryRouter><RegisterPage /></MemoryRouter>)
}

test('validates required fields, email, password length, and password confirmation', async () => {
  const user = userEvent.setup()
  renderPage()

  await user.click(screen.getByRole('button', { name: 'Create account' }))
  expect(screen.getByText('Enter your full name.')).toBeInTheDocument()
  expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
  expect(screen.getByText('Create a password.')).toBeInTheDocument()
  expect(screen.getByText('Confirm your password.')).toBeInTheDocument()
  expect(screen.getByText('Enter your workspace or company name.')).toBeInTheDocument()
  expect(registerUser).not.toHaveBeenCalled()

  await user.type(screen.getByLabelText('Full name'), 'Jordan Lee')
  await user.type(screen.getByLabelText('Email'), 'invalid-email')
  await user.type(screen.getByLabelText('Password'), 'short')
  await user.type(screen.getByLabelText('Confirm password'), 'different')
  await user.type(screen.getByLabelText('Workspace or company name'), 'Apex')
  await user.click(screen.getByRole('button', { name: 'Create account' }))

  expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
  expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument()
  expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
  expect(registerUser).not.toHaveBeenCalled()
})

test('toggles visibility for both password inputs', async () => {
  const user = userEvent.setup()
  renderPage()
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  expect(screen.getByLabelText('Confirm password')).toHaveAttribute('type', 'password')
  await user.click(screen.getByRole('button', { name: 'Show passwords' }))
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'text')
  expect(screen.getByLabelText('Confirm password')).toHaveAttribute('type', 'text')
})

test('sends the typed registration fields without storing credentials and links to sign in on success', async () => {
  const user = userEvent.setup()
  vi.mocked(registerUser).mockResolvedValueOnce()
  renderPage()

  await user.type(screen.getByLabelText('Full name'), '  Jordan Lee  ')
  await user.type(screen.getByLabelText('Email'), ' jordan@example.com ')
  await user.type(screen.getByLabelText('Password'), 'UniquePass123')
  await user.type(screen.getByLabelText('Confirm password'), 'UniquePass123')
  await user.type(screen.getByLabelText('Workspace or company name'), ' Apex Talent ')
  await user.click(screen.getByRole('button', { name: 'Create account' }))

  await waitFor(() => expect(registerUser).toHaveBeenCalledWith({
    full_name: 'Jordan Lee',
    email: 'jordan@example.com',
    password: 'UniquePass123',
    workspace_name: 'Apex Talent',
  }))
  expect(await screen.findByText('Your registration request was completed. Sign in to continue.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Go to sign in' })).toHaveAttribute('href', '/login')
  expect(localStorage.length).toBe(0)
})

test('shows a clear unavailable-API error without claiming registration succeeded', async () => {
  const user = userEvent.setup()
  const unavailable = Object.assign(new Error('Not found'), {
    isAxiosError: true,
    response: { status: 404, data: { detail: 'Not Found' } },
  })
  vi.mocked(registerUser).mockRejectedValueOnce(unavailable)
  renderPage()

  await user.type(screen.getByLabelText('Full name'), 'Jordan Lee')
  await user.type(screen.getByLabelText('Email'), 'jordan@example.com')
  await user.type(screen.getByLabelText('Password'), 'UniquePass123')
  await user.type(screen.getByLabelText('Confirm password'), 'UniquePass123')
  await user.type(screen.getByLabelText('Workspace or company name'), 'Apex Talent')
  await user.click(screen.getByRole('button', { name: 'Create account' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Registration is not available yet')
  expect(screen.getByRole('alert')).toHaveTextContent('No account was created.')
  expect(screen.queryByText('Your registration request was completed.')).not.toBeInTheDocument()
})
