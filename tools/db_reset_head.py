import os
import sys

import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file at the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
dotenv_path = os.path.join(project_root, ".env")
if not os.path.exists(dotenv_path):
    print(f"ERROR: .env file not found at {dotenv_path}")
    sys.exit(1)
load_dotenv(dotenv_path)

# --- CONFIGURATION ---
# This is the last VALID revision ID from your alembic/versions folder
CORRECT_REVISION_ID = "ca7e25511046"
# --- END CONFIGURATION ---


def reset_alembic_head():
    """
    Directly connects to the database and updates the alembic_version table
    to fix a corrupted or divergent head state.
    """
    conn = None
    try:
        # Get DB connection details from environment variables for host access
        db_url = os.environ.get("HOST_DATABASE_URL")
        if not db_url:
            raise ValueError(
                "HOST_DATABASE_URL not found in your .env file. Please ensure it is set, e.g., HOST_DATABASE_URL=postgresql://user:password@localhost:5432/portfolio_db"
            )

        print("Connecting to the database...")
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        print(f"Attempting to reset alembic head to revision: {CORRECT_REVISION_ID}")

        # The SQL command to force-update the version number
        sql_command = "UPDATE alembic_version SET version_num = %s"

        cursor.execute(sql_command, (CORRECT_REVISION_ID,))

        if cursor.rowcount == 0:
            print(
                "WARNING: The UPDATE command affected 0 rows. This might mean the table was empty."
            )
            print("Attempting to INSERT the version instead.")
            insert_sql = "INSERT INTO alembic_version (version_num) VALUES (%s)"
            cursor.execute(insert_sql, (CORRECT_REVISION_ID,))

        conn.commit()

        print("\nSUCCESS: The database's alembic version has been reset.")
        print("You can now safely run 'alembic revision --autogenerate' again.")

        cursor.close()

    except psycopg2.Error as e:
        print(f"\nERROR: A database error occurred: {e}")
        print(
            "Please ensure PostgreSQL is running in Docker and is accessible "
            "from your host machine."
        )
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        if conn is not None:
            conn.close()
            print("Database connection closed.")


if __name__ == "__main__":
    reset_alembic_head()
