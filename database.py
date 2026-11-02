
"""Ticket persistence and employee database connections for the local demo.

Employees live in db/employees/employees.db; tickets, requests and
notifications live in db/tickets/tickets.db.
"""

import sqlite3
from pathlib import Path


# =====================================================
# DATABASE PATHS
# =====================================================

PROJECT_DIR = Path(__file__).resolve().parent

DB_PATH = PROJECT_DIR / "db" / "tickets" / "tickets.db"

EMPLOYEE_DB_PATH = (
    PROJECT_DIR / "db" / "employees" / "employees.db"
)


def _require_database(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"Database not found: {path}"
        )


# =====================================================
# ALLOWED DEPARTMENTS
# =====================================================

ALLOWED_DEPARTMENTS = {
    "IT Support",
    "Maintenance",
    "Housekeeping",
    "Warehouse",
    "Purchasing",
    "Reception",
}


# =====================================================
# DATABASE CONNECTIONS
# =====================================================

def _connect(path: Path) -> sqlite3.Connection:

    _require_database(path)

    connection = sqlite3.connect(
        path,
        timeout=30,
    )

    connection.execute(
        "PRAGMA busy_timeout = 30000"
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def get_connection() -> sqlite3.Connection:
    """
    Backward-compatible connection for ticket operations.
    """
    return _connect(DB_PATH)


def get_ticket_connection() -> sqlite3.Connection:
    """
    Connect to tickets.db.
    """
    return _connect(DB_PATH)


def get_employee_connection() -> sqlite3.Connection:
    """
    Connect to employees.db.
    """
    return _connect(EMPLOYEE_DB_PATH)


# =====================================================
# INITIALIZE TICKETS DATABASE
# =====================================================

def initialize_database() -> None:
    """
    Create missing ticket-side tables without deleting
    or modifying existing records.
    """

    with get_ticket_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                original_message TEXT NOT NULL,
                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                department TEXT NOT NULL,
                location TEXT,
                routing_decision TEXT NOT NULL
                    DEFAULT 'ROUTE',
                status TEXT NOT NULL DEFAULT 'New',
                assigned_to TEXT,
                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (request_id)
                    REFERENCES requests(id)
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_tickets_department
            ON tickets(department, status)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_requests_employee
            ON requests(employee_id)
            """
        )

        # The employees table is in a different
        # SQLite file, so user_id is stored without
        # a cross-database foreign key.

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ticket_id INTEGER,
                title TEXT NOT NULL,
                message TEXT NOT NULL,

                is_read INTEGER NOT NULL DEFAULT 0
                    CHECK (is_read IN (0, 1)),

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (ticket_id)
                    REFERENCES tickets(id)
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_notifications_user_read
            ON notifications(user_id, is_read)
            """
        )


# =====================================================
# CREATE REQUEST + TICKETS + NOTIFICATIONS
# =====================================================

def create_request_with_tickets(
    employee_id: str,
    original_message: str,
    issues: list[dict],
) -> int:
    """
    Save a request, its tickets, and notifications
    in one ticket-database transaction.

    Employee recipients are read from employees.db.
    """

    if (
        not isinstance(employee_id, str)
        or not employee_id.strip()
    ):
        raise ValueError(
            "Employee ID is required."
        )

    if (
        not isinstance(original_message, str)
        or not original_message.strip()
    ):
        raise ValueError(
            "Original message is required."
        )

    if not isinstance(issues, list) or not issues:
        raise ValueError(
            "At least one issue is required."
        )

    # Validate all issues before writing data.

    for issue in issues:

        if not isinstance(issue, dict):
            raise ValueError(
                "Each issue must be a dictionary."
            )

        if issue.get("routing_decision") != "ROUTE":
            raise ValueError(
                "Only ROUTE issues can be saved."
            )

        if issue.get("department") not in ALLOWED_DEPARTMENTS:
            raise ValueError(
                f"Invalid department: "
                f"{issue.get('department')!r}"
            )

        for field in ("description", "category"):

            value = issue.get(field)

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"Invalid field: {field}"
                )

        if (
            issue.get("location") is not None
            and not isinstance(
                issue["location"],
                str,
            )
        ):
            raise ValueError(
                "Invalid location."
            )

    # Read employees from the attached database.
    # Write requests, tickets, and notifications
    # to tickets.db only.

    _require_database(EMPLOYEE_DB_PATH)

    with get_ticket_connection() as connection:

        connection.execute(
            """
            ATTACH DATABASE ? AS employee_directory
            """,
            (str(EMPLOYEE_DB_PATH),),
        )

        cursor = connection.execute(
            """
            INSERT INTO requests (
                employee_id,
                original_message
            )
            VALUES (?, ?)
            """,
            (
                employee_id.strip(),
                original_message.strip(),
            ),
        )

        request_id = cursor.lastrowid

        for issue in issues:

            cursor = connection.execute(
                """
                INSERT INTO tickets (
                    request_id,
                    description,
                    category,
                    department,
                    location,
                    routing_decision,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    issue["description"].strip(),
                    issue["category"].strip(),
                    issue["department"],
                    issue.get("location"),
                    "ROUTE",
                    "New",
                ),
            )

            ticket_id = cursor.lastrowid
            department = issue["department"]

            # Find active employees in the
            # department associated with the ticket.

            recipients = connection.execute(
                """
                SELECT id
                FROM employee_directory.users
                WHERE department = ?
                  AND is_active = 1
                  AND role IN ('Employee', 'Staff')
                """,
                (department,),
            ).fetchall()

            # Create one notification per employee.

            connection.executemany(
                """
                INSERT INTO notifications (
                    user_id,
                    ticket_id,
                    title,
                    message
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        recipient[0],
                        ticket_id,
                        "New Ticket",
                        f"Ticket #{ticket_id} "
                        f"has been created for {department}.",
                    )
                    for recipient in recipients
                ],
            )

    return request_id


# =====================================================
# GET DEPARTMENT TICKETS
# =====================================================

def get_department_tickets(
    department: str,
) -> list[dict]:

    if department not in ALLOWED_DEPARTMENTS:
        raise ValueError(
            "Invalid department."
        )

    with get_ticket_connection() as connection:

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                request_id,
                description,
                category,
                department,
                location,
                routing_decision,
                status,
                assigned_to,
                created_at
            FROM tickets
            WHERE department = ?
            ORDER BY id DESC
            """,
            (department,),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# =====================================================
# GET EMPLOYEE TICKETS
# =====================================================

def get_employee_tickets(
    employee_id: str,
) -> list[dict]:

    if (
        not isinstance(employee_id, str)
        or not employee_id.strip()
    ):
        raise ValueError(
            "Employee ID is required."
        )

    with get_ticket_connection() as connection:

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                t.id,
                t.request_id,
                t.description,
                t.category,
                t.department,
                t.location,
                t.routing_decision,
                t.status,
                t.assigned_to,
                t.created_at
            FROM tickets AS t

            JOIN requests AS r
                ON r.id = t.request_id

            WHERE r.employee_id = ?

            ORDER BY t.id DESC
            """,
            (employee_id.strip(),),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# =====================================================
# CLAIM TICKET
# =====================================================

def claim_ticket(
    ticket_id: int,
    employee_id: str,
    department: str,
) -> bool:
    """
    Claim an unassigned New or Reopened ticket.
    """

    if department not in ALLOWED_DEPARTMENTS:
        raise ValueError(
            "Invalid department."
        )

    if (
        not isinstance(employee_id, str)
        or not employee_id.strip()
    ):
        raise ValueError(
            "Employee ID is required."
        )

    with get_ticket_connection() as connection:

        cursor = connection.execute(
            """
            UPDATE tickets

            SET
                status = 'In Progress',
                assigned_to = ?

            WHERE id = ?
              AND department = ?
              AND status IN ('New', 'Reopened')
              AND assigned_to IS NULL
            """,
            (
                employee_id.strip(),
                ticket_id,
                department,
            ),
        )

        return cursor.rowcount == 1


# =====================================================
# MARK TICKET COMPLETED
# =====================================================

def mark_ticket_completed(
    ticket_id: int,
    employee_id: str,
    department: str,
) -> bool:
    """
    Only the assigned worker can submit a ticket
    for requester confirmation.
    """

    if department not in ALLOWED_DEPARTMENTS:
        raise ValueError(
            "Invalid department."
        )

    if (
        not isinstance(employee_id, str)
        or not employee_id.strip()
    ):
        raise ValueError(
            "Employee ID is required."
        )

    with get_ticket_connection() as connection:

        cursor = connection.execute(
            """
            UPDATE tickets

            SET status = 'Pending Confirmation'

            WHERE id = ?
              AND department = ?
              AND status = 'In Progress'
              AND assigned_to = ?
            """,
            (
                ticket_id,
                department,
                employee_id.strip(),
            ),
        )

        return cursor.rowcount == 1


# =====================================================
# CONFIRM TICKET - YES / NO
# =====================================================

def confirm_ticket(
    ticket_id: int,
    employee_id: str,
    solved: bool,
) -> bool:
    """
    Only the original requester may resolve
    or reopen a pending ticket.
    """

    if type(solved) is not bool:
        raise ValueError(
            "solved must be True or False."
        )

    if (
        not isinstance(employee_id, str)
        or not employee_id.strip()
    ):
        raise ValueError(
            "Employee ID is required."
        )

    new_status = (
        "Resolved"
        if solved
        else "Reopened"
    )

    with get_ticket_connection() as connection:

        cursor = connection.execute(
            """
            UPDATE tickets

            SET
                status = ?,

                assigned_to = CASE
                    WHEN ? = 'Reopened'
                    THEN NULL
                    ELSE assigned_to
                END

            WHERE id = ?
              AND status = 'Pending Confirmation'

              AND EXISTS (
                  SELECT 1
                  FROM requests

                  WHERE requests.id = tickets.request_id
                    AND requests.employee_id = ?
              )
            """,
            (
                new_status,
                new_status,
                ticket_id,
                employee_id.strip(),
            ),
        )

        return cursor.rowcount == 1


# =====================================================
# LEGACY FUNCTION
# =====================================================

def resolve_ticket(
    ticket_id: int,
    employee_id: str,
    department: str,
) -> bool:
    """
    Keep compatibility with older project files.
    Now sends a ticket for requester confirmation.
    """

    return mark_ticket_completed(
        ticket_id,
        employee_id,
        department,
    )


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    initialize_database()

    print(
        "Database initialized successfully!"
    )

    print(
        f"Tickets database: {DB_PATH}"
    )

    print(
        f"Employees database: {EMPLOYEE_DB_PATH}"
    )

    print(
        "New Ticket -> Department Notifications"
    )

    print(
        "New -> In Progress -> Pending Confirmation"
    )

    print(
        "YES -> Resolved | NO -> Reopened"
    )
