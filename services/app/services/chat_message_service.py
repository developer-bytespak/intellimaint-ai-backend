# import os
# import psycopg2
# from psycopg2.extras import RealDictCursor
# from datetime import datetime


# class ChatMessageService:
#     DB_URL = os.getenv("DATABASE_URL")

#     # -----------------------------
#     # Create Chat Session
#     # -----------------------------
#     @staticmethod
#     def create_chat_session(user_id, title=None, equipment_context=None, context_summary=None):
#         conn = None
#         try:
#             conn = psycopg2.connect(ChatMessageService.DB_URL)
#             cur = conn.cursor(cursor_factory=RealDictCursor)

#             now = datetime.now()

#             query = """
#                 INSERT INTO chat_sessions
#                 (id, user_id, title, equipment_context, context_summary, status, created_at, updated_at)
#                 VALUES (gen_random_uuid(), %s, %s, %s, %s, 'active', %s, %s)
#                 RETURNING id;
#             """

#             params = (
#                 user_id,
#                 title,
#                 equipment_context if equipment_context else [],
#                 context_summary,
#                 now,
#                 now
#             )

#             cur.execute(query, params)
#             session_id = cur.fetchone()["id"]

#             conn.commit()
#             return {"session_id": str(session_id)}

#         except Exception as e:
#             if conn:
#                 conn.rollback()
#             print(f"[ChatSession] ❌ Error: {e}")
#             return None
#         finally:
#             if conn:
#                 cur.close()
#                 conn.close()

#     # -----------------------------
#     # Save Chat Message
#     # -----------------------------
#     @staticmethod
#     def save_chat_message(
#         session_id,
#         role,
#         content,
#         model=None,
#         prompt_tokens=None,
#         completion_tokens=None,
#         total_tokens=None,
#         is_stopped=False
#     ):
#         conn = None
#         try:
#             conn = psycopg2.connect(ChatMessageService.DB_URL)
#             cur = conn.cursor(cursor_factory=RealDictCursor)

#             now = datetime.now()

#             query = """
#                 INSERT INTO chat_messages
#                 (
#                     id,
#                     session_id,
#                     role,
#                     content,
#                     model,
#                     prompt_tokens,
#                     completion_tokens,
#                     total_tokens,
#                     is_stopped,
#                     created_at
#                 )
#                 VALUES
#                 (
#                     gen_random_uuid(),
#                     %s, %s, %s, %s, %s, %s, %s, %s, %s
#                 )
#                 RETURNING id;
#             """

#             params = (
#                 session_id,
#                 role,
#                 content,
#                 model,
#                 prompt_tokens,
#                 completion_tokens,
#                 total_tokens,
#                 is_stopped,
#                 now
#             )

#             cur.execute(query, params)
#             message_id = cur.fetchone()["id"]

#             conn.commit()
#             return {"message_id": str(message_id)}

#         except Exception as e:
#             if conn:
#                 conn.rollback()
#             print(f"[ChatMessage] ❌ Error: {e}")
#             return None
#         finally:
#             if conn:
#                 cur.close()
#                 conn.close()




import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime


class ChatMessageService:
    DB_URL = os.getenv("DATABASE_URL")

    @staticmethod
    def create_chat_session(user_id, title=None):
        conn = psycopg2.connect(ChatMessageService.DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        now = datetime.now()
        cur.execute("""
            INSERT INTO chat_sessions
            (id, user_id, title, status, created_at, updated_at)
            VALUES (gen_random_uuid(), %s, %s, 'active', %s, %s)
            RETURNING id;
        """, (user_id, title, now, now))

        sid = cur.fetchone()["id"]
        conn.commit()
        cur.close()
        conn.close()
        return {"session_id": str(sid)}

    @staticmethod
    def save_chat_message(
        session_id, role, content,
        model=None, prompt_tokens=None,
        completion_tokens=None, total_tokens=None
    ):
        conn = psycopg2.connect(ChatMessageService.DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            INSERT INTO chat_messages
            (id, session_id, role, content, model,
             prompt_tokens, completion_tokens, total_tokens, created_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, now());
        """, (
            session_id, role, content, model,
            prompt_tokens, completion_tokens, total_tokens
        ))

        conn.commit()
        cur.close()
        conn.close()
