"""
Nasaaem AI Helpdesk
Cloud Ticket Management — Synthetic Demo

Phase 1: Validate requests before writing to Supabase.
"""

from database import ALLOWED_DEPARTMENTS


def validate_cloud_request(
    employee_id: str,
    original_message: str,
    issues: list[dict],
) -> None:
    """
    Validate synthetic-demo requests.

    This function does not access or modify
    the cloud database.
    """

    if employee_id != "TEST001":
        raise ValueError(
            "Cloud demo only accepts TEST001."
        )

    if (
        not isinstance(original_message, str)
        or not 1 <= len(original_message.strip()) <= 2000
    ):
        raise ValueError(
            "Message must contain 1–2000 characters."
        )

    if not isinstance(issues, list) or not issues:
        raise ValueError(
            "At least one issue is required."
        )

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
                "Invalid department."
            )

        for field in ("description", "category"):
            value = issue.get(field)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Invalid issue field: {field}"
                )

        location = issue.get("location")

        if location is not None and not isinstance(location, str):
            raise ValueError(
                "Location must be text or None."
            )


if __name__ == "__main__":

    print("=== NASAAEM CLOUD REQUEST VALIDATION ===")

    valid_issues = [{
        "description": "Synthetic printer issue",
        "category": "Printer Issue",
        "department": "IT Support",
        "location": "Reception",
        "routing_decision": "ROUTE",
    }]

    validate_cloud_request(
        "TEST001",
        "Synthetic demo: printer not working.",
        valid_issues,
    )
    print("VALID REQUEST: PASS")

    try:
        validate_cloud_request(
            "OTHER001",
            "Synthetic request",
            valid_issues,
        )
    except ValueError:
        print("INVALID EMPLOYEE REJECTED: PASS")
    else:
        print("INVALID EMPLOYEE REJECTED: FAIL")

    try:
        validate_cloud_request(
            "TEST001",
            "Synthetic medical equipment issue",
            [{
                **valid_issues[0],
                "routing_decision": "REVIEW",
            }],
        )
    except ValueError:
        print("REVIEW ISSUE REJECTED: PASS")
    else:
        print("REVIEW ISSUE REJECTED: FAIL")

    print("TEST COMPLETED")


def create_cloud_request_with_tickets(
    employee_id: str,
    original_message: str,
    issues: list[dict],
) -> int:
    """
    Create a synthetic request, tickets, and
    notifications in one PostgreSQL transaction.

    This function is for private demo testing only.
    """

    from cloud_database import get_app_connection

    validate_cloud_request(
        employee_id,
        original_message,
        issues,
    )

    # Our current notification RLS policy permits
    # IT Support tickets for TEST001 only.
    # Reject other departments until their demo
    # notification policies are designed.
    if any(
        issue["department"] != "IT Support"
        for issue in issues
    ):
        raise ValueError(
            "Cloud demo currently supports "
            "IT Support tickets only."
        )

    # The connection context commits on success
    # and rolls back if an exception occurs.
    with get_app_connection() as conn:

        request_id = conn.execute(
            """
            INSERT INTO helpdesk.requests (
                employee_id,
                original_message
            )
            VALUES (%s, %s)
            RETURNING id
            """,
            (
                employee_id,
                original_message.strip(),
            ),
        ).fetchone()[0]

        for issue in issues:

            ticket_id = conn.execute(
                """
                INSERT INTO helpdesk.tickets (
                    request_id,
                    description,
                    category,
                    department,
                    location,
                    routing_decision,
                    status
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                RETURNING id
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
            ).fetchone()[0]

            # Notify the permitted synthetic
            # IT Support employee.
            conn.execute(
                """
                INSERT INTO helpdesk.notifications (
                    user_id,
                    ticket_id,
                    title,
                    message
                )
                SELECT
                    id,
                    %s,
                    'New Ticket',
                    %s
                FROM employees.users
                WHERE employee_id = 'TEST001'
                  AND department = 'IT Support'
                  AND is_active = TRUE
                """,
                (
                    ticket_id,
                    f"Ticket #{ticket_id} "
                    "has been created for IT Support.",
                ),
            )

    return request_id


def get_cloud_employee_tickets(
    employee_id: str,
) -> list[dict]:
    """
    Read tickets submitted by our synthetic
    demo employee.

    The database RLS policy also restricts
    which tickets the application role can see.
    """

    from psycopg.rows import dict_row
    from cloud_database import get_app_connection

    if employee_id != "TEST001":
        raise ValueError(
            "Cloud demo only accepts TEST001."
        )

    with get_app_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
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
                FROM helpdesk.tickets AS t
                JOIN helpdesk.requests AS r
                    ON r.id = t.request_id
                WHERE r.employee_id = %s
                ORDER BY t.id DESC
            """, (employee_id,))

            return cursor.fetchall()


def get_cloud_department_tickets(
    department: str,
) -> list[dict]:
    """
    Read synthetic-demo tickets belonging
    to the specified department.

    This function is a data query, not a
    replacement for authorization checks.
    """

    from psycopg.rows import dict_row
    from cloud_database import get_app_connection

    if department not in ALLOWED_DEPARTMENTS:
        raise ValueError(
            "Invalid department."
        )

    with get_app_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
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
                FROM helpdesk.tickets
                WHERE department = %s
                ORDER BY id DESC
            """, (department,))

            return cursor.fetchall()


def claim_cloud_ticket(
    ticket_id: int,
    employee_id: str,
    department: str,
) -> bool:
    """
    Claim a synthetic-demo ticket.

    This is a demo workflow, not secure
    employee identity verification.
    """

    from cloud_database import get_app_connection

    if employee_id != "TEST001":
        raise ValueError(
            "Cloud demo only accepts TEST001."
        )

    if department != "IT Support":
        raise ValueError(
            "Cloud demo currently supports IT Support only."
        )

    if isinstance(ticket_id, bool):
        return False

    try:
        ticket_id = int(ticket_id)
    except (TypeError, ValueError):
        return False

    if ticket_id <= 0:
        return False

    with get_app_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE helpdesk.tickets
            SET
                status = 'In Progress',
                assigned_to = %s
            WHERE id = %s
              AND department = %s
              AND status IN ('New', 'Reopened')
              AND assigned_to IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM helpdesk.requests r
                  WHERE r.id = helpdesk.tickets.request_id
                    AND r.employee_id = 'TEST001'
              )
            """,
            (
                employee_id,
                ticket_id,
                department,
            ),
        )

        return cursor.rowcount == 1


def mark_cloud_ticket_completed(
    ticket_id: int,
    employee_id: str,
    department: str,
) -> bool:
    """
    Move an assigned synthetic-demo ticket
    from In Progress to Pending Confirmation.

    Employee identity is not independently verified.
    """

    from cloud_database import get_app_connection

    if employee_id != "TEST001":
        raise ValueError(
            "Cloud demo only accepts TEST001."
        )

    if department != "IT Support":
        raise ValueError(
            "Cloud demo currently supports IT Support only."
        )

    if isinstance(ticket_id, bool):
        return False

    try:
        ticket_id = int(ticket_id)
    except (TypeError, ValueError):
        return False

    if ticket_id <= 0:
        return False

    with get_app_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE helpdesk.tickets
            SET status = 'Pending Confirmation'
            WHERE id = %s
              AND department = %s
              AND status = 'In Progress'
              AND assigned_to = %s
              AND EXISTS (
                  SELECT 1
                  FROM helpdesk.requests r
                  WHERE r.id = helpdesk.tickets.request_id
                    AND r.employee_id = 'TEST001'
              )
            """,
            (
                ticket_id,
                department,
                employee_id,
            ),
        )

        return cursor.rowcount == 1


def confirm_cloud_ticket(
    ticket_id: int,
    employee_id: str,
    solved: bool,
) -> bool:
    """
    Confirm resolution or reopen a synthetic demo ticket.

    This function checks the request's employee ID,
    but phone + employee ID is not secure authentication.
    """

    from cloud_database import get_app_connection

    if type(solved) is not bool:
        raise ValueError("solved must be True or False.")

    if employee_id != "TEST001":
        raise ValueError(
            "Cloud demo only accepts TEST001."
        )

    if isinstance(ticket_id, bool):
        return False

    try:
        ticket_id = int(ticket_id)
    except (TypeError, ValueError):
        return False

    if ticket_id <= 0:
        return False

    new_status = "Resolved" if solved else "Reopened"

    with get_app_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE helpdesk.tickets
            SET
                status = %s,
                assigned_to = CASE
                    WHEN %s = 'Reopened'
                    THEN NULL
                    ELSE assigned_to
                END
            WHERE id = %s
              AND department = 'IT Support'
              AND status = 'Pending Confirmation'
              AND EXISTS (
                  SELECT 1
                  FROM helpdesk.requests r
                  WHERE r.id = helpdesk.tickets.request_id
                    AND r.employee_id = %s
              )
            """,
            (
                new_status,
                new_status,
                ticket_id,
                employee_id,
            ),
        )

        return cursor.rowcount == 1
