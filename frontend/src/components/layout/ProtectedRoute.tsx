import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../../features/auth/AuthContext'
import { LoadingState } from '../shared/Primitives'

export function ProtectedRoute() {
  const { token, loading } = useAuth()
  if (loading) return <div className="p-6"><LoadingState label="Restoring your session..." /></div>
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}