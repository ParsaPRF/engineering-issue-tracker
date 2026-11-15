/**
 * 404 inside the authenticated shell.
 *
 * Kept inside `AppShell` so a mistyped URL still shows the navigation and the signed-in user rather
 * than dumping them onto a blank page.
 */

import { Link } from 'react-router-dom';
import { Card, PageHeader } from '../components/ui/Card';
import { EmptyState } from '../components/ui/States';

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" subtitle="That address does not exist in this application." />
      <Card>
        <EmptyState
          title="Nothing here"
          message="Check the address, or use the navigation to find what you were looking for."
          action={
            <>
              <Link to="/" className="btn btn--primary">
                Go to the dashboard
              </Link>
              <Link to="/tickets" className="btn btn--secondary">
                Browse tickets
              </Link>
            </>
          }
        />
      </Card>
    </>
  );
}
