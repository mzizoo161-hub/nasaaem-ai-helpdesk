from prototype_auth import authenticate_prototype_employee

import sqlite3
import psycopg

import streamlit as st

from auth import authenticate_by_phone_employee_id
from cloud_employees import authenticate_cloud_employee, load_cloud_user

# Cloud mode is intended for synthetic-data testing only.
USE_CLOUD_DEMO = False
# Select SQLite or synthetic Supabase backend.
from helpdesk_backend import get_backend_functions

# Synthetic 150-account cloud backend (not the legacy TEST001 demo).
from prototype_backend import get_backend_functions as get_prototype_backend
backend = get_prototype_backend()
from classifier_test import classify_request

from database import (
    ALLOWED_DEPARTMENTS,
    claim_ticket,
    confirm_ticket,
    create_request_with_tickets,
    get_employee_connection,
    get_ticket_connection,
    get_department_tickets,
    get_employee_tickets,
    initialize_database,
    mark_ticket_completed,
)

from notifications import (
    get_unread_count,
    get_user_notifications,
    initialize_notifications,
    mark_notification_read,
)


# =====================================================
# 1. APPLICATION CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="Al Nasaaem Helpdesk",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# The hosted application uses persistent PostgreSQL; no SQLite initialization.

if "main_user" not in st.session_state:
    st.session_state.main_user = None

if "main_page" not in st.session_state:
    st.session_state.main_page = "Home"


# =====================================================
# 2. HELPER FUNCTIONS
# =====================================================

def logout():
    st.session_state.main_user = None
    st.session_state.main_page = "Home"
    st.rerun()


def navigate(page):
    st.session_state.main_page = page
    st.rerun()


def load_user(user_id):
    """
    Load employee profile from the selected database.

    Cloud mode: synthetic Supabase demo only.
    Local mode: existing SQLite database.
    """

    if USE_CLOUD_DEMO:
        return load_cloud_user(user_id)

    from prototype_cloud import get_prototype_connection
    from psycopg.rows import dict_row

    with get_prototype_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                '''
                SELECT
                    id, username, full_name,
                    role, department, is_active
                FROM nasaaem_prototype.users
                WHERE id = %s
                ''',
                (user_id,),
            )
            row = cursor.fetchone()

    return row

    with get_employee_connection() as connection:
        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                id,
                username,
                full_name,
                role,
                department,
                is_active
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    return dict(row) if row else None


def get_saved_tickets(request_id):
    """Read saved synthetic tickets from the persistent cloud database."""
    from psycopg.rows import dict_row
    from prototype_cloud import get_prototype_connection
    with get_prototype_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT id, department, status
                   FROM nasaaem_prototype.tickets
                   WHERE request_id = %s ORDER BY id""",
                (request_id,),
            )
            return cursor.fetchall()


# =====================================================
# 3. LOGIN PAGE
# PHONE NUMBER + HOSPITAL EMPLOYEE ID
# =====================================================

if st.session_state.main_user is None:

    st.title("Al Nasaaem Helpdesk")
    st.subheader("Employee Login")

    st.caption(
        "Enter your registered phone number "
        "and hospital employee ID."
    )

    with st.form("login_form"):

        phone_number = st.text_input(
            "Phone Number",
            placeholder="01XXXXXXXXX",
        )

        employee_id = st.text_input(
            "Hospital Employee ID",
            placeholder="Enter your Employee ID",
        )

        login_clicked = st.form_submit_button(
            "Login",
            type="primary",
            use_container_width=True,
        )

    if login_clicked:

        if USE_CLOUD_DEMO:
            user = authenticate_cloud_employee(
                phone_number=phone_number,
                employee_id=employee_id,
            )
        else:
            user = authenticate_prototype_employee(
                phone_number=phone_number,
                employee_id=employee_id,
            )

        if user is None:

            st.error(
                "Invalid phone number or employee ID."
            )

        else:

            st.session_state.main_user = user
            st.session_state.main_page = "Home"
            st.rerun()

    st.caption(
        "Prototype access only. Phone number and "
        "employee ID do not securely verify identity."
    )

    st.stop()


# =====================================================
# 4. VERIFY LOGGED-IN USER
# =====================================================

session_user = st.session_state.main_user

user = load_user(session_user["id"])

if (
    user is None
    or user["is_active"] != 1
    or user["username"] != session_user["username"]
):
    logout()

if user["role"] not in {
    "Employee",
    "Staff",
    "Admin",
}:

    st.error("Invalid account role.")
    st.stop()


is_admin = user["role"] == "Admin"

# Every employee assigned to a valid department
# can access the dashboard of that department.
# Admin can access all departments.

can_use_dashboard = (
    is_admin
    or (
        user["role"] == "Staff"
        and user["department"] in ALLOWED_DEPARTMENTS
    )
)

# Use the internal user ID to identify ticket
# ownership and staff assignments.

# Preserve legacy SQLite identity.
# Use the synthetic hospital ID in cloud demo mode.
user_identity = f"USER-{user['id']}"


# =====================================================
# 5. HEADER + NOTIFICATIONS
# =====================================================

header, notification_column, logout_column = st.columns(
    [5, 1.7, 1]
)

with header:

    st.title("Al Nasaaem Helpdesk")

    st.caption(
        f"Welcome, {user['full_name']}"
    )


with notification_column:

    try:

        unread_count = backend["get_unread_count"](
            user["id"]
        )

    except (sqlite3.Error, psycopg.Error, PermissionError):
        unread_count = None

    notification_label = (
        f"Notifications ({unread_count})"
        if unread_count is not None
        else "Notifications"
    )

    with st.popover(
        notification_label,
        use_container_width=True,
    ):

        st.subheader("Notifications")

        try:

            notifications = backend["get_user_notifications"](
                user["id"]
            )

        except (sqlite3.Error, psycopg.Error, PermissionError):

            st.error(
                "Unable to load notifications."
            )

            notifications = []

        if not notifications:

            st.info("No notifications yet.")

        else:

            for notification in notifications[:15]:

                with st.container(border=True):

                    if not notification["is_read"]:

                        st.markdown(
                            f"**{notification['title']}**"
                        )

                    else:

                        st.write(
                            notification["title"]
                        )

                    st.write(
                        notification["message"]
                    )

                    st.caption(
                        str(notification["created_at"])
                    )

                    if not notification["is_read"]:

                        if st.button(
                            "Mark as Read",
                            key=f"read_{notification['id']}",
                        ):

                            try:

                                changed = backend["mark_notification_read"](
                                    notification_id=notification["id"],
                                    user_id=user["id"],
                                )

                            except (sqlite3.Error, psycopg.Error, PermissionError):

                                st.error(
                                    "Could not update notification."
                                )

                            else:

                                if changed:
                                    st.rerun()

                                else:
                                    st.info(
                                        "Notification already read."
                                    )


with logout_column:

    st.button(
        "Logout",
        on_click=logout,
        use_container_width=True,
    )


st.divider()


# =====================================================
# 6. HOME PAGE
# =====================================================

if st.session_state.main_page == "Home":

    st.subheader(
        "What would you like to do?"
    )

    col1, col2, col3 = st.columns(3)

    # AI CHAT

    with col1:

        with st.container(border=True):

            st.subheader("AI Chat")

            st.write(
                "Submit a new support request."
            )

            if st.button(
                "Open AI Chat",
                use_container_width=True,
            ):

                navigate("Chat")

    # MY TICKETS

    with col2:

        with st.container(border=True):

            st.subheader("My Tickets")

            st.write(
                "Track and confirm your requests."
            )

            if st.button(
                "Open My Tickets",
                use_container_width=True,
            ):

                navigate("My Tickets")

    # DEPARTMENT DASHBOARD

    with col3:

        with st.container(border=True):

            st.subheader(
                "Department Dashboard"
            )

            if can_use_dashboard:

                if is_admin:

                    st.write(
                        "Manage tickets from all departments."
                    )

                else:

                    st.write(
                        f"Manage {user['department']} tickets."
                    )

                if st.button(
                    "Open Dashboard",
                    use_container_width=True,
                ):

                    navigate("Dashboard")

            else:

                st.info(
                    "No department assigned to your account."
                )

    if is_admin and st.button("Open Admin Overview", use_container_width=True):
        navigate("Admin")
    st.stop()


# =====================================================
# 7. BACK NAVIGATION
# =====================================================

if st.button("Back to Home"):

    navigate("Home")

st.divider()


# =====================================================
# 8. AI CHAT
# =====================================================

if st.session_state.main_page == "Chat":

    with st.form("ai_request_form"):

        message = st.text_area(
            "اكتب المشكلة",
            label_visibility="collapsed",
            placeholder="",
            height=170,
        )

        submitted = st.form_submit_button(
            "إرسال طلب",
            type="primary",
            use_container_width=True,
        )

    if submitted:

        message = message.strip()

        if not message:

            st.warning(
                "من فضلك اكتب المشكلة."
            )

        else:

            with st.spinner(
                "جاري تحليل الطلب..."
            ):

                try:

                    result = classify_request(
                        message
                    )

                except Exception:

                    result = None

            if result is None:

                st.error(
                    "تعذر تحليل الطلب. "
                    "لم يتم إنشاء Ticket."
                )

            else:

                routable = (
                    bool(result.issues)
                    and all(
                        issue.routing_decision == "ROUTE"
                        and issue.department in ALLOWED_DEPARTMENTS
                        and isinstance(
                            issue.description,
                            str,
                        )
                        and bool(
                            issue.description.strip()
                        )
                        and isinstance(
                            issue.category,
                            str,
                        )
                        and bool(
                            issue.category.strip()
                        )
                        for issue in result.issues
                    )
                )

                if not routable:

                    st.warning(
                        "الطلب يحتاج توضيحًا أو "
                        "مراجعة بشرية، ولم يتم "
                        "توجيهه تلقائيًا."
                    )

                    for issue in result.issues:

                        if issue.clarification_question:

                            st.write(
                                issue.clarification_question
                            )

                    st.error(
                        "المشكلات العاجلة أو المتعلقة "
                        "بسلامة المرضى يجب الإبلاغ "
                        "عنها مباشرة وفق إجراءات المستشفى."
                    )

                else:

                    issues = [
                        {
                            "description": issue.description,
                            "category": issue.category,
                            "department": issue.department,
                            "location": issue.location,
                            "routing_decision": "ROUTE",
                        }
                        for issue in result.issues
                    ]

                    try:

                        request_id = (
                            backend["create_request_with_tickets"](
                                employee_id=user_identity,
                                original_message=message,
                                issues=issues,
                            )
                        )

                    except (
                        ValueError,
                        (sqlite3.Error, psycopg.Error, PermissionError),
                    ):

                        st.error(
                            "تعذر تأكيد حفظ الطلب. "
                            "تحقق من التسجيل قبل "
                            "إعادة المحاولة."
                        )

                    else:

                        st.success(
                            "تم تسجيل طلبك بنجاح."
                        )

                        st.write(
                            f"Request ID: #{request_id}"
                        )

                        try:

                            saved_tickets = get_saved_tickets(
                                request_id
                            )

                            for ticket in saved_tickets:

                                st.write(
                                    f"Ticket #{ticket['id']} "
                                    f"- {ticket['department']}"
                                )

                        except (sqlite3.Error, psycopg.Error, PermissionError):

                            st.warning(
                                "تم حفظ الطلب لكن تعذر "
                                "عرض أرقام التذاكر."
                            )

                        if st.button(
                            "View My Tickets",
                            key=f"view_{request_id}",
                        ):

                            navigate("My Tickets")


# =====================================================
# 9. MY TICKETS
# =====================================================

elif st.session_state.main_page == "My Tickets":

    st.subheader("My Tickets")

    st.caption(
        "Requests submitted using your own account."
    )

    try:

        my_tickets = backend["get_employee_tickets"](
            user_identity
        )

    except (
        ValueError,
        (sqlite3.Error, psycopg.Error, PermissionError),
    ):

        st.error(
            "Unable to load your tickets."
        )

        st.stop()

    if not my_tickets:

        st.info(
            "You have not submitted any tickets yet."
        )

    else:

        for ticket in my_tickets:

            with st.container(border=True):

                left, right = st.columns(
                    [3, 1]
                )

                with left:

                    st.markdown(
                        f"### Ticket #{ticket['id']}"
                    )

                    st.write(
                        ticket["description"]
                    )

                    st.write(
                        f"**Department:** "
                        f"{ticket['department'] or 'Not assigned'}"
                    )

                    st.write(
                        f"**Location:** "
                        f"{ticket['location'] or 'Not specified'}"
                    )

                with right:

                    st.write(
                        f"**Status:** {ticket['status']}"
                    )

                # Two-way ticket conversation (readable by requester and assigned staff).
                st.markdown("#### Ticket conversation")
                try:
                    messages = backend["get_ticket_messages"](ticket["id"])
                    existing_feedback = backend["get_ticket_feedback"](ticket["id"])
                except (ValueError, PermissionError, psycopg.Error):
                    messages = []
                    existing_feedback = None
                    st.warning("Could not load ticket conversation.")
                for entry in messages:
                    st.caption(f"{entry['author']} · {entry['created_at']}")
                    st.write(entry['body'])
                if existing_feedback and existing_feedback['rating']:
                    st.caption(f"Requester feedback: {existing_feedback['rating']}/5")
                if ticket["status"] != "Resolved":
                    with st.form(f"reply_form_{ticket['id']}", clear_on_submit=True):
                        reply = st.text_area("Reply / add details", max_chars=2000)
                        send = st.form_submit_button("Send message")
                    if send:
                        try:
                            backend['add_ticket_message'](ticket['id'], reply)
                        except (ValueError, PermissionError, psycopg.Error):
                            st.error("Unable to send message.")
                        else:
                            st.rerun()

                # Requester confirms solution and leaves feedback.
                if ticket["status"] == "Pending Confirmation":
                    st.divider()
                    st.markdown("#### هل تم حل المشكلة؟ / Was your issue solved?")
                    with st.form(f"confirm_form_{ticket['id']}"):
                        verdict = st.radio("Problem solved?", ["Yes — Solved", "No — Still a problem"])
                        rating = st.select_slider("Service rating", options=[1, 2, 3, 4, 5], value=5)
                        feedback_note = st.text_area("Feedback or what still needs fixing", max_chars=2000)
                        submitted_feedback = st.form_submit_button("Send confirmation & feedback", type="primary")
                    if submitted_feedback:
                        solved = verdict.startswith("Yes")
                        try:
                            success = backend['confirm_ticket_with_feedback'](
                                ticket_id=ticket['id'],
                                employee_id=user_identity,
                                solved=solved,
                                rating=rating,
                                comment=feedback_note,
                            )
                        except ValueError as exc:
                            st.warning(str(exc))
                        except (PermissionError, psycopg.Error):
                            st.error("Could not save your feedback.")
                        else:
                            st.session_state['notice'] = (
                                "Ticket resolved — thanks for your feedback!" if success and solved
                                else "Ticket reopened. The department has been notified." if success
                                else "Ticket state changed; refresh and try again."
                            )
                            st.rerun()

                elif ticket["status"] == "Resolved":

                    st.success(
                        "This ticket has been resolved."
                    )

                elif ticket["status"] == "Reopened":

                    st.warning(
                        "Your ticket was reopened "
                        "and is awaiting follow-up."
                    )

                elif ticket["status"] == "In Progress":

                    st.info(
                        "The department is working "
                        "on your request."
                    )

                elif ticket["status"] == "New":

                    st.info(
                        "Your ticket is awaiting assignment."
                    )

    if "notice" in st.session_state:

        st.info(
            st.session_state.pop("notice")
        )


# =====================================================
# 10. DEPARTMENT DASHBOARD
# =====================================================

elif st.session_state.main_page == "Dashboard":

    if not can_use_dashboard:

        st.error("Access denied.")
        st.stop()

    st.subheader(
        "Department Dashboard"
    )

    # Admin can select any department.

    if is_admin:

        department = st.selectbox(
            "Select Department",
            sorted(ALLOWED_DEPARTMENTS),
        )

    else:

        department = user["department"]

        st.info(
            f"Your Department: {department}"
        )

    if (
        not is_admin
        and department != user["department"]
    ):

        st.error(
            "Department access denied."
        )

        st.stop()

    # Load department tickets.

    try:

        tickets = backend["get_department_tickets"](
            department
        )

    except (
        ValueError,
        (sqlite3.Error, psycopg.Error, PermissionError),
    ):

        st.error(
            "Unable to load department tickets."
        )

        st.stop()

    # Metrics

    total = len(tickets)

    new = sum(
        t["status"] == "New"
        for t in tickets
    )

    progress = sum(
        t["status"] == "In Progress"
        for t in tickets
    )

    pending = sum(
        t["status"] == "Pending Confirmation"
        for t in tickets
    )

    resolved = sum(
        t["status"] == "Resolved"
        for t in tickets
    )

    reopened = sum(
        t["status"] == "Reopened"
        for t in tickets
    )

    columns = st.columns(6)

    columns[0].metric("Total", total)
    columns[1].metric("New", new)
    columns[2].metric("In Progress", progress)
    columns[3].metric("Pending", pending)
    columns[4].metric("Resolved", resolved)
    columns[5].metric("Reopened", reopened)

    st.divider()

    st.subheader(
        f"{department} - Tickets"
    )

    if not tickets:

        st.info(
            "No tickets available."
        )

    else:

        for ticket in tickets:

            with st.container(border=True):

                left, right = st.columns(
                    [3, 1]
                )

                with left:

                    st.markdown(
                        f"### Ticket #{ticket['id']}"
                    )

                    st.write(
                        ticket["description"]
                    )

                    st.caption(
                        f"Request #{ticket['request_id']}"
                    )

                    st.write(
                        f"**Category:** {ticket['category']}"
                    )

                    st.write(
                        f"**Location:** "
                        f"{ticket['location'] or 'Not specified'}"
                    )

                with right:

                    st.write(
                        f"**Status:** {ticket['status']}"
                    )

                    st.write(
                        f"**Assigned To:** "
                        f"{ticket['assigned_to'] or 'Unassigned'}"
                    )

                    # Two-way ticket conversation for staff/admin.
                    st.markdown("**Conversation**")
                    try:
                        for entry in backend['get_ticket_messages'](ticket['id']):
                            st.caption(f"{entry['author']} · {entry['created_at']}")
                            st.write(entry['body'])
                        requester_feedback = backend['get_ticket_feedback'](ticket['id'])
                        if requester_feedback:
                            st.caption(f"Feedback rating: {requester_feedback['rating'] or '—'}/5")
                            if requester_feedback['comment']:
                                st.write(requester_feedback['comment'])
                    except (ValueError, PermissionError, psycopg.Error):
                        st.warning("Conversation not available")
                    if ticket['status'] != 'Resolved':
                        with st.form(f"staff_reply_{ticket['id']}", clear_on_submit=True):
                            reply = st.text_area("Reply to requester", max_chars=2000)
                            send = st.form_submit_button("Send reply")
                        if send:
                            try:
                                backend['add_ticket_message'](ticket['id'], reply)
                            except (ValueError, PermissionError, psycopg.Error):
                                st.error("Could not send reply.")
                            else:
                                st.rerun()

                    # NEW / REOPENED

                    if ticket["status"] in (
                        "New",
                        "Reopened",
                    ):

                        if st.button(
                            "Start Working",
                            key=f"claim_{ticket['id']}",
                            use_container_width=True,
                        ):

                            try:

                                success = backend["claim_ticket"](
                                    ticket_id=ticket["id"],
                                    employee_id=user_identity,
                                    department=department,
                                )

                            except (
                                ValueError,
                                (sqlite3.Error, psycopg.Error, PermissionError),
                            ):

                                st.error(
                                    "Unable to claim ticket."
                                )

                            else:

                                if success:

                                    st.toast(
                                        "Ticket claimed successfully."
                                    )

                                    st.rerun()

                                else:

                                    st.warning(
                                        "Ticket is no longer available."
                                    )

                    # IN PROGRESS

                    elif ticket["status"] == "In Progress":

                        if (
                            ticket["assigned_to"]
                            == user_identity
                        ):

                            st.success(
                                "Assigned to you"
                            )

                            if st.button(
                                "Mark Completed",
                                key=f"complete_{ticket['id']}",
                                type="primary",
                                use_container_width=True,
                            ):

                                try:

                                    success = backend["mark_ticket_completed"](
                                        ticket_id=ticket["id"],
                                        employee_id=user_identity,
                                        department=department,
                                    )

                                except (
                                    ValueError,
                                    (sqlite3.Error, psycopg.Error, PermissionError),
                                ):

                                    st.error(
                                        "Could not update ticket."
                                    )

                                else:

                                    if success:

                                        st.toast(
                                            "Waiting for requester confirmation."
                                        )

                                        st.rerun()

                                    else:

                                        st.warning(
                                            "Unable to complete ticket."
                                        )

                        else:

                            st.info(
                                "Assigned to another employee."
                            )

                    # PENDING CONFIRMATION

                    elif (
                        ticket["status"]
                        == "Pending Confirmation"
                    ):

                        st.warning(
                            "Waiting for requester confirmation."
                        )

                    # RESOLVED

                    elif ticket["status"] == "Resolved":

                        st.success(
                            "Resolved"
                        )




# Admin overview — read-only by design; never exposes stored password hashes.
elif st.session_state.main_page == "Admin":
    if not is_admin:
        st.error("Access denied")
        st.stop()
    from prototype_cloud import get_prototype_connection
    from psycopg.rows import dict_row
    st.subheader("Synthetic Cloud Admin Overview")
    st.caption("Prototype only. Two-field login is not secure for real employee data.")
    with get_prototype_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""SELECT role, COUNT(*) AS total
                              FROM nasaaem_prototype.users GROUP BY role""")
            role_counts = {row['role']: row['total'] for row in cursor.fetchall()}
            cursor.execute("""SELECT department, status, COUNT(*) AS total
                              FROM nasaaem_prototype.tickets
                              GROUP BY department, status ORDER BY department, status""")
            summaries = cursor.fetchall()
    cols = st.columns(3)
    for col, role in zip(cols, ('Employee','Staff','Admin')):
        col.metric(role, role_counts.get(role, 0))
    st.subheader('Department ticket status')
    if summaries:
        st.dataframe(summaries, use_container_width=True, hide_index=True)
    else:
        st.info('No tickets yet')

# =====================================================
# 11. FOOTER
# =====================================================

st.divider()

st.caption(
    "Al Nasaaem Helpdesk - Synthetic Cloud Prototype"
)

st.caption(
    "Synthetic data only. "
    "Not approved for real hospital operations."
)
