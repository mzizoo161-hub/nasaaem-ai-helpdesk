"""Identifier-only access to SYNTHETIC test accounts; NOT real authentication."""
from psycopg.rows import dict_row
from prototype_cloud import get_prototype_connection


def authenticate_prototype_employee(phone_number, employee_id):
    phone = str(phone_number).strip()
    emp_id = str(employee_id).strip().upper()
    if not phone or not emp_id:
        return None
    with get_prototype_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('''SELECT id, username, full_name, role, department,
                                  phone_number, employee_id, is_active
                           FROM nasaaem_prototype.users
                           WHERE phone_number = %s AND UPPER(employee_id) = %s
                             AND is_active = TRUE LIMIT 1''', (phone, emp_id))
            return cur.fetchone()
