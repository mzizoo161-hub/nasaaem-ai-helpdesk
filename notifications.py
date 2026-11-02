
import sqlite3


from database import get_ticket_connection as get_connection

# ==========================================
# INITIALIZE NOTIFICATIONS TABLE
# ==========================================

def initialize_notifications():

    with get_connection() as connection:

        connection.execute("""
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

                FOREIGN KEY (user_id)
                    REFERENCES users(id),

                FOREIGN KEY (ticket_id)
                    REFERENCES tickets(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_notifications_user_read
            ON notifications(user_id, is_read)
        """)


# ==========================================
# CREATE NOTIFICATION
# ==========================================

def create_notification(
    user_id: int,
    title: str,
    message: str,
    ticket_id: int | None = None,
) -> int:

    if type(user_id) is not int or user_id <= 0:
        raise ValueError("Invalid user ID.")

    if not title.strip() or not message.strip():
        raise ValueError("Title and message are required.")

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO notifications (
                user_id,
                ticket_id,
                title,
                message
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                ticket_id,
                title.strip(),
                message.strip(),
            ),
        )

        return cursor.lastrowid


# ==========================================
# GET USER NOTIFICATIONS
# ==========================================

def get_user_notifications(
    user_id: int,
) -> list[dict]:

    with get_connection() as connection:

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                id,
                ticket_id,
                title,
                message,
                is_read,
                created_at
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


# ==========================================
# UNREAD COUNT
# ==========================================

def get_unread_count(user_id: int) -> int:

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM notifications
            WHERE user_id = ?
              AND is_read = 0
            """,
            (user_id,),
        ).fetchone()

    return row[0]


# ==========================================
# MARK NOTIFICATION AS READ
# ==========================================

def mark_notification_read(
    notification_id: int,
    user_id: int,
) -> bool:

    with get_connection() as connection:

        cursor = connection.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE id = ?
              AND user_id = ?
              AND is_read = 0
            """,
            (notification_id, user_id),
        )

        return cursor.rowcount == 1


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    initialize_notifications()

    print("Notifications table initialized successfully!")
    print("Notification system ready for testing.")
