#!/usr/bin/env python3
"""Seed database with initial sample data"""

import psycopg2
import os

def seed_database():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cursor = conn.cursor()
    
    # Add seed data queries here
    print("Seeding database...")
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Database seeded successfully!")

if __name__ == "__main__":
    seed_database()

