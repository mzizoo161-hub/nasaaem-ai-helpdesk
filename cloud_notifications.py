"""
Nasaaem AI Helpdesk
Cloud Notifications — Synthetic Demo

Phase 1: Read-only notification operations.
"""

from psycopg.rows import dict_row

from cloud_database import get_app_connection


def _validate_demo_user(user_id: int) -> int:
    """
    Accept only the synthetic cloud employee.

    This is a demo data restriction,
    not secure authentication.
    """
    if isinstance(user_id, bool):
        raise ValueError("Invalid user ID.")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid user ID.") from None

    with get_app_connection() as conn:
        row = conn.execute("""
            SELECT id
            FROM employees.users
            WHERE id = %s
              AND employee_id = 'TEST001'
              AND is_active = TRUE
        """, (user_id,)).fetchone()

    if row is None:
        raise ValueError("Synthetic demo user not found.")

    return user_id


def get_cloud_user_notifications(user_id: int) -> list[dict]:
    """
    Retrieve visible notifications for a demo user.
    """
    user_id = _validate_demo_user(user_id)

    with get_app_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT
                    id,
                    ticket_id,
                    title,
                    message,
                    is_read,
                    created_at
                FROM helpdesk.notifications
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
            """, (user_id,))

            return cursor.fetchall()


def get_cloud_unread_count(user_id: int) -> int:
    """
    Count unread demo notifications.
    """
    user_id = _validate_demo_user(user_id)

    with get_app_connection() as conn:
        return conn.execute("""
            SELECT COUNT(*)
            FROM helpdesk.notifications
            WHERE user_id = %s
              AND is_read = FALSE
        """, (user_id,)).fetchone()[0]


if __name__ == "__main__":
    print("=== NASAAEM CLOUD NOTIFICATIONS TEST ===")

    from cloud_employees import authenticate_cloud_employee

    employee = authenticate_cloud_employee(
        "01000000000",
        "TEST001",
    )

    if employee is None:
        raise SystemExit("Synthetic demo login failed.")

    user_id = employee["id"]

    notifications = get_cloud_user_notifications(user_id)
    unread = get_cloud_unread_count(user_id)

    print("NOTIFICATIONS:", len(notifications))
    print("UNREAD:", unread)
    print("READ FUNCTIONS: PASS")
    print("DATABASE WRITES: NONE")
    print("STEP 222: PASS")


def mark_cloud_notification_read(
    notification_id: int,
    user_id: int,
) -> bool:
    """
    Mark a synthetic-demo notification as read.

    Returns True if exactly one unread notification
    was updated, otherwise False.

    The caller must separately enforce authorization.
    """

    user_id = _validate_demo_user(user_id)

    if isinstance(notification_id, bool):
        return False

    try:
        notification_id = int(notification_id)
    except (TypeError, ValueError):
        return False

    if notification_id <= 0:
        return False

    with get_app_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE helpdesk.notifications
            SET is_read = TRUE
            WHERE id = %s
              AND user_id = %s
              AND is_read = FALSE
            """,
            (notification_id, user_id),
        )

        return cursor.rowcount == 1
