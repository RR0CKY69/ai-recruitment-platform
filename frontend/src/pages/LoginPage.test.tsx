import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../features/auth/AuthContext'
import LoginPage from './LoginPage'

test('renders login form', () => {
  render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  )
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy()
})