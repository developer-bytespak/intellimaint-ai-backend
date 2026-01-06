import os
import psycopg2
import json
import logging
from psycopg2.extras import RealDictCursor
from datetime import datetime

logger = logging.getLogger(__name__)


class KnowledgeStoreService:
    # Neon DATABASE_URL environment variable se lein
    DB_URL = os.getenv("DATABASE_URL")

    @staticmethod
    def create_knowledge_source(
        title,
        raw_content,
        source_type="pdf",
        model_id=None,
        user_id=None,
        email=None,
        role=None,
        name=None,
        auto_chunk=True,
    ):
        """
        Create a knowledge source and optionally trigger chunking.

        Args:
            title: Document title
            raw_content: Extracted text content
            source_type: Type of source (pdf, etc.)
            model_id: Associated model ID
            user_id: User who uploaded
            email, role, name: User metadata
            auto_chunk: If True, automatically create chunks after saving (default: True)

        Returns:
            Dict with id, status, and chunks_created (if auto_chunk)
        """
        conn = None
        try:
            # Metadata object taiyar karein kyunke email/role ke liye alag columns nahi hain
            user_metadata = {
                "auto_extracted": True,
                "user_info": {"email": email, "role": role, "name": name},
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

            cur.execute(query, params)
            result = cur.fetchone()
            new_id = str(result["id"])

            conn.commit()
            print(f"Successfully saved to Neon DB with ID: {new_id}")

            # Close cursor before chunking
            cur.close()
            conn.close()
            conn = None

            # Auto-trigger chunking if enabled
            chunks_created = 0
            if auto_chunk:
                try:
                    chunks_created = KnowledgeStoreService._trigger_chunking(new_id)
                    print(
                        f"Auto-chunking completed: {chunks_created} chunks created for {new_id}"
                    )
                except Exception as chunk_err:
                    print(f"Auto-chunking failed for {new_id}: {chunk_err}")
                    # Don't fail the whole operation, just log the error
                    chunks_created = -1  # Indicates error

            return {"id": new_id, "status": "success", "chunks_created": chunks_created}

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Neon DB Storage Failed: {e}")
            return None
        finally:
            if conn:
                try:
                    cur.close()
                except:
                    pass
                conn.close()

    @staticmethod
    def get_chunks_by_source_id(source_id: str):
        """
        Source ID se saare chunks fetch karta hai
        Returns: List of dicts with id, chunk_index, content
        """
        conn = None
        try:
            conn = psycopg2.connect(KnowledgeStoreService.DB_URL)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT id, chunk_index, content 
                FROM knowledge_chunks 
                WHERE source_id = %s 
                ORDER BY chunk_index ASC;
            """

            cur.execute(query, (source_id,))
            chunks = cur.fetchall()

            print(f"Fetched {len(chunks)} chunks for source_id: {source_id}")
            return chunks

        except Exception as e:
            print(f"Error fetching chunks: {e}")
            return None
        finally:
            if conn:
                cur.close()
                conn.close()

    @staticmethod
    def update_chunk_embeddings(chunk_embeddings: list):
        """
        Har chunk ki embedding update karta hai
        chunk_embeddings: List of dicts with 'chunk_id' and 'embedding'
        """
        conn = None
        try:
            conn = psycopg2.connect(KnowledgeStoreService.DB_URL)
            cur = conn.cursor()

            updated_count = 0

            for item in chunk_embeddings:
                chunk_id = item["chunk_id"]
                embedding = item["embedding"]

                # pgvector format mein embedding store karna
                query = """
                    UPDATE knowledge_chunks 
                    SET embedding = %s::vector
                    WHERE id = %s;
                """

                cur.execute(query, (str(embedding), chunk_id))
                updated_count += 1

            conn.commit()
            print(f"Successfully updated {updated_count} chunk embeddings")
            return {"updated": updated_count, "status": "success"}

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error updating embeddings: {e}")
            return None
        finally:
            if conn:
                cur.close()
                conn.close()

    @staticmethod
    def _trigger_chunking(source_id: str) -> int:
        """
        Trigger chunking for a knowledge source.

        Args:
            source_id: UUID of the knowledge source

        Returns:
            Number of chunks created
        """
        from .chunker import process_source

        try:
            print(f"Starting chunking for source_id: {source_id}")
            result = process_source(source_id, dry_run=False, overwrite=True)
            return result.get("num_chunks", 0)
        except Exception as e:
            print(f"Chunking failed for {source_id}: {e}")
            raise
