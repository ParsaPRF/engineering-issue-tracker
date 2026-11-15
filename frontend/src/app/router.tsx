/**
 * The route table.
 *
 * Structure: two public routes (`/login`, `/register`), then one protected branch whose element is
 * `<ProtectedRoute><AppShell/></ProtectedRoute>`. Because the shell is the layout route, every child
 * route is protected by construction — a new screen cannot be added outside the guard by accident,
 * which is the failure mode of putting `<ProtectedRoute>` around each page individually.
 *
 * `/login?next=…` round trip: `ProtectedRoute` writes the requested path into the query string and
 * `LoginPage` reads it back, so a deep link survives authentication.
 */

import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './AppShell'
import { ErrorBoundary } from './ErrorBoundary'
import { ProtectedRoute, PublicOnlyRoute } from '../features/auth/ProtectedRoute'
import { LoginPage } from '../pages/auth/LoginPage'
import { RegisterPage } from '../pages/auth/RegisterPage'
import { DashboardPage } from '../pages/DashboardPage'
import { ProjectsPage } from '../pages/ProjectsPage'
import { ProjectDetailPage } from '../pages/ProjectDetailPage'
import { TicketsPage } from '../pages/TicketsPage'
import { TicketCreatePage } from '../pages/TicketCreatePage'
import { TicketDetailPage } from '../pages/TicketDetailPage'
import { MyAssignmentsPage } from '../pages/MyAssignmentsPage'
import { NotificationsPage } from '../pages/NotificationsPage'
import { ReportsPage } from '../pages/ReportsPage'
import { ProfilePage } from '../pages/ProfilePage'
import { TeamPage } from '../pages/TeamPage'
import { AuditPage } from '../pages/AuditPage'
import { NotFoundPage } from '../pages/NotFoundPage'

export function AppRoutes() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <LoginPage />
            </PublicOnlyRoute>
          }
        />
        <Route
          path="/register"
          element={
            <PublicOnlyRoute>
              <RegisterPage />
            </PublicOnlyRoute>
          }
        />

        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/tickets" element={<TicketsPage />} />
          <Route path="/tickets/new" element={<TicketCreatePage />} />
          <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
          <Route path="/my-assignments" element={<MyAssignmentsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/team" element={<TeamPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>

        {/* An unknown path outside the shell still lands somewhere sensible. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
