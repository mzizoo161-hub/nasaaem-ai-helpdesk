
import hashlib
import hmac
import secrets
import sqlite3

from getpass import getpass

from database import (
    get_employee_connection,
    ALLOWED_DEPARTMENTS,
)


# =====================================================
# 1. EMPLOYEE DATABASE CONNECTION
# =====================================================

def get_connection():
    """
    All authentication and employee-account operations
    use the separate employees database.

    Database:
        db/employees/employees.db
    """
    return get_employee_connection()


# =====================================================
# 2. PASSWORD HASHING
# =====================================================

def hash_password(password: str) -> str:
    """
    Generate a salted password hash using scrypt.
    """

    if not isinstance(password, str) or len(password) < 12:
        raise ValueError(
            "Password must contain at least 12 characters."
        )

    salt = secrets.token_bytes(16)

    hashed = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )

    return (
        f"scrypt$16384$8$1$"
        f"{salt.hex()}${hashed.hex()}"
    )


def verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    """
    Verify an existing password hash.
    """

    if not isinstance(password, str):
        return False

    if not isinstance(stored_hash, str):
        return False

    try:

        algorithm, n, r, p, salt_hex, hash_hex = (
            stored_hash.split("$")
        )

        if algorithm != "scrypt":
            return False

        if (n, r, p) != ("16384", "8", "1"):
            return False

        actual_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )

        return hmac.compare_digest(
            actual_hash,
            bytes.fromhex(hash_hex),
        )

    except (ValueError, TypeError, AttributeError):
        return False


# =====================================================
# 3. PHONE NUMBER VALIDATION
# =====================================================

# Synthetic test number for the local prototype.
# This exception is NOT suitable for production use.
DEMO_ADMIN_PHONE = "0123456789"


def normalize_phone_number(phone_number: str) -> str:
    """
    Normalize an Egyptian mobile phone number.

    Accepted examples:
        01012345678
        +201012345678
        201012345678

    Special local-demo exception:
        0123456789

    Stored format:
        01XXXXXXXXX
    """

    if not isinstance(phone_number, str):
        raise ValueError(
            "Phone number must be text."
        )

    phone = "".join(
        phone_number.split()
    )

    # Allow the exact synthetic Admin demo number.

    if phone == DEMO_ADMIN_PHONE:
        return phone

    if phone.startswith("+20"):

        phone = "0" + phone[3:]

    elif phone.startswith("20"):

        phone = "0" + phone[2:]

    if (
        len(phone) != 11
        or not phone.isascii()
        or not phone.isdigit()
        or not phone.startswith(
            ("010", "011", "012", "015")
        )
    ):

        raise ValueError(
            "Invalid Egyptian mobile number."
        )

    return phone


# =====================================================
# 4. EMPLOYEE ID VALIDATION
# =====================================================

def normalize_employee_id(employee_id: str) -> str:
    """
    Normalize a hospital employee ID.

    Stored as text to preserve leading zeros.
    """

    if not isinstance(employee_id, str):
        raise ValueError(
            "Employee ID must be text."
        )

    employee_id = employee_id.strip()

    if not employee_id:

        raise ValueError(
            "Employee ID is required."
        )

    if len(employee_id) > 100:

        raise ValueError(
            "Employee ID is too long."
        )

    return employee_id


# =====================================================
# 5. PUBLIC USER DATA
# =====================================================

def public_user_data(row) -> dict:
    """
    Return user information without exposing
    password hashes or personal phone numbers.
    """

    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
        "department": row["department"],
    }


# =====================================================
# 6. INITIALIZE EMPLOYEE DATABASE
# =====================================================

def initialize_auth_database():
    """
    Initialize employee tables if required.

    Existing records are preserved.
    """

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                username TEXT NOT NULL UNIQUE,

                password_hash TEXT NOT NULL,

                full_name TEXT NOT NULL,

                role TEXT NOT NULL
                    CHECK (
                        role IN (
                            'Employee',
                            'Staff',
                            'Admin'
                        )
                    ),

                department TEXT,

                phone_number TEXT,

                employee_id TEXT,

                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (is_active IN (0, 1)),

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(users)"
            )
        }

        # Upgrade older schemas without deleting data.

        if "phone_number" not in columns:

            connection.execute(
                """
                ALTER TABLE users
                ADD COLUMN phone_number TEXT
                """
            )

        if "employee_id" not in columns:

            connection.execute(
                """
                ALTER TABLE users
                ADD COLUMN employee_id TEXT
                """
            )

        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_users_phone_number
            ON users(phone_number)
            WHERE phone_number IS NOT NULL
            """
        )

        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_users_employee_id
            ON users(employee_id)
            WHERE employee_id IS NOT NULL
            """
        )


# =====================================================
# 7. CREATE NEW EMPLOYEE / ADMIN
# =====================================================

def create_user(
    username: str,
    password: str,
    full_name: str,
    role: str,
    department: str | None,
    phone_number: str | None = None,
    employee_id: str | None = None,
) -> int:
    """
    Create a new employee or Admin account.

    Setting role='Admin' gives the account
    Admin permissions in the application.

    Note:
    Only call this function from an authorized
    Admin workflow.
    """

    if not isinstance(username, str):
        raise ValueError(
            "Username must be text."
        )

    if not isinstance(full_name, str):
        raise ValueError(
            "Full name must be text."
        )

    username = username.strip().lower()
    full_name = full_name.strip()

    if not username or not full_name:

        raise ValueError(
            "Username and full name are required."
        )

    if role not in {
        "Employee",
        "Staff",
        "Admin",
    }:

        raise ValueError(
            "Invalid role."
        )

    if (
        department is not None
        and department not in ALLOWED_DEPARTMENTS
    ):

        raise ValueError(
            "Invalid department."
        )

    if phone_number is not None:

        phone_number = normalize_phone_number(
            phone_number
        )

    if employee_id is not None:

        employee_id = normalize_employee_id(
            employee_id
        )

    password_hash = hash_password(
        password
    )

    initialize_auth_database()

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO users (
                username,
                password_hash,
                full_name,
                role,
                department,
                phone_number,
                employee_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                password_hash,
                full_name,
                role,
                department,
                phone_number,
                employee_id,
            ),
        )

        return cursor.lastrowid


# =====================================================
# 8. USERNAME + PASSWORD AUTHENTICATION
# =====================================================

def authenticate_user(
    username: str,
    password: str,
) -> dict | None:
    """
    Legacy username/password authentication.

    Preserved for backward compatibility.
    """

    if not isinstance(username, str):
        return None

    if not isinstance(password, str):
        return None

    with get_connection() as connection:

        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                id,
                username,
                password_hash,
                full_name,
                role,
                department

            FROM users

            WHERE username = ?
              AND is_active = 1
            """,
            (
                username.strip().lower(),
            ),
        ).fetchone()

    if row is None:
        return None

    if not verify_password(
        password,
        row["password_hash"],
    ):
        return None

    return public_user_data(row)


# =====================================================
# 9. PHONE NUMBER + EMPLOYEE ID LOGIN
# =====================================================

def authenticate_by_phone_employee_id(
    phone_number: str,
    employee_id: str,
) -> dict | None:
    """
    Local demo login.

    Check phone number + employee ID against
    the same active employee record.

    Works for:
        - Employee
        - Staff
        - Admin

    WARNING:
    Phone number and employee ID are not secrets
    and are insufficient for production security.
    """

    try:

        phone = normalize_phone_number(
            phone_number
        )

        hospital_id = normalize_employee_id(
            employee_id
        )

    except ValueError:
        return None

    with get_connection() as connection:

        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                id,
                username,
                full_name,
                role,
                department

            FROM users

            WHERE phone_number = ?
              AND employee_id = ?
              AND is_active = 1

            LIMIT 1
            """,
            (
                phone,
                hospital_id,
            ),
        ).fetchone()

    if row is None:
        return None

    return public_user_data(row)


# =====================================================
# 10. SYNTHETIC DEMO ACCOUNTS
# =====================================================

DEMO_USERS = [
    (
        "ahmed",
        "Ahmed Demo",
        "Employee",
        "Reception",
    ),
    (
        "mahmoud",
        "Mahmoud Demo",
        "Staff",
        "IT Support",
    ),
    (
        "omar",
        "Omar Demo",
        "Staff",
        "Maintenance",
    ),
    (
        "sara",
        "Sara Demo",
        "Staff",
        "Housekeeping",
    ),
    (
        "admin",
        "Admin Demo",
        "Admin",
        None,
    ),
]


def setup_demo_accounts():
    """
    Add missing synthetic demo accounts only.

    Never overwrite existing users or passwords.
    """

    initialize_auth_database()

    print("Create demo accounts")
    print("Choose a password for each account.")

    with get_connection() as connection:

        existing = {
            row[0]
            for row in connection.execute(
                """
                SELECT username
                FROM users
                """
            ).fetchall()
        }

    for (
        username,
        name,
        role,
        department,
    ) in DEMO_USERS:

        if username in existing:

            print(
                f"Skipped existing user: {username}"
            )

            continue

        while True:

            password = getpass(
                f"Password for {username} "
                f"(min 12 chars): "
            )

            confirm = getpass(
                f"Confirm password for {username}: "
            )

            if password != confirm:

                print(
                    "Passwords do not match. Try again."
                )

                continue

            try:

                user_id = create_user(
                    username=username,
                    password=password,
                    full_name=name,
                    role=role,
                    department=department,
                )

                print(
                    f"Created: {username} "
                    f"(ID #{user_id})"
                )

                break

            except (
                ValueError,
                sqlite3.IntegrityError,
            ) as error:

                print(
                    f"Error: {error}"
                )


# =====================================================
# 11. MAIN
# =====================================================

if __name__ == "__main__":

    initialize_auth_database()

    print(
        "Employee authentication database ready."
    )

    with get_connection() as connection:

        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        ).fetchone()[0]

    print(
        f"Total employee accounts: {count}"
    )

    print(
        "Employee database: "
        "db/employees/employees.db"
    )

    print(
        "Phone + Employee ID login: ENABLED"
    )

    print(
        "Admin demo phone exception: ENABLED"
    )
