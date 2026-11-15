/**
 * Application shell: sidebar, topbar, and the mobile drawer.
 *
 * Layout strategy: the sidebar is `position: fixed` and translated off-canvas below 1025px, where
 * the topbar's menu button reveals it as a drawer with a scrim; at 1025px and above it becomes a
 * sticky grid column and the menu button disappears. One component serves both because the only
 * differences are a CSS class and whether the drawer is open.
 *
 * The unread badge polls `/notifications/unread-count/` (30s) only while a session exists — passing
 * `enabled: isAuthenticated` keeps an anonymous visitor from firing a stream of 403s.
 */

import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuthContext, isAdmin } from '../features/auth/hooks/useAuthContext'
import { useLogout, useUnreadNotificationCount } from '../features/auth/hooks'
import { roleLabel } from '../lib/format'
import { Avatar } from '../components/ui/Card'
import { Button } from '../components/ui/Button'

interface NavItem {
  to: string
  label: string
  icon: string
  /** Notification badge source. */
  badge?: 'unread'
  end?: boolean
}

interface NavGroup {
  label?: string
  items: NavItem[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      { to: '/', label: 'Dashboard', icon: '▦', end: true },
      { to: '/my-assignments', label: 'My assignments', icon: '☑' },
      { to: '/notifications', label: 'Notifications', icon: '🔔', badge: 'unread' },
    ],
  },
  {
    label: 'Work',
    items: [
      { to: '/tickets', label: 'Tickets', icon: '◈' },
      { to: '/projects', label: 'Projects', icon: '▤' },
      { to: '/reports', label: 'Reports', icon: '◔' },
    ],
  },
  {
    label: 'Organisation',
    items: [{ to: '/team', label: 'Team', icon: '☰' }],
  },
]

export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()
  const { user, isAuthenticated } = useAuthContext()
  const logout = useLogout()
  const unread = useUnreadNotificationCount(isAuthenticated)

  // Close the drawer on navigation: otherwise it stays open over the screen the user asked for.
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  const unreadCount = unread.data?.unread ?? 0

  // The admin-only audit screen is appended for admins only. This is presentation: the endpoint
  // itself is `IsAdminUser`, so a non-admin who types the URL gets the API's 403, not data.
  const groups: NavGroup[] = isAdmin(user)
    ? [
        ...NAV_GROUPS,
        { label: 'Security', items: [{ to: '/audit', label: 'Audit log', icon: '⌘' }] },
      ]
    : NAV_GROUPS

  return (
    <div className="app-shell">
      {drawerOpen ? (
        <button
          type="button"
          className="sidebar__scrim"
          aria-label="Close navigation"
          onClick={() => setDrawerOpen(false)}
        />
      ) : null}

      <aside className={`sidebar${drawerOpen ? ' sidebar--open' : ''}`} id="app-sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__mark" aria-hidden="true">
            ET
          </span>
          <span>Eng Tracker</span>
        </div>

        <nav className="sidebar__nav" aria-label="Main">
          {groups.map((group, index) => (
            <div key={group.label ?? `group-${index}`}>
              {group.label ? <p className="sidebar__group-label">{group.label}</p> : null}
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => `sidebar__link${isActive ? ' sidebar__link--active' : ''}`}
                >
                  <span className="sidebar__link-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                  {item.badge === 'unread' && unreadCount > 0 ? (
                    <span className="sidebar__link-badge">
                      {unreadCount > 99 ? '99+' : unreadCount}
                      <span className="sr-only"> unread notifications</span>
                    </span>
                  ) : null}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="sidebar__user">
            <Avatar name={user?.full_name} size="sm" />
            <div style={{ minWidth: 0, flex: 1 }}>
              <p className="sidebar__user-name">{user?.full_name ?? 'Signed out'}</p>
              <p className="sidebar__user-role">{user ? roleLabel(user.system_role) : ''}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            fullWidth
            loading={logout.isPending}
            onClick={() => logout.mutate()}
          >
            Sign out
          </Button>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <Button
            variant="ghost"
            iconOnly
            className="topbar__menu"
            aria-label="Open navigation"
            aria-controls="app-sidebar"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            ☰
          </Button>
          <span className="topbar__title">
            {titleForPath(location.pathname)}
          </span>
          <span className="topbar__spacer" />
          <div className="topbar__actions">
            <NotificationBell count={unreadCount} />
            <NavLink to="/profile" className="row row--nowrap" style={{ color: 'inherit', gap: 'var(--space-2)' }}>
              <Avatar name={user?.full_name} size="sm" />
              <span className="sr-only">Your profile</span>
            </NavLink>
          </div>
        </header>

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function NotificationBell({ count }: { count: number }) {
  return (
    <NavLink to="/notifications" className="icon-button" aria-label={`Notifications${count > 0 ? `, ${count} unread` : ''}`}>
      <span aria-hidden="true">🔔</span>
      {count > 0 ? (
        <span className="icon-button__badge">{count > 99 ? '99+' : count}</span>
      ) : null}
    </NavLink>
  )
}

/**
 * Topbar title.
 *
 * Resolved from the path rather than from each screen, so the topbar does not have to be re-rendered
 * by a context update every time a title changes. Deep routes fall back to their section name.
 */
function titleForPath(pathname: string): string {
  if (pathname === '/' || pathname === '') return 'Dashboard'
  const segments = pathname.split('/').filter(Boolean)
  const first = segments[0] ?? ''
  const titles: Record<string, string> = {
    tickets: 'Tickets',
    projects: 'Projects',
    'my-assignments': 'My assignments',
    notifications: 'Notifications',
    reports: 'Reports',
    team: 'Team',
    profile: 'Profile',
    audit: 'Audit log',
  }
  const base = titles[first] ?? 'Eng Tracker'
  if (segments.length > 1 && first === 'tickets') return 'Ticket detail'
  if (segments.length > 1 && first === 'projects') return 'Project detail'
  return base
}
