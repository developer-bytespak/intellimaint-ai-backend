import psycopg2
from dotenv import load_dotenv
import os
from urllib.parse import urlparse

# Load environment variables from .env
load_dotenv()

# Get the DATABASE_URL from environment variable
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise ValueError("DATABASE_URL not set in environment variables.")

# Parse DATABASE_URL using urlparse
result = urlparse(database_url)
print(f"🔍 Parsed database URL: {result}")

# Configure database connection settings
DB_CONFIG = {
    "user": result.username,
    "password": result.password,
    "host": result.hostname,
    "port": result.port,
    "database": result.path[1:],  # Remove the leading '/'
}

# Connect to the database
try:
    connection = psycopg2.connect(**DB_CONFIG)
    print("Connection successful!")

    # Create a cursor and execute a simple query
    cursor = connection.cursor()
    cursor.execute("SELECT NOW();")
    result = cursor.fetchone()
    print("Current Time:", result)

    # Close cursor and connection
    cursor.close()
    connection.close()
    print("Connection closed.")

except Exception as e:
    print(f"Failed to connect: {e}")
