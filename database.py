
import sqlite3
from pathlib import Path
from datetime import datetime
import uuid

# -----------------------------------
# DATABASE CONFIGURATION
# -----------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

DB_PATH = DATABASE_DIR / "civic_eye.db"


# -----------------------------------
# DATABASE CONNECTION
# -----------------------------------

def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


# -----------------------------------
# INITIALIZE DATABASE
# -----------------------------------

def initialize_database():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            complaint_id TEXT UNIQUE NOT NULL,

            citizen_name TEXT NOT NULL,

            issue_type TEXT NOT NULL,

            description TEXT NOT NULL,

            location TEXT NOT NULL,

            severity TEXT,

            department TEXT,

            urgency TEXT,

            confidence TEXT,

            status TEXT DEFAULT 'Submitted',

            image_path TEXT,

            created_at TEXT NOT NULL,

            latitude REAL,

            longitude REAL,

            assigned_department TEXT,

            assigned_at TEXT

        )
    """)

    # Check existing database columns
    cursor.execute("PRAGMA table_info(complaints)")

    existing_columns = [
        column["name"]
        for column in cursor.fetchall()
    ]

    # Add missing columns to older databases
    migrations = {
    "latitude": "REAL",
    "longitude": "REAL",
    "assigned_department": "TEXT",
    "assigned_at": "TEXT",
    "repair_image_path": "TEXT"
     }

    for column_name, column_type in migrations.items():

        if column_name not in existing_columns:

            cursor.execute(
                f"ALTER TABLE complaints ADD COLUMN "
                f"{column_name} {column_type}"
            )

    connection.commit()
    connection.close()


# -----------------------------------
# ADD NEW COMPLAINT
# -----------------------------------

def add_complaint(
    citizen_name,
    issue_type,
    description,
    location,
    severity=None,
    department=None,
    urgency=None,
    confidence=None,
    image_path=None,
    latitude=None,
    longitude=None
):

    complaint_id = (
        "CE-" + uuid.uuid4().hex[:8].upper()
    )

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO complaints (

            complaint_id,
            citizen_name,
            issue_type,
            description,
            location,
            severity,
            department,
            urgency,
            confidence,
            image_path,
            created_at,
            latitude,
            longitude

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        complaint_id,
        citizen_name,
        issue_type,
        description,
        location,
        severity,
        department,
        urgency,
        confidence,
        image_path,
        datetime.now().isoformat(timespec="seconds"),
        latitude,
        longitude

    ))

    connection.commit()
    connection.close()

    return complaint_id


# -----------------------------------
# GET ALL COMPLAINTS
# -----------------------------------

def get_all_complaints():

    connection = get_connection()

    rows = connection.execute("""
        SELECT *
        FROM complaints
        ORDER BY id DESC
    """).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


# -----------------------------------
# GET SINGLE COMPLAINT
# -----------------------------------

def get_complaint(complaint_id):

    connection = get_connection()

    row = connection.execute("""
        SELECT *
        FROM complaints
        WHERE complaint_id = ?
    """, (complaint_id,)).fetchone()

    connection.close()

    return dict(row) if row else None


# -----------------------------------
# UPDATE COMPLAINT STATUS
# -----------------------------------

def update_complaint_status(
    complaint_id,
    new_status
):

    allowed_statuses = [
        "Submitted",
        "Under Review",
        "Assigned",
        "In Progress",
        "Resolved",
        "Rejected"
    ]

    if new_status not in allowed_statuses:
        raise ValueError("Invalid complaint status.")

    connection = get_connection()

    cursor = connection.execute("""
        UPDATE complaints
        SET status = ?
        WHERE complaint_id = ?
    """, (
        new_status,
        complaint_id
    ))

    connection.commit()

    updated = cursor.rowcount > 0

    connection.close()

    return updated


# -----------------------------------
# ASSIGN COMPLAINT TO DEPARTMENT
# -----------------------------------

def assign_complaint_department(
    complaint_id,
    assigned_department
):

    if not assigned_department or not assigned_department.strip():
        raise ValueError("Department name cannot be empty.")

    assigned_department = assigned_department.strip()

    connection = get_connection()

    cursor = connection.execute("""
        UPDATE complaints

        SET assigned_department = ?,
            assigned_at = ?

        WHERE complaint_id = ?

    """, (
        assigned_department,
        datetime.now().isoformat(timespec="seconds"),
        complaint_id
    ))

    connection.commit()

    updated = cursor.rowcount > 0

    connection.close()

    return updated


# -----------------------------------
# GET COMPLAINTS BY STATUS
# -----------------------------------

def get_complaints_by_status(status):

    connection = get_connection()

    rows = connection.execute("""
        SELECT *
        FROM complaints
        WHERE status = ?
        ORDER BY id DESC
    """, (status,)).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


# -----------------------------------
# GET COMPLAINT COUNTS
# -----------------------------------

def get_complaint_counts():

    connection = get_connection()

    rows = connection.execute("""
        SELECT status, COUNT(*) AS total
        FROM complaints
        GROUP BY status
    """).fetchall()

    connection.close()

    return {
        row["status"]: row["total"]
        for row in rows
    }


# -----------------------------------
# FIND POSSIBLE DUPLICATES
# -----------------------------------

def find_possible_duplicates(
    issue_type,
    description,
    location,
    latitude=None,
    longitude=None,
    max_results=5
):

    import re
    from difflib import SequenceMatcher
    from math import radians, sin, cos, sqrt, atan2

    def normalize(value):

        value = str(value or "").lower()

        value = re.sub(
            r"[^a-z0-9\s]",
            " ",
            value
        )

        return " ".join(value.split())

    def similarity(first, second):

        first = normalize(first)
        second = normalize(second)

        if not first or not second:
            return 0.0

        return SequenceMatcher(
            None,
            first,
            second
        ).ratio()

    def gps_distance(
        lat1,
        lon1,
        lat2,
        lon2
    ):

        earth_radius = 6371000

        lat1, lon1, lat2, lon2 = map(
            radians,
            [lat1, lon1, lat2, lon2]
        )

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            sin(dlat / 2) ** 2
            + cos(lat1)
            * cos(lat2)
            * sin(dlon / 2) ** 2
        )

        return earth_radius * 2 * atan2(
            sqrt(a),
            sqrt(1 - a)
        )

    connection = get_connection()

    rows = connection.execute("""
        SELECT
            complaint_id,
            issue_type,
            description,
            location,
            status,
            created_at,
            latitude,
            longitude

        FROM complaints

        ORDER BY id DESC
    """).fetchall()

    connection.close()

    possible_duplicates = []

    new_issue = normalize(issue_type)
    new_description = normalize(description)
    new_location = normalize(location)

    for row in rows:

        old = dict(row)

        old_issue = normalize(old["issue_type"])
        old_description = normalize(old["description"])
        old_location = normalize(old["location"])

        issue_match = (
            new_issue == old_issue
            or similarity(
                new_issue,
                old_issue
            ) >= 0.75
        )

        description_score = similarity(
            new_description,
            old_description
        )

        location_score = similarity(
            new_location,
            old_location
        )

        distance = None

        if (
            latitude is not None
            and longitude is not None
            and old["latitude"] is not None
            and old["longitude"] is not None
        ):

            distance = gps_distance(
                float(latitude),
                float(longitude),
                float(old["latitude"]),
                float(old["longitude"])
            )

        nearby_by_gps = (
            distance is not None
            and distance <= 250
        )

        nearby_by_text = (
            location_score >= 0.55
        )

        same_problem_area = (
            nearby_by_gps or nearby_by_text
        )

        is_possible_duplicate = (
            issue_match and (
                (
                    same_problem_area
                    and description_score >= 0.30
                )
                or description_score >= 0.70
            )
        )

        if is_possible_duplicate:

            possible_duplicates.append({

                "complaint_id": old["complaint_id"],

                "issue_type": old["issue_type"],

                "description": old["description"],

                "location": old["location"],

                "status": old["status"],

                "created_at": old["created_at"],

                "distance_m": (
                    round(distance, 1)
                    if distance is not None
                    else None
                ),

                "similarity": round(
                    description_score * 100,
                    1
                )

            })

    possible_duplicates.sort(
        key=lambda item: (
            item["distance_m"]
            if item["distance_m"] is not None
            else 999999,

            -item["similarity"]
        )
    )

    return possible_duplicates[:max_results]


# -----------------------------------
# INITIALIZE DATABASE AUTOMATICALLY
# -----------------------------------

initialize_database()
