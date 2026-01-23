"""
Shared database connection pool for all services
Use this to avoid multiple pool conflicts
"""
import os
from psycopg2.pool import ThreadedConnectionPool


class SharedDBPool:
    """Singleton connection pool shared across all services"""
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_pool(cls) -> ThreadedConnectionPool:
        """Get or create the shared connection pool"""
        if cls._pool is None:
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                raise ValueError("DATABASE_URL environment variable not set")
            
            try:
                cls._pool = ThreadedConnectionPool(
                    minconn=5,    # Minimum connections
                    maxconn=20,   # Maximum connections
                    dsn=db_url
                )
                print("[DB_POOL] ✅ Shared connection pool initialized (5-20 connections)", flush=True)
            except Exception as e:
                print(f"[DB_POOL] ❌ Failed to create pool: {e}", flush=True)
                raise
        
        return cls._pool

    @classmethod
    def get_connection(cls):
        """Get a connection from the pool"""
        pool = cls.get_pool()
        return pool.getconn()

    @classmethod
    def return_connection(cls, conn):
        """Return a connection to the pool"""
        pool = cls.get_pool()
        pool.putconn(conn)

    @classmethod
    def close_all(cls):
        """Close all connections (use on shutdown)"""
        if cls._pool is not None:
            cls._pool.closeall()
            cls._pool = None
            print("[DB_POOL] ✅ All connections closed", flush=True)