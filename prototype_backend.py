"""Nasaaem 150-account SYNTHETIC prototype backend, PostgreSQL only.

This module is NOT secure authentication for real employee records. The caller
must use an isolated synthetic-data deployment; two-field login is guessable.
"""
from psycopg.rows import dict_row
from prototype_cloud import get_prototype_connection
from database import ALLOWED_DEPARTMENTS


def _session_user(conn):
    import streamlit as st
    session = st.session_state.get("main_user")
    if not isinstance(session, dict) or not isinstance(session.get("id"), int):
        raise PermissionError("Login required")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, username, role, department, is_active
                       FROM nasaaem_prototype.users WHERE id = %s""", (session["id"],))
        user = cur.fetchone()
    if not user or not user["is_active"] or user["username"] != session.get("username"):
        raise PermissionError("Session no longer valid")
    return user


def _identity(user):
    return f"USER-{user['id']}"


def _require_identity(conn, employee_id):
    user = _session_user(conn)
    if employee_id != _identity(user):
        raise PermissionError("Account mismatch")
    return user


def _require_department(conn, department):
    if department not in ALLOWED_DEPARTMENTS:
        raise ValueError("Invalid department")
    user = _session_user(conn)
    if user["role"] != "Admin" and not (
        user["role"] == "Staff" and user["department"] == department
    ):
        raise PermissionError("Department permission denied")
    return user


def create_request_with_tickets(employee_id, original_message, issues):
    if not isinstance(original_message, str) or not 1 <= len(original_message.strip()) <= 2000:
        raise ValueError("Message should be 1–2000 characters")
    if not isinstance(issues, list) or not issues:
        raise ValueError("At least one issue is required")
    for item in issues:
        if not isinstance(item, dict) or item.get("routing_decision") != "ROUTE":
            raise ValueError("Only ROUTE issues are supported")
        if item.get("department") not in ALLOWED_DEPARTMENTS:
            raise ValueError("Unknown department")
        if not isinstance(item.get("description"), str) or not item["description"].strip():
            raise ValueError("Missing description")
        if not isinstance(item.get("category"), str) or not item["category"].strip():
            raise ValueError("Missing category")
        if len(item["description"]) > 2000 or len(item["category"]) > 300:
            raise ValueError("Issue is too long")
        if item.get("location") is not None and not isinstance(item["location"], str):
            raise ValueError("Invalid location")
    with get_prototype_connection() as conn:
        user = _require_identity(conn, employee_id)
        request_id = conn.execute("""
            INSERT INTO nasaaem_prototype.requests (employee_id, original_message)
            VALUES (%s,%s) RETURNING id
        """, (employee_id, original_message.strip())).fetchone()[0]
        for item in issues:
            department = item["department"]
            ticket_id = conn.execute("""
                INSERT INTO nasaaem_prototype.tickets
                    (request_id, description, category, department, location, routing_decision, status)
                VALUES (%s,%s,%s,%s,%s,'ROUTE','New') RETURNING id
            """, (request_id, item["description"].strip(), item["category"].strip(),
                  department, item.get("location"))).fetchone()[0]
            conn.execute("""
                INSERT INTO nasaaem_prototype.notifications
                    (user_id, ticket_id, title, message)
                SELECT id, %s, 'New Ticket', %s
                FROM nasaaem_prototype.users
                WHERE is_active = TRUE AND role IN ('Staff','Admin')
                  AND (department = %s OR role = 'Admin')
            """, (ticket_id, f"New ticket #{ticket_id} for {department}", department))
    return request_id


def get_employee_tickets(employee_id):
    with get_prototype_connection() as conn:
        _require_identity(conn, employee_id)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT t.id, t.request_id, t.description, t.category, t.department,
                       t.location, t.routing_decision, t.status, t.assigned_to, t.created_at
                FROM nasaaem_prototype.tickets t
                JOIN nasaaem_prototype.requests r ON r.id = t.request_id
                WHERE r.employee_id = %s ORDER BY t.id DESC
            """, (employee_id,))
            return cur.fetchall()


def get_department_tickets(department):
    with get_prototype_connection() as conn:
        _require_department(conn, department)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, request_id, description, category, department,
                       location, routing_decision, status, assigned_to, created_at
                FROM nasaaem_prototype.tickets
                WHERE department = %s ORDER BY id DESC
            """, (department,))
            return cur.fetchall()


def claim_ticket(ticket_id, employee_id, department):
    with get_prototype_connection() as conn:
        user = _require_department(conn, department)
        _require_identity(conn, employee_id)
        cur = conn.execute("""
            UPDATE nasaaem_prototype.tickets
            SET status = 'In Progress', assigned_to = %s
            WHERE id = %s AND department = %s
              AND status IN ('New','Reopened') AND assigned_to IS NULL
        """, (_identity(user), ticket_id, department))
        return cur.rowcount == 1


def mark_ticket_completed(ticket_id, employee_id, department):
    with get_prototype_connection() as conn:
        _require_department(conn, department)
        _require_identity(conn, employee_id)
        cur = conn.execute("""
            UPDATE nasaaem_prototype.tickets SET status = 'Pending Confirmation'
            WHERE id = %s AND department = %s AND status = 'In Progress'
              AND assigned_to = %s
        """, (ticket_id, department, employee_id))
        if cur.rowcount != 1:
            return False
        owner_row = conn.execute('''SELECT r.employee_id
             FROM nasaaem_prototype.requests r
             JOIN nasaaem_prototype.tickets t ON t.request_id = r.id
             WHERE t.id = %s''', (ticket_id,)).fetchone()
        if owner_row and owner_row[0].startswith('USER-'):
            owner_id = int(owner_row[0][5:])
            conn.execute('''INSERT INTO nasaaem_prototype.notifications
                   (user_id, ticket_id, title, message)
                 VALUES (%s,%s,'Ready for confirmation',%s)''',
                 (owner_id, ticket_id, f'Please confirm if ticket #{ticket_id} was solved'))
        return True


def confirm_ticket(ticket_id, employee_id, solved):
    if type(solved) is not bool:
        raise ValueError("Invalid confirmation")
    new_status = 'Resolved' if solved else 'Reopened'
    with get_prototype_connection() as conn:
        _require_identity(conn, employee_id)
        cur = conn.execute("""
            UPDATE nasaaem_prototype.tickets t
            SET status = %s,
                assigned_to = CASE WHEN %s = 'Reopened' THEN NULL ELSE assigned_to END
            WHERE t.id = %s AND t.status = 'Pending Confirmation'
              AND EXISTS (
                SELECT 1 FROM nasaaem_prototype.requests r
                WHERE r.id = t.request_id AND r.employee_id = %s
              )
        """, (new_status, new_status, ticket_id, employee_id))
        return cur.rowcount == 1


def get_user_notifications(user_id):
    with get_prototype_connection() as conn:
        user = _session_user(conn)
        if user["id"] != int(user_id):
            raise PermissionError("Cannot view another account's notifications")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, ticket_id, title, message, is_read, created_at
                FROM nasaaem_prototype.notifications
                WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT 100
            """, (user_id,))
            return cur.fetchall()


def get_unread_count(user_id):
    with get_prototype_connection() as conn:
        user = _session_user(conn)
        if user["id"] != int(user_id):
            raise PermissionError("Account mismatch")
        return conn.execute("""
            SELECT COUNT(*) FROM nasaaem_prototype.notifications
            WHERE user_id = %s AND is_read = FALSE
        """, (user_id,)).fetchone()[0]


def mark_notification_read(notification_id, user_id):
    with get_prototype_connection() as conn:
        user = _session_user(conn)
        if user["id"] != int(user_id):
            raise PermissionError("Account mismatch")
        cur = conn.execute("""
            UPDATE nasaaem_prototype.notifications
            SET is_read = TRUE WHERE id = %s AND user_id = %s AND is_read = FALSE
        """, (notification_id, user_id))
        return cur.rowcount == 1


def get_backend_functions():
    return {
        "create_request_with_tickets": create_request_with_tickets,
        "get_employee_tickets": get_employee_tickets,
        "get_department_tickets": get_department_tickets,
        "claim_ticket": claim_ticket,
        "mark_ticket_completed": mark_ticket_completed,
        "confirm_ticket": confirm_ticket,
        "get_user_notifications": get_user_notifications,
        "get_unread_count": get_unread_count,
        "mark_notification_read": mark_notification_read,
    }


# Two-way ticket conversation: owner and assigned department only.
def _ticket_actor(conn, ticket_id):
    user = _session_user(conn)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('''SELECT t.id, t.department, t.status, t.assigned_to,
                              r.employee_id
                       FROM nasaaem_prototype.tickets t
                       JOIN nasaaem_prototype.requests r ON r.id=t.request_id
                       WHERE t.id=%s''', (ticket_id,))
        ticket = cur.fetchone()
    if not ticket:
        raise PermissionError('Ticket not found')
    owner = ticket['employee_id'] == _identity(user)
    staff = user['role'] == 'Admin' or (
        user['role'] == 'Staff' and user['department'] == ticket['department']
    )
    if not (owner or staff):
        raise PermissionError('Ticket access denied')
    return user, ticket, owner


def get_ticket_messages(ticket_id):
    with get_prototype_connection() as conn:
        _ticket_actor(conn, ticket_id)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('''SELECT m.id, m.body, m.created_at,
                                  u.full_name AS author, u.role AS author_role
                           FROM nasaaem_prototype.ticket_messages m
                           JOIN nasaaem_prototype.users u ON u.id=m.author_id
                           WHERE m.ticket_id=%s ORDER BY m.id LIMIT 200''', (ticket_id,))
            return cur.fetchall()


def add_ticket_message(ticket_id, body):
    if not isinstance(body, str) or not 1 <= len(body.strip()) <= 2000:
        raise ValueError('Message must be 1–2000 characters')
    with get_prototype_connection() as conn:
        user, ticket, owner = _ticket_actor(conn, ticket_id)
        if ticket['status'] == 'Resolved':
            raise ValueError('Reopen the ticket before posting new messages')
        conn.execute('''INSERT INTO nasaaem_prototype.ticket_messages
                           (ticket_id, author_id, body) VALUES (%s,%s,%s)''',
                     (ticket_id, user['id'], body.strip()))
        if owner:
            conn.execute('''INSERT INTO nasaaem_prototype.notifications
                               (user_id, ticket_id, title, message)
                            SELECT id, %s, 'Requester replied', %s
                            FROM nasaaem_prototype.users
                            WHERE is_active=TRUE AND (role='Admin' OR
                                  (role='Staff' AND department=%s))''',
                         (ticket_id, f'New message on ticket #{ticket_id}', ticket['department']))
        else:
            owner_id = int(ticket['employee_id'].removeprefix('USER-'))
            conn.execute('''INSERT INTO nasaaem_prototype.notifications
                               (user_id, ticket_id, title, message)
                            VALUES (%s,%s,'Department replied',%s)''',
                         (owner_id, ticket_id, f'New response on ticket #{ticket_id}'))
    return True


def get_ticket_feedback(ticket_id):
    with get_prototype_connection() as conn:
        _ticket_actor(conn, ticket_id)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute('''SELECT solved, rating, comment, updated_at
                           FROM nasaaem_prototype.ticket_feedback
                           WHERE ticket_id=%s''', (ticket_id,))
            return cur.fetchone()


def confirm_ticket_with_feedback(ticket_id, employee_id, solved, rating, comment):
    if type(solved) is not bool or not isinstance(comment, str) or len(comment) > 2000:
        raise ValueError('Invalid feedback')
    if rating is not None and (type(rating) is not int or not 1 <= rating <= 5):
        raise ValueError('Rating must be 1–5')
    if not solved and not comment.strip():
        raise ValueError('Explain what is still wrong')
    with get_prototype_connection() as conn:
        user = _require_identity(conn, employee_id)
        actor, ticket, is_owner = _ticket_actor(conn, ticket_id)
        if not is_owner or actor['id'] != user['id']:
            raise PermissionError('Only the requester can confirm')
        if ticket['status'] != 'Pending Confirmation':
            return False
        new_status = 'Resolved' if solved else 'Reopened'
        updated = conn.execute('''UPDATE nasaaem_prototype.tickets
                                  SET status=%s,
                                    assigned_to=CASE WHEN %s='Reopened' THEN NULL
                                                     ELSE assigned_to END
                                  WHERE id=%s AND status='Pending Confirmation' ''',
                               (new_status, new_status, ticket_id)).rowcount
        if not updated:
            return False
        conn.execute('''INSERT INTO nasaaem_prototype.ticket_feedback
                           (ticket_id, author_id, solved, rating, comment)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (ticket_id) DO UPDATE SET
                          solved=EXCLUDED.solved, rating=EXCLUDED.rating,
                          comment=EXCLUDED.comment, updated_at=NOW()''',
                     (ticket_id, user['id'], solved, rating, comment.strip()))
        if comment.strip():
            conn.execute('''INSERT INTO nasaaem_prototype.ticket_messages
                               (ticket_id, author_id, body) VALUES (%s,%s,%s)''',
                         (ticket_id, user['id'], comment.strip()))
        conn.execute('''INSERT INTO nasaaem_prototype.notifications
                           (user_id, ticket_id, title, message)
                        SELECT id, %s, 'Requester feedback', %s
                        FROM nasaaem_prototype.users
                        WHERE is_active=TRUE AND (role='Admin' OR
                              (role='Staff' AND department=%s))''',
                     (ticket_id, f'Ticket #{ticket_id}: {new_status}, requester feedback received', ticket['department']))
    return True


# Extend the original backend routing without changing any existing call signatures.
_previous_backend_functions = get_backend_functions

def get_backend_functions():
    funcs = _previous_backend_functions()
    funcs.update({
        'get_ticket_messages': get_ticket_messages,
        'add_ticket_message': add_ticket_message,
        'get_ticket_feedback': get_ticket_feedback,
        'confirm_ticket_with_feedback': confirm_ticket_with_feedback,
    })
    return funcs
