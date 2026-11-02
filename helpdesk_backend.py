"""
Nasaaem AI Helpdesk
Database Backend Router

Default: Existing SQLite implementation.
Cloud: Synthetic-data demo only.

This module selects functions but does not
provide user authentication or authorization.
"""

from database import (
    create_request_with_tickets as local_create_request,
    get_employee_tickets as local_employee_tickets,
    get_department_tickets as local_department_tickets,
    claim_ticket as local_claim_ticket,
    mark_ticket_completed as local_complete_ticket,
    confirm_ticket as local_confirm_ticket,
)

from notifications import (
    get_user_notifications as local_notifications,
    get_unread_count as local_unread_count,
    mark_notification_read as local_mark_read,
)

from cloud_tickets import (
    create_cloud_request_with_tickets,
    get_cloud_employee_tickets,
    get_cloud_department_tickets,
    claim_cloud_ticket,
    mark_cloud_ticket_completed,
    confirm_cloud_ticket,
)

from cloud_notifications import (
    get_cloud_user_notifications,
    get_cloud_unread_count,
    mark_cloud_notification_read,
)


def get_backend_functions(use_cloud=False):
    """
    Return a dictionary of backend functions.

    Cloud mode must only be used with synthetic
    data in a controlled demo environment.
    """

    if use_cloud:
        return {
            "create_request_with_tickets":
                create_cloud_request_with_tickets,
            "get_employee_tickets":
                get_cloud_employee_tickets,
            "get_department_tickets":
                get_cloud_department_tickets,
            "claim_ticket":
                claim_cloud_ticket,
            "mark_ticket_completed":
                mark_cloud_ticket_completed,
            "confirm_ticket":
                confirm_cloud_ticket,
            "get_user_notifications":
                get_cloud_user_notifications,
            "get_unread_count":
                get_cloud_unread_count,
            "mark_notification_read":
                mark_cloud_notification_read,
        }

    return {
        "create_request_with_tickets":
            local_create_request,
        "get_employee_tickets":
            local_employee_tickets,
        "get_department_tickets":
            local_department_tickets,
        "claim_ticket":
            local_claim_ticket,
        "mark_ticket_completed":
            local_complete_ticket,
        "confirm_ticket":
            local_confirm_ticket,
        "get_user_notifications":
            local_notifications,
        "get_unread_count":
            local_unread_count,
        "mark_notification_read":
            local_mark_read,
    }


if __name__ == "__main__":
    print("=== NASAAEM BACKEND ROUTER TEST ===")

    local = get_backend_functions(False)
    cloud = get_backend_functions(True)

    expected = {
        "create_request_with_tickets",
        "get_employee_tickets",
        "get_department_tickets",
        "claim_ticket",
        "mark_ticket_completed",
        "confirm_ticket",
        "get_user_notifications",
        "get_unread_count",
        "mark_notification_read",
    }

    assert set(local) == expected
    assert set(cloud) == expected
    assert all(callable(fn) for fn in local.values())
    assert all(callable(fn) for fn in cloud.values())

    print("LOCAL BACKEND: PASS")
    print("CLOUD BACKEND: PASS")
    print("FUNCTION MAPPING: PASS")
    print("DATABASE OPERATIONS: NONE")
    print("STEP 252: PASS")
