import os
import psycopg2
import json
from psycopg2.extras import RealDictCursor
from datetime import datetime

class KnowledgeStoreService:
    # Neon DATABASE_URL environment variable se lein
    DB_URL = os.getenv("DATABASE_URL")

    @staticmethod
    def create_knowledge_source(title, raw_content, source_type="pdf", model_id=None, user_id=None, email=None, role=None, name=None):
        conn = None
        try:
            # Metadata object taiyar karein kyunke email/role ke liye alag columns nahi hain
            user_metadata = {
                "auto_extracted": True,
                "user_info": {
                    "email": email,
                    "role": role,
                    "name": name
                }
            }
            
            print(f"Storing knowledge source for User ID: {user_id}")
            
            # Database connection
            conn = psycopg2.connect(KnowledgeStoreService.DB_URL)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            word_count = len(raw_content.split())
            now = datetime.now()

            # SQL Query: Prisma schema ke exact columns ke mutabiq
            # Humne 9 columns specify kiye hain (id automatically gen_random_uuid() se banega)
            query = """
                INSERT INTO knowledge_sources 
                (id, title, source_type, raw_content, model_id, user_id, word_count, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            
            # Params tuple: Isme exact 9 values honi chahiye (jitne %s hain)
            params = (
                title, 
                source_type, 
                raw_content, 
                model_id if model_id else None, 
                user_id if user_id else None, 
                word_count, 
                now, 
                now, 
                # json.dumps(user_metadata) # Metadata JSON field
            )

            # cur.execute(query, params)
            # result = cur.fetchone()
            # new_id = result['id']
            
            # conn.commit()
            print(f"Successfully saved to Neon DB with ID: {new_id}")
            return {"id": str(new_id), "status": "success"}

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Neon DB Storage Failed: {e}")
            return None
        finally:
            if conn:
                cur.close()
                conn.close()