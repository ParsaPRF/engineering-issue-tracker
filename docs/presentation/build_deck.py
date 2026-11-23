"""Build the defence deck for the Engineering Issue & Ticket Tracking System.

Run with the bundled runtime:

    "C:/Users/parsa/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe" \
        docs/presentation/build_deck.py

Output: docs/presentation/defense-deck.pptx (16:9, editable text/tables, no images).

Design rules applied here:
* one message per slide, stated in the slide title (a reader should get the argument from titles);
* bullets stay short so they do not wrap into the footer; body 16-18pt, titles 28pt;
* every number on a slide is one that was actually produced by a command in this repository
  (238 tests, 4 CI jobs, 19 declared transitions, 9 modules, 10 statuses);
* no images: everything is text and native tables, so it stays editable in PowerPoint.
"""

from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = "docs/presentation/defense-deck.pptx"

INK = RGBColor(0x0F, 0x17, 0x2A)
MUTED = RGBColor(0x47, 0x55, 0x69)
ACCENT = RGBColor(0x25, 0x63, 0xEB)
ACCENT_SOFT = RGBColor(0xEF, 0xF6, 0xFF)
LINE = RGBColor(0xE2, 0xE8, 0xF0)
GREEN = RGBColor(0x05, 0x96, 0x69)
AMBER = RGBColor(0xB4, 0x53, 0x09)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

LEFT = Inches(0.7)
WIDTH = Inches(11.93)
BODY_TOP = Inches(1.75)


def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def rect(slide, left, top, width, height, fill=None, line=None, line_width=Pt(1)):
    from pptx.enum.shapes import MSO_SHAPE

    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.adjustments[0] = 0.06
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = line_width
    shape.shadow.inherit = False
    return shape


def text(slide, value, left, top, width, height, size=16, bold=False, color=INK, align=PP_ALIGN.LEFT,
         line_spacing=1.15, space_after=0):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    paragraph.line_spacing = line_spacing
    paragraph.space_after = Pt(space_after)
    run = paragraph.add_run()
    run.text = value
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Segoe UI"
    return box


def bullets(slide, items, left, top, width, height, size=17, color=INK, space_after=10, bullet_color=ACCENT):
    """Items are strings, or (text, level) tuples for a second level."""
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    first = True
    for item in items:
        value, level = (item, 0) if isinstance(item, str) else item
        paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
        first = False
        paragraph.level = level
        paragraph.space_after = Pt(space_after)
        paragraph.line_spacing = 1.12
        marker = "•" if level == 0 else "–"
        bullet_run = paragraph.add_run()
        bullet_run.text = f"{'    ' * level}{marker}  "
        bullet_run.font.size = Pt(size)
        bullet_run.font.bold = True
        bullet_run.font.color.rgb = bullet_color if level == 0 else MUTED
        bullet_run.font.name = "Segoe UI"
        run = paragraph.add_run()
        run.text = value
        run.font.size = Pt(size if level == 0 else size - 2)
        run.font.color.rgb = color if level == 0 else MUTED
        run.font.name = "Segoe UI"
    return box


def header(slide, kicker: str, title: str, index: int, total: int) -> None:
    bar = slide.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(0.09))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False

    # Long titles shrink instead of wrapping into the rule below them. python-pptx cannot measure
    # text, so this is the deterministic part of the layout: one line, always.
    title_size = 27 if len(title) <= 58 else (24 if len(title) <= 70 else 21)

    text(slide, kicker.upper(), LEFT, Inches(0.42), WIDTH, Inches(0.3), size=11, bold=True, color=ACCENT)
    text(slide, title, LEFT, Inches(0.72), WIDTH, Inches(0.8), size=title_size, bold=True, color=INK)

    line = slide.shapes.add_shape(1, LEFT, Inches(1.52), WIDTH, Emu(9525))
    line.fill.solid()
    line.fill.fore_color.rgb = LINE
    line.line.fill.background()
    line.shadow.inherit = False

    text(slide, "Engineering Issue & Ticket Tracking System", LEFT, Inches(7.02), Inches(8), Inches(0.3),
         size=10, color=MUTED)
    text(slide, f"{index} / {total}", Inches(11.4), Inches(7.02), Inches(1.2), Inches(0.3),
         size=10, color=MUTED, align=PP_ALIGN.RIGHT)


def table(slide, rows, left, top, width, col_widths, header_row=True, size=12, row_height=Inches(0.34)):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), left, top, width, row_height * len(rows))
    tbl = shape.table
    for index, fraction in enumerate(col_widths):
        tbl.columns[index].width = Emu(int(width * fraction))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = ""
            frame = cell.text_frame
            frame.word_wrap = True
            paragraph = frame.paragraphs[0]
            paragraph.space_after = Pt(0)
            run = paragraph.add_run()
            run.text = str(value)
            run.font.size = Pt(size)
            run.font.name = "Segoe UI"
            run.font.bold = header_row and r == 0
            run.font.color.rgb = WHITE if (header_row and r == 0) else INK
            cell.fill.solid()
            cell.fill.fore_color.rgb = ACCENT if (header_row and r == 0) else (
                ACCENT_SOFT if r % 2 == 0 else WHITE
            )
            cell.margin_left = Inches(0.09)
            cell.margin_right = Inches(0.09)
            cell.margin_top = Inches(0.04)
            cell.margin_bottom = Inches(0.04)
    return tbl


prs = new_deck()
TOTAL = 14
# The title slide counts as 1 even though it has no footer, otherwise every page number is off by one.
index = 1


def next_slide(kicker: str, title: str):
    global index
    index += 1
    slide = blank(prs)
    header(slide, kicker, title, index, TOTAL)
    return slide


# --------------------------------------------------------------------------- 1
slide = blank(prs)
band = slide.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
band.fill.solid()
band.fill.fore_color.rgb = INK
band.line.fill.background()
band.shadow.inherit = False

text(slide, "COURSE PROJECT · SOFTWARE ENGINEERING", LEFT, Inches(1.5), WIDTH, Inches(0.4),
     size=13, bold=True, color=RGBColor(0x93, 0xC5, 0xFD))
text(slide, "Engineering Issue &\nTicket Tracking System", LEFT, Inches(2.0), Inches(9.5), Inches(1.9),
     size=44, bold=True, color=WHITE, line_spacing=1.05)
text(slide, "A modular-monolith backend in Django REST Framework, a React/TypeScript SPA,\n"
           "and the documentation and tests that defend every decision.",
     LEFT, Inches(4.15), Inches(10.5), Inches(0.9), size=17, color=RGBColor(0xCB, 0xD5, 0xE1))
text(slide, "Amir Parsa Fatholahi", LEFT, Inches(5.5), Inches(6), Inches(0.4), size=16, bold=True, color=WHITE)
text(slide, "github.com/ParsaPRF/engineering-issue-tracker   ·   238 tests on PostgreSQL   ·   4/4 CI jobs",
     LEFT, Inches(5.95), Inches(11), Inches(0.4), size=13, color=RGBColor(0x93, 0xC5, 0xFD))

# --------------------------------------------------------------------------- 2
slide = next_slide("Problem", "A team cannot see its own work — and cannot prove what happened")
bullets(slide, [
    "Work arrives from everywhere: bugs, features, support, change requests.",
    "Nobody knows who is doing what, or what is blocked and why.",
    "Status changes happen in chat, so the history of a ticket is a rumour.",
    "Attachments with customer data live in group chats and public links.",
], LEFT, BODY_TOP, Inches(6.6), Inches(3.2), size=17)

rect(slide, Inches(7.7), BODY_TOP, Inches(4.9), Inches(3.6), fill=ACCENT_SOFT, line=LINE)
text(slide, "What the system must guarantee", Inches(8.0), Inches(1.95), Inches(4.3), Inches(0.4),
     size=15, bold=True, color=ACCENT)
bullets(slide, [
    "One project-scoped place for all work",
    "A lifecycle only the server may move",
    "Collaboration with access control on files",
    "An audit trail nobody can rewrite",
], Inches(8.0), Inches(2.45), Inches(4.35), Inches(2.6), size=14, space_after=8)

text(slide, "Scope chosen: 9 modules · 4 system roles · 3 project roles · 10 ticket statuses · 19 legal transitions",
     LEFT, Inches(5.55), Inches(11.6), Inches(0.5), size=15, bold=True, color=ACCENT)

# --------------------------------------------------------------------------- 3
slide = next_slide("Delivered", "Nine bounded contexts, each owning its models, rules, API and tests")
modules = [
    ("accounts", "users, roles, session auth, profiles"),
    ("projects", "projects, memberships, components, permissions"),
    ("tickets", "tickets, labels, key allocation, assignment"),
    ("workflows", "state machine, transitions, status timeline"),
    ("comments", "discussion with edit window and moderation"),
    ("attachments", "private files, validated and access-controlled"),
    ("notifications", "in-app inbox, Celery delivery, dedupe"),
    ("audit", "append-only trail across every module"),
    ("reports", "dashboard, workload, activity (read-only)"),
]
for i, (name, purpose) in enumerate(modules):
    col, row = i % 3, i // 3
    left = Inches(0.7 + col * 4.02)
    top = Inches(1.85 + row * 1.5)
    rect(slide, left, top, Inches(3.8), Inches(1.25), fill=WHITE, line=LINE)
    text(slide, name, left + Inches(0.2), top + Inches(0.16), Inches(3.4), Inches(0.35),
         size=15, bold=True, color=ACCENT)
    text(slide, purpose, left + Inches(0.2), top + Inches(0.55), Inches(3.45), Inches(0.6),
         size=12, color=MUTED)

text(slide, "Frontend: 13 screens (React 19 + TypeScript + Vite) · Infrastructure: Docker Compose, Nginx, PostgreSQL, Redis, Celery, S3-compatible storage",
     LEFT, Inches(6.35), Inches(11.9), Inches(0.5), size=12, color=MUTED)

# --------------------------------------------------------------------------- 4
slide = next_slide("Architecture", "Four layers, one direction: API → services → selectors → models")
layers = [
    ("Presentation  ·  apps/*/api/", "validate shape, call a service, choose a status code", ACCENT_SOFT),
    ("Application  ·  apps/*/services/", "own the transaction, check permission, write audit + notification", WHITE),
    ("Query  ·  apps/*/selectors/", "permission-scoped reads with joins, no mutation", ACCENT_SOFT),
    ("Data  ·  apps/*/models/", "schema, constraints, single-row invariants", WHITE),
]
for i, (name, detail, fill) in enumerate(layers):
    top = Inches(1.8 + i * 1.05)
    rect(slide, LEFT, top, Inches(7.1), Inches(0.9), fill=fill, line=LINE)
    text(slide, name, LEFT + Inches(0.22), top + Inches(0.13), Inches(3.3), Inches(0.3), size=14, bold=True)
    text(slide, detail, LEFT + Inches(0.22), top + Inches(0.47), Inches(6.6), Inches(0.3), size=12, color=MUTED)

rect(slide, Inches(8.25), Inches(1.8), Inches(4.35), Inches(4.2), fill=INK)
text(slide, "Why it matters", Inches(8.55), Inches(2.0), Inches(3.8), Inches(0.4), size=15, bold=True, color=WHITE)
bullets(slide, [
    "A rule lives in one place, so the admin, a CLI command and a test cannot bypass it",
    "Views stay thin enough to read in one screen",
    "Cross-module calls go through services, never through a sibling app's models",
], Inches(8.55), Inches(2.5), Inches(3.85), Inches(3.2), size=13, color=RGBColor(0xE2, 0xE8, 0xF0),
    bullet_color=RGBColor(0x93, 0xC5, 0xFD), space_after=10)

# --------------------------------------------------------------------------- 5
slide = next_slide("Decisions", "The choices a reviewer should challenge — and why they were made")
rows = [
    ["Decision", "Chosen", "Rejected alternative (and why)"],
    ["Topology", "Modular monolith", "Microservices: distributed transactions across ticket+workflow+audit"],
    ["Identity", "Session cookie + CSRF", "JWT in browser storage: refresh token readable by any XSS"],
    ["Status writes", "One transition service", "Writable status field: NEW → CLOSED in one request, no actor"],
    ["Lifecycle rules", "Transition table (data)", "if/else in views: impossible to test exhaustively"],
    ["Ticket key", "Lock + unique + retry", "MAX()+1: two requests read the same maximum"],
    ["Attachments", "Private object + authorising view", "Public bucket URL: one shared link leaks customer data"],
    ["Cash: test DB", "SQLite locally, PostgreSQL in CI", "SQLite only: FOR UPDATE silently ignored (see slide 12)"],
]
rows[-1][0] = "Test database"
table(slide, rows, LEFT, BODY_TOP, WIDTH, [0.16, 0.3, 0.54], size=12, row_height=Inches(0.52))
text(slide, "16 ADRs in docs/architecture/architecture-decisions.md — each records context, options, decision and consequences.",
     LEFT, Inches(6.2), WIDTH, Inches(0.4), size=12, color=MUTED)

# --------------------------------------------------------------------------- 6
slide = next_slide("Data model", "Constraints carry the rules that a bug could otherwise break")
rows = [
    ["Entity", "Constraint that matters"],
    ["User", "unique case-insensitive email (lower(email)) — 'Ali@x.com' is not a second account"],
    ["Project", "unique key (case-insensitive); it prefixes every ticket key, so it is immutable"],
    ["ProjectMembership", "unique (project, user) — re-adding a member reactivates the row, never duplicates"],
    ["Component", "unique (project, name); lead must be a member of that project"],
    ["Ticket", "unique key; component must belong to the same project; assignee must be eligible"],
    ["Attachment", "CHECK at least one anchor (ticket or comment) — an orphan file has no permission path"],
    ["TicketStatusHistory", "append-only in code: history.save() on an existing row raises"],
    ["AuditEvent", "append-only: update and delete raise; production revokes the SQL privileges"],
]
table(slide, rows, LEFT, Inches(1.78), WIDTH, [0.2, 0.8], size=12, row_height=Inches(0.47))
text(slide, "Deletion behaviour is explicit everywhere: PROTECT for anything that history points at, SET_NULL where work should continue, CASCADE only inside a ticket.",
     LEFT, Inches(6.35), WIDTH, Inches(0.5), size=12, color=MUTED)

# --------------------------------------------------------------------------- 7
slide = next_slide("Permissions", "Who may do what = system role × membership in that project")
rows = [
    ["Action", "Admin", "Project MANAGER", "Project ENGINEER", "Project REPORTER"],
    ["Create project", "✓", "✓", "—", "—"],
    ["Edit / archive project", "✓", "✓", "—", "—"],
    ["Manage members, components", "✓", "✓", "—", "—"],
    ["Create a ticket", "✓", "✓", "✓", "✓"],
    ["Assign / reassign", "✓", "✓", "self, if unassigned", "—"],
    ["Start / review work", "✓", "✓", "assignee", "—"],
    ["Resolve / close", "✓", "✓", "—", "—"],
    ["Reopen", "✓", "✓", "✓", "✓"],
    ["Read the audit trail", "✓", "—", "—", "—"],
]
table(slide, rows, LEFT, Inches(1.78), Inches(8.4), [0.36, 0.14, 0.24, 0.24, 0.24], size=11,
      row_height=Inches(0.44))

rect(slide, Inches(9.35), Inches(1.78), Inches(3.25), Inches(3.9), fill=ACCENT_SOFT, line=LINE)
text(slide, "Two rules worth stating", Inches(9.6), Inches(1.95), Inches(2.8), Inches(0.3),
     size=13, bold=True, color=ACCENT)
bullets(slide, [
    "One kernel: projects/permissions.py — pure functions used by API, services and tests",
    "A foreign object answers 404, not 403: existence itself is not confirmed",
    "Admin bypasses membership but every action is still audited",
], Inches(9.6), Inches(2.35), Inches(2.85), Inches(3.1), size=12, space_after=8)

# --------------------------------------------------------------------------- 8
slide = next_slide("Workflow", "Status is not a field a client may write — it is a validated process")
text(slide, "NEW → TRIAGED → IN_PROGRESS → IN_REVIEW → RESOLVED → CLOSED      (with REOPENED, BLOCKED, REJECTED, DUPLICATE as documented detours)",
     LEFT, Inches(1.78), WIDTH, Inches(0.5), size=14, bold=True, color=ACCENT)
bullets(slide, [
    "19 declared transitions; each names the project roles allowed to make it",
    "Guards: rejecting, blocking, duplicating and reopening require a written reason",
    "Starting or finishing work requires an assignee — work nobody owns cannot be resolved",
    "POST /tickets/{id}/transitions/ is the only writer; a PATCH carrying status is an error, not a silent no-op",
    "The same transaction appends the timeline row and the audit event, so they cannot disagree",
    "The UI renders buttons from GET /workflows/transitions/ — it cannot offer a move the API would reject",
], LEFT, Inches(2.45), Inches(7.3), Inches(3.6), size=15, space_after=11)

rect(slide, Inches(8.3), Inches(2.45), Inches(4.3), Inches(3.5), fill=WHITE, line=LINE)
text(slide, "Why a table, not if/else", Inches(8.55), Inches(2.62), Inches(3.8), Inches(0.3),
     size=14, bold=True, color=ACCENT)
text(slide, "The service reads the table, the API serves it, and the test derives its expectations from\nit:\n\n"
            "19 declared moves × 3 roles → allowed or 403\n"
            "71 undeclared pairs → 400 invalid_transition\n\n"
            "Adding a status is a few rows, not a hunt for conditions.",
     Inches(8.55), Inches(3.0), Inches(3.8), Inches(2.8), size=12, color=MUTED, line_spacing=1.2)

# --------------------------------------------------------------------------- 9
slide = next_slide("Concurrency", "Two people creating tickets at once must never share a key")
bullets(slide, [
    "Layer 1 — a counter row per project, locked with SELECT … FOR UPDATE and incremented",
    "Layer 2 — the candidate key is checked before it is returned (covers a drifted counter)",
    "Layer 3 — a unique index on Ticket.key is the real guarantee, not the counter",
    "If a writer still loses the race, the IntegrityError is caught, the attempt rolls back to a savepoint, and it retries with the next number",
], LEFT, Inches(1.8), Inches(7.35), Inches(3.6), size=15, space_after=12)

rect(slide, Inches(8.35), Inches(1.8), Inches(4.25), Inches(1.55), fill=ACCENT_SOFT, line=LINE)
text(slide, "Numbers", Inches(8.6), Inches(1.95), Inches(3.7), Inches(0.3), size=13, bold=True, color=ACCENT)
text(slide, "8 threads, 8 tickets\n8 distinct keys, 0 collisions\n(PostgreSQL-only test, runs in CI)",
     Inches(8.6), Inches(2.3), Inches(3.7), Inches(0.9), size=12, color=INK, line_spacing=1.25)

rect(slide, Inches(8.35), Inches(3.5), Inches(4.25), Inches(2.6), fill=WHITE, line=LINE)
text(slide, "Gap tolerance", Inches(8.6), Inches(3.65), Inches(3.7), Inches(0.3), size=13, bold=True, color=ACCENT)
text(slide, "A failed attempt may burn a number, so keys can skip — accepted on purpose: a gap costs\nnothing, a duplicate corrupts references.",
     Inches(8.6), Inches(4.0), Inches(3.7), Inches(1.8), size=12, color=MUTED, line_spacing=1.25)

# --------------------------------------------------------------------------- 10
slide = next_slide("Security", "Every access decision is re-checked on the server, on every path")
rows = [
    ["Threat", "Control implemented"],
    ["Token theft from JavaScript", "Session id in an HttpOnly cookie; no token in localStorage at all"],
    ["Cross-site request forgery", "CSRF cookie + X-CSRFToken, and login/register are csrf_protect (DRF is exempt by default)"],
    ["Reading another project's data", "Querysets start permission-scoped; foreign objects answer 404"],
    ["Stolen or shared file link", "Private bucket, random object key, download only through an authorising view"],
    ["Stored XSS through an upload", "svg/html rejected; downloads forced to attachment + octet-stream"],
    ["Rewriting history", "Audit rows refuse update/delete; production revokes UPDATE/DELETE in SQL"],
    ["Privilege escalation via profile", "system_role is not an accepted field; role change is Admin-only and audited"],
]
table(slide, rows, LEFT, Inches(1.78), WIDTH, [0.28, 0.72], size=12, row_height=Inches(0.5))
text(slide, "Least privilege by default: registration grants the lowest role, every endpoint requires authentication unless it is explicitly opened (health, csrf, login, register, schema).",
     LEFT, Inches(6.2), WIDTH, Inches(0.5), size=12, color=MUTED)

# --------------------------------------------------------------------------- 11
slide = next_slide("Testing", "238 tests on PostgreSQL, zero skips, and a matrix instead of a sample")
rows = [
    ["Suite", "Count", "What it protects"],
    ["accounts", "28", "registration, login, CSRF, session death, escalation, directory"],
    ["projects", "35", "visibility, last-manager invariant, components, IDOR across projects"],
    ["tickets", "52", "creation rules, filtering, ordering, assignment, key allocation"],
    ["workflows", "44", "every declared and undeclared transition, guards, history, audit"],
    ["comments / attachments", "28", "edit window, soft delete, upload validation, download authorisation"],
    ["notifications / audit / reports", "39", "audience, dedupe, immutability, report scoping"],
    ["structure / E2E scripts", "12", "module layout hazards, end-to-end stack verification"],
]
table(slide, rows, LEFT, Inches(1.78), Inches(7.6), [0.34, 0.12, 0.54], size=11, row_height=Inches(0.46))

rect(slide, Inches(8.55), Inches(1.78), Inches(4.05), Inches(3.5), fill=INK)
text(slide, "CI: 4 jobs, every push", Inches(8.8), Inches(1.95), Inches(3.5), Inches(0.3),
     size=14, bold=True, color=WHITE)
bullets(slide, [
    "lint + schema (--fail-on-warn) + migrations check",
    "full suite on PostgreSQL 17, fails if anything is skipped",
    "frontend tsc + production build",
    "the whole compose stack, driven end to end",
], Inches(8.8), Inches(2.4), Inches(3.55), Inches(2.6), size=12,
    color=RGBColor(0xE2, 0xE8, 0xF0), bullet_color=RGBColor(0x93, 0xC5, 0xFD), space_after=9)

text(slide, "docs/development/test-scenarios.md maps every scenario to the test that defends it — and lists, by name, what is not covered.",
     LEFT, Inches(6.3), WIDTH, Inches(0.5), size=12, color=MUTED)

# --------------------------------------------------------------------------- 12
slide = next_slide("Verification", "Running the real stack found seven defects the tests could not")
bullets(slide, [
    "The worker could not start: kombu imports `packaging`, declared only as an optional extra",
    "GET /auth/users/directory/ returned 500 — the endpoint the UI uses had no test at all",
    "The stack claimed PostgreSQL but ran on SQLite: a local .env value leaked into containers",
    "Celery executed inline instead of publishing to Redis (same leak, different variable)",
    "Every /api/ call returned 502 after a backend restart: Nginx cached the old container IP",
    "The API container could never be healthy: the HTTPS redirect answered the probe with 301",
    "beat reported a meaningless `unhealthy` forever: it inherited a gunicorn health check",
], LEFT, Inches(1.78), Inches(7.55), Inches(4.1), size=14, space_after=9)

rect(slide, Inches(8.5), Inches(1.78), Inches(4.1), Inches(4.25), fill=ACCENT_SOFT, line=LINE)
text(slide, "What is proven now", Inches(8.75), Inches(1.95), Inches(3.6), Inches(0.3),
     size=14, bold=True, color=ACCENT)
bullets(slide, [
    "7 services healthy behind Nginx",
    "login + CSRF on one origin",
    "attachment stored in S3 and downloaded byte-identically",
    "the separate worker logs the task as succeeded",
    "anonymous 403, audit 403 for a manager",
    "Now a CI job on every push",
], Inches(8.75), Inches(2.4), Inches(3.6), Inches(3.4), size=12, space_after=8)

text(slide, "A green suite on a different database with different services is not evidence about the running system.",
     LEFT, Inches(6.2), WIDTH, Inches(0.5), size=14, bold=True, color=AMBER)

# --------------------------------------------------------------------------- 13
slide = next_slide("Limitations", "What is not covered — stated here, not discovered later")
rows = [
    ["Not covered", "Why", "How it would be closed"],
    ["Browser rendering / accessibility", "No headless browser run yet", "A Playwright job: login → dashboard → ticket → transition"],
    ["Object persistence across restarts", "Shipped S3 mock keeps objects in memory", "Point AWS_S3_ENDPOINT_URL at MinIO / SeaweedFS / real S3"],
    ["TLS, HSTS, load balancing", "The stack serves plain HTTP by design", "Edge terminator + remove the SSL-redirect override"],
    ["Email / SMS delivery", "In-app only; the transport seam exists", "Implement a sender behind send_notification"],
    ["Load and performance testing", "No k6/Locust run", "Seed 10k tickets, measure p95 on the list endpoint"],
]
table(slide, rows, LEFT, Inches(1.82), WIDTH, [0.27, 0.33, 0.4], size=12, row_height=Inches(0.62))
text(slide, "Every gap is written in docs/development/test-scenarios.md §10 and the deployment guide — a known gap is defensible; a hidden one is not.",
     LEFT, Inches(6.35), WIDTH, Inches(0.5), size=12, color=MUTED)

# --------------------------------------------------------------------------- 14
slide = next_slide("Summary", "Three things worth remembering")
cards = [
    ("One home for every rule", "Services own transactions and permissions; views and serializers only translate HTTP."),
    ("The server is the authority", "Status moves through a validated table; foreign objects are invisible, not forbidden."),
    ("Evidence over claims", "238 tests on PostgreSQL, 4 CI jobs, a script that drives the real stack — and honest limits."),
]
for i, (title, body) in enumerate(cards):
    left = Inches(0.7 + i * 4.02)
    rect(slide, left, Inches(1.85), Inches(3.8), Inches(2.15), fill=WHITE, line=LINE)
    text(slide, f"0{i + 1}", left + Inches(0.22), Inches(2.0), Inches(1), Inches(0.4),
         size=20, bold=True, color=ACCENT)
    text(slide, title, left + Inches(0.22), Inches(2.45), Inches(3.4), Inches(0.4), size=15, bold=True)
    text(slide, body, left + Inches(0.22), Inches(2.9), Inches(3.4), Inches(1.0), size=12, color=MUTED)

text(slide, "Questions — and a live demo if you would like to see the workflow in action.",
     LEFT, Inches(4.35), WIDTH, Inches(0.5), size=18, bold=True, color=INK)
text(slide, "github.com/ParsaPRF/engineering-issue-tracker      docs/architecture · docs/requirements · docs/api · docs/development · docs/learning",
     LEFT, Inches(5.0), WIDTH, Inches(0.4), size=12, color=MUTED)
text(slide, "Key files to open: apps/workflows/state_machine.py · apps/projects/permissions.py · "
            "apps/tickets/services/keys.py · apps/attachments/services.py · scripts/verify_stack.sh",
     LEFT, Inches(5.4), WIDTH, Inches(0.6), size=12, color=ACCENT)

prs.save(OUT)
print(f"saved {OUT} with {len(prs.slides._sldIdLst)} slides")