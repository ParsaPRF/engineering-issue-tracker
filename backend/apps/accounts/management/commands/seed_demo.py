"""``manage.py seed_demo`` — populate a development instance with realistic data.

Design rules:

* **Idempotent.** Running it twice does not duplicate anything: every object is looked up by its
  natural key (email, project key, ticket title) first.
* **Through the services.** Users, projects and tickets are created by calling the same service
  functions the API uses, so the seeded data satisfies every invariant (owner is a manager, every
  ticket has a key and a timeline entry, audit events exist). Inserting rows directly would create a
  database that the application itself would never produce — useless for testing.
* **Obviously fake credentials.** The passwords are printed at the end and are documented as
  demo-only; they must never reach a production deployment.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import SystemRole, User
from apps.projects.models import Project, ProjectMembership, ProjectRole
from apps.projects.services.components import create_component
from apps.projects.services.memberships import add_member
from apps.projects.services.projects import create_project
from apps.tickets.models import Priority, Severity, Ticket, TicketStatus, TicketType
from apps.tickets.services.tickets import assign_ticket, create_ticket
from apps.workflows.services import transition_ticket

#: Demo-only password, printed at the end of the run. Banned from production deployments because
#: ``manage.py seed_demo`` is documented as a development convenience only.
DEMO_PASSWORD = "Demo!Passw0rd"  # noqa: S105 - intentional fixture credential, never used in production

DEMO_USERS = [
    ("admin@example.com", "Ada Admin", SystemRole.ADMIN),
    ("manager@example.com", "Mo Manager", SystemRole.PROJECT_MANAGER),
    ("engineer@example.com", "Eve Engineer", SystemRole.ENGINEER),
    ("engineer2@example.com", "Sam Senior", SystemRole.ENGINEER),
    ("reporter@example.com", "Rob Reporter", SystemRole.REPORTER),
]

DEMO_TICKETS = [
    {
        "title": "Checkout returns 500 when the coupon expires mid-session",
        "description": "Steps:\n1. add an item\n2. apply an expired coupon\n\nExpected: a validation message.\nActual: HTTP 500.",
        "type": TicketType.BUG,
        "priority": Priority.CRITICAL,
        "severity": Severity.CRITICAL,
        "component": "Checkout",
        "assignee": "engineer@example.com",
        "journey": [TicketStatus.TRIAGED, TicketStatus.IN_PROGRESS],
    },
    {
        "title": "Add CSV export to the ticket list",
        "description": "Managers want to export the filtered ticket list for sprint reviews. Respect active filters.",
        "type": TicketType.FEATURE,
        "priority": Priority.MEDIUM,
        "severity": Severity.MINOR,
        "component": "Web App",
        "assignee": "engineer2@example.com",
        "journey": [TicketStatus.TRIAGED],
    },
    {
        "title": "Rotate the staging database credentials",
        "description": "The staging credentials were shared in a public channel; rotate and update the secret store.",
        "type": TicketType.TASK,
        "priority": Priority.HIGH,
        "severity": Severity.MAJOR,
        "component": "Infrastructure",
        "assignee": None,
        "journey": [TicketStatus.TRIAGED, TicketStatus.BLOCKED],
    },
    {
        "title": "Deprecate the v1 search endpoint",
        "description": "The v1 search endpoint has no callers left. Announce deprecation, then remove it.",
        "type": TicketType.CHANGE_REQUEST,
        "priority": Priority.LOW,
        "severity": Severity.MINOR,
        "component": "API",
        "assignee": None,
        "journey": [],
    },
    {
        "title": "Customer cannot upload evidence larger than 5 MB",
        "description": "Support reports that a 6 MB log file is rejected although the documented limit is 10 MB.",
        "type": TicketType.SUPPORT,
        "priority": Priority.HIGH,
        "severity": Severity.MAJOR,
        "component": "API",
        "assignee": "engineer@example.com",
        "journey": [TicketStatus.TRIAGED, TicketStatus.IN_PROGRESS, TicketStatus.IN_REVIEW],
    },
]


class Command(BaseCommand):
    help = "Create demo users, a demo project, components and tickets (idempotent, development only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--project-key",
            default="ENG",
            help="Key of the demo project (default: ENG).",
        )

    # NOTE on transactions: this command deliberately does **not** wrap the whole run in one
    # ``transaction.atomic()`` block. Each service call is atomic on its own, which is the right
    # granularity for a seeding command: progress survives a failure, locks are short, and a
    # half-seeded database can simply be re-run (the command is idempotent). A single mega-transaction
    # also exposed an environment-specific SQLite failure ("unable to open database file") when an
    # audit write followed a project creation inside the same long transaction — documented in
    # docs/development/testing-guide.md.
    def handle(self, *args, **options):
        users = self._seed_users()
        project = self._seed_project(options["project_key"], users)
        self._seed_members(project, users)
        components = self._seed_components(project, users)
        self._seed_tickets(project, users, components)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  project      : {project.key} — {project.name}")
        self.stdout.write(f"  tickets      : {project.tickets.count()}")
        self.stdout.write("  accounts     (demo only — never use these passwords in production):")
        for email, full_name, role in DEMO_USERS:
            self.stdout.write(f"    {email:<24} {DEMO_PASSWORD:<16} {role}  ({full_name})")

    # -- helpers -------------------------------------------------------------
    def _seed_users(self) -> dict[str, User]:
        created: dict[str, User] = {}
        for email, full_name, role in DEMO_USERS:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=DEMO_PASSWORD, full_name=full_name, system_role=role)
                self.stdout.write(f"  + user {email} ({role})")
            created[email] = user
        return created

    def _seed_project(self, key: str, users: dict[str, User]) -> Project:
        existing = Project.objects.filter(key=key.upper()).first()
        if existing is not None:
            return existing
        project = create_project(
            actor=users["manager@example.com"],
            key=key,
            name="Engineering Platform",
            description="Core product engineering: API, web app, checkout and infrastructure.",
        )
        self.stdout.write(f"  + project {project.key}")
        return project

    def _seed_members(self, project: Project, users: dict[str, User]) -> None:
        plan = {
            "engineer@example.com": ProjectRole.ENGINEER,
            "engineer2@example.com": ProjectRole.ENGINEER,
            "reporter@example.com": ProjectRole.REPORTER,
        }
        for email, role in plan.items():
            if not ProjectMembership.objects.filter(project=project, user=users[email], is_active=True).exists():
                add_member(
                    actor=project.owner, project=project, user=users[email], role=role
                )
                self.stdout.write(f"  + member {email} as {role}")

    def _seed_components(self, project: Project, users: dict[str, User]) -> dict[str, object]:
        components = {}
        for name in ("API", "Web App", "Checkout", "Infrastructure"):
            component = project.components.filter(name=name).first()
            if component is None:
                component = create_component(actor=project.owner, project=project, name=name)
                self.stdout.write(f"  + component {name}")
            components[name] = component
        return components

    def _seed_tickets(self, project: Project, users: dict[str, User], components) -> None:
        reporter = users["reporter@example.com"]
        manager = project.owner

        for spec in DEMO_TICKETS:
            if Ticket.objects.filter(project=project, title=spec["title"]).exists():
                continue

            assignee = users.get(spec["assignee"]) if spec["assignee"] else None
            ticket = create_ticket(
                actor=reporter,
                project=project,
                title=spec["title"],
                description=spec["description"],
                type=spec["type"],
                priority=spec["priority"],
                severity=spec["severity"],
                component=components[spec["component"]],
            )
            if assignee is not None:
                assign_ticket(actor=manager, ticket=ticket, assignee=assignee)

            for target in spec["journey"]:
                # REJECTED/DUPLICATE/BLOCKED/REOPENED require a reason; give the demo one.
                comment = ""
                if target in {TicketStatus.BLOCKED, TicketStatus.REJECTED, TicketStatus.DUPLICATE}:
                    comment = "Seeded demo reason."
                transition_ticket(ticket=ticket, to_status=target, actor=manager, comment=comment)

            self.stdout.write(f"  + ticket {ticket.key} ({ticket.status})")

        # One overdue ticket so the dashboard's "overdue" filter has something to show.
        overdue_title = "Investigate elevated p95 latency on the tickets endpoint"
        if not Ticket.objects.filter(project=project, title=overdue_title).exists():
            ticket = create_ticket(
                actor=reporter,
                project=project,
                title=overdue_title,
                description="p95 latency doubled after the last release; dashboard and list endpoints affected.",
                type=TicketType.BUG,
                priority=Priority.HIGH,
                severity=Severity.MAJOR,
                component=components["API"],
                due_date=timezone.localdate() - timedelta(days=3),
            )
            # A reporter may file work but may not assign somebody else (FR-4.1); the manager does it.
            assign_ticket(actor=manager, ticket=ticket, assignee=users["engineer2@example.com"])
            transition_ticket(ticket=ticket, to_status=TicketStatus.TRIAGED, actor=manager, comment="")
            self.stdout.write(f"  + ticket {ticket.key} (overdue)")