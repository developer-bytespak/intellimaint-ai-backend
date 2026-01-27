from pyexpat.errors import messages
from app.redis_client import redis_client
import json

import os
from psycopg2.extras import RealDictCursor
from app.services.shared_db_pool import SharedDBPool


class ChatMessageService:
    DB_URL = os.getenv("DATABASE_URL")

    # ✅ Use shared pool instead of separate pool
    @classmethod
    def _get_conn(cls):
        return SharedDBPool.get_connection()

    @classmethod
    def _put_conn(cls, conn):
        SharedDBPool.return_connection(conn)

    # -----------------------------
    # WRITE: create chat session
    # -----------------------------
    @staticmethod
    def create_chat_session(session_id, user_id, status="active", user_text=None):
        if not session_id or not user_id:
            return

        conn = ChatMessageService._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO chat_sessions (id, user_id, status, created_at, updated_at, title)
                VALUES (%s, %s, %s, now(), now(), %s)
                ON CONFLICT (id) DO NOTHING;
                """,
                (session_id, user_id, status, user_text),
            )
            conn.commit()
            cur.close()
        finally:
            ChatMessageService._put_conn(conn)

    # -----------------------------
    # READ: last messages
    # -----------------------------
    @staticmethod
    def get_last_messages(session_id, limit=5):
        if not session_id:
            return []
        
        cache_key = f"last_msgs:{session_id}:{limit}"

        cached = redis_client.get(cache_key)
        if cached:
            print(f"[ChatMessageService] 🔥 Cache hit for last_messages {cache_key}", flush=True)
            return json.loads(cached)

        conn = ChatMessageService._get_conn()
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
            messages = list(reversed(rows))

            redis_client.setex(
                cache_key,
                10,  # 🔥 short TTL (10 sec is perfect for voice)
                json.dumps(messages)
            )

            return messages
        except Exception as e:
            print(f"[ChatMessageService] ❌ get_last_messages failed: {e}", flush=True)
            return []
        finally:
            ChatMessageService._put_conn(conn)

    # -----------------------------
    # READ: summary
    # -----------------------------
    @staticmethod
    def get_summary(session_id):
        if not session_id:
            return None
        
        cache_key = f"summary:{session_id}:10"
        
        cached = redis_client.get(cache_key)
        if cached:
            return cached.encode("utf-8")

        conn = ChatMessageService._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT context_summary
                FROM chat_sessions
                WHERE id = %s;
            """, (session_id,))
            row = cur.fetchone()
            cur.close()
            summary =  row[0] if row else None
            if summary:
                redis_client.setex(
                    cache_key,
                    1800,  # 🔥 30 minutes (summary rarely changes)
                    summary
                )

            return summary
        except Exception as e:
            print(f"[ChatMessageService] ❌ get_summary failed: {e}", flush=True)
            return None
        finally:
            ChatMessageService._put_conn(conn)

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
        conn = ChatMessageService._get_conn()
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
            # after DB insert
            redis_client.delete(f"last_msgs:{session_id}:5")
            redis_client.delete(f"last_msgs:{session_id}:10")

        finally:
            ChatMessageService._put_conn(conn)

    # -----------------------------
    # WRITE: update summary
    # -----------------------------
    @staticmethod
    def update_summary(session_id, summary):
        conn = ChatMessageService._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE chat_sessions
                SET context_summary = %s, updated_at = now()
                WHERE id = %s;
            """, (summary, session_id))
            conn.commit()
            cur.close()
                    # 🔥 REDIS SYNC
            redis_client.setex(
                f"summary:{session_id}",
                1800,
                summary
            )
        finally:
            ChatMessageService._put_conn(conn)