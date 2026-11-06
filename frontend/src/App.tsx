import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './features/auth/AuthContext'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import WorkspaceSelectPage from './pages/WorkspaceSelectPage'
import DashboardPage from './pages/DashboardPage'
import JobsPage from './pages/JobsPage'
import JobDetailPage from './pages/JobDetailPage'
import MatchingPage from './pages/MatchingPage'
import CandidatesPage from './pages/CandidatesPage'
import CandidateDetailPage from './pages/CandidateDetailPage'
import ShortlistsPage from './pages/ShortlistsPage'
import EvaluationsPage from './pages/EvaluationsPage'
import BooleanSearchPage from './pages/BooleanSearchPage'
import SettingsPage from './pages/SettingsPage'
import { Placeholder } from './components/shared/Placeholder'
import PipelinePage from './pages/PipelinePage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/workspaces" element={<WorkspaceSelectPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
            <Route path="/candidates" element={<CandidatesPage />} />
            <Route path="/candidates/:candidateId" element={<CandidateDetailPage />} />
            <Route path="/matching" element={<MatchingPage />} />
            <Route path="/boolean-search" element={<BooleanSearchPage />} />
            <Route path="/shortlisted" element={<ShortlistsPage />} />
            <Route path="/evaluations" element={<EvaluationsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/workspace-team" element={<Placeholder title="Workspace & Team" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}