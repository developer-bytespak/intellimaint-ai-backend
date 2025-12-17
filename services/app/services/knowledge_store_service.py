import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

class KnowledgeStoreService:
    # Neon DATABASE_URL direct use karein
    DB_URL = os.getenv("DATABASE_URL")

    @staticmethod
    def create_knowledge_source(title, raw_content, source_type="pdf", model_id=None, user_id=None):
        conn = None
        try:
            # Database connection establish karna
            conn = psycopg2.connect(KnowledgeStoreService.DB_URL)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            word_count = len(raw_content.split())
            now = datetime.now()

            # SQL Query: Prisma schema ke mutabiq (snake_case mappings use karein)
            # @@map("knowledge_sources") ki wajah se table name knowledge_sources hai
            query = """
                INSERT INTO knowledge_sources 
                (id, title, source_type, raw_content, model_id, user_id, word_count, created_at, updated_at, metadata)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            
            import json
            params = (
                title, 
                source_type, 
                raw_content, 
                model_id, 
                user_id, 
                word_count, 
                now, 
                now, 
                json.dumps({"auto_extracted": True})
            )

            cur.execute(query, params)
            new_id = cur.fetchone()['id']
            
            conn.commit()
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