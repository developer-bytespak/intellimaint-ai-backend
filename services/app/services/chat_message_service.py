

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


class ChatMessageService:
    DB_URL = os.getenv("DATABASE_URL")

    # 🔹 Create ONE pool per process
    _pool: ThreadedConnectionPool | None = None

    @classmethod
    def _get_pool(cls) -> ThreadedConnectionPool:
        if cls._pool is None:
            cls._pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,          # adjust if needed
                dsn=cls.DB_URL,
            )
        return cls._pool

    @classmethod
    def _get_conn(cls):
        return cls._get_pool().getconn()

    @classmethod
    def _put_conn(cls, conn):
        cls._get_pool().putconn(conn)


    # -----------------------------
    # WRITE: create chat session
    # -----------------------------
    @staticmethod
    def create_chat_session(session_id, user_id, status="active", user_text=None):
        if not session_id or not user_id:
            return

        pool = ChatMessageService._get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO chat_sessions (id, user_id, status, created_at, updated_at,title)
                VALUES (%s, %s, %s, now(), now(), %s)
                ON CONFLICT (id) DO NOTHING;
                """,
                (session_id, user_id, status, user_text),
            )
            conn.commit()
            cur.close()
        finally:
            pool.putconn(conn)

    # -----------------------------
    # READ: last messages
    # -----------------------------
    @staticmethod
    def get_last_messages(session_id, limit=5):
        if not session_id:
            return []

        pool = ChatMessageService._get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT role, content
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s;
            """, (session_id, limit))
            rows = cur.fetchall()
            cur.close()
            return list(reversed(rows))
        finally:
            pool.putconn(conn)

    # -----------------------------
    # READ: summary
    # -----------------------------
    @staticmethod
    def get_summary(session_id):
        if not session_id:
            return None

        pool = ChatMessageService._get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT context_summary
                FROM chat_sessions
                WHERE id = %s;
            """, (session_id,))
            row = cur.fetchone()
            cur.close()
            return row[0] if row else None
        finally:
            pool.putconn(conn)

    # -----------------------------
    # WRITE: save message
    # -----------------------------
    @staticmethod
    def save_chat_message(
        session_id,
        role,
        content,
        model=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
    ):
        pool = ChatMessageService._get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO chat_messages
                (id, session_id, role, content, model,
                 prompt_tokens, completion_tokens, total_tokens, created_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, now());
            """, (
                session_id,
                role,
                content,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
            ))
            conn.commit()
            cur.close()
        finally:
            pool.putconn(conn)

    # -----------------------------
    # WRITE: update summary
    # -----------------------------
    @staticmethod
    def update_summary(session_id, summary):
        pool = ChatMessageService._get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE chat_sessions
                SET context_summary = %s, updated_at = now()
                WHERE id = %s;
            """, (summary, session_id))
            conn.commit()
            cur.close()
        finally:
            pool.putconn(conn)

