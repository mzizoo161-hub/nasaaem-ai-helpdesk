"""
Nasaaem AI Helpdesk
Cloud Employee Management — Phase 1

Read-only PostgreSQL employee directory functions.

All database access uses the restricted application role.
"""

from psycopg.rows import dict_row

from cloud_database import get_app_connection


def get_all_employees():
    """
    Return employees visible through the current
    restricted PostgreSQL connection.

    This function must only be called from an
    authorized Admin workflow.
    """

    with get_app_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:

            cursor.execute("""
                SELECT
                    id,
                    username,
                    full_name,
                    phone_number,
                    employee_id,
                    department,
                    role,
                    is_active,
                    created_at
                FROM employees.users
                ORDER BY id
            """)

            return cursor.fetchall()


def get_employee_by_id(user_id):
    """
    Find one employee using the internal
    database ID.
    """

    with get_app_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:

            cursor.execute("""
                SELECT
                    id,
                    username,
                    full_name,
                    phone_number,
                    employee_id,
                    department,
                    role,
                    is_active
                FROM employees.users
                WHERE id = %s
            """, (user_id,))

            return cursor.fetchone()


def get_employee_count():
    """
    Count employees visible to the application role.
    """

    with get_app_connection() as conn:
        return conn.execute("""
            SELECT COUNT(*)
            FROM employees.users
        """).fetchone()[0]


if __name__ == "__main__":

    print("=== NASAAEM CLOUD EMPLOYEE MODULE ===")

    employees = get_all_employees()

    print("VISIBLE EMPLOYEES:", len(employees))

    for employee in employees:
        print(
            employee["full_name"],
            "|",
            employee["department"],
            "|",
            employee["role"],
        )

    print("EMPLOYEE COUNT:", get_employee_count())

    if employees:
        found = get_employee_by_id(
            employees[0]["id"]
        )

        print(
            "LOOKUP:",
            "SUCCESS" if found else "FAILED"
        )

    print("TEST COMPLETED")


def authenticate_cloud_employee(
    phone_number: str,
    employee_id: str,
) -> dict | None:
    """
    Synthetic-data demo login only.

    Phone number + employee ID are identifiers,
    not secure authentication credentials.
    """

    from auth import (
        normalize_phone_number,
        normalize_employee_id,
    )

    try:
        phone = normalize_phone_number(phone_number)
        hospital_id = normalize_employee_id(employee_id)
    except ValueError:
        return None

    with get_app_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    full_name,
                    role,
                    department
                FROM employees.users
                WHERE phone_number = %s
                  AND employee_id = %s
                  AND is_active = TRUE
                LIMIT 1
                """,
                (phone, hospital_id),
            )

            return cursor.fetchone()


def load_cloud_user(user_id: int) -> dict | None:
    """
    Load an active synthetic-demo employee
    from the restricted cloud database.

    This is a database lookup, not an
    independent authorization check.
    """

    if isinstance(user_id, bool):
        return None

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    with get_app_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    full_name,
                    role,
                    department,
                    is_active
                FROM employees.users
                WHERE id = %s
                  AND is_active = TRUE
                LIMIT 1
                """,
                (user_id,),
            )

            return cursor.fetchone()
