#!/usr/bin/env python3
"""
Example: Chunking + Embeddings Integration with Database Schema

This script demonstrates a complete workflow for knowledge_chunks table:
1. Read extracted PDF markdown
2. Chunk the text using pdf_text_chunker.py
3. Prepare for embedding
4. (Optional) Call an embedding API
5. Output ready for database insertion

Usage:
    python example_chunking_to_embeddings.py \
        --input sample.md \
        --source-id 550e8400-e29b-41d4-a716-446655440000 \
        --chunks-output chunks.json \
        --embeddings-output embeddings.json
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional


class EmbeddingPrep:
    """Prepare chunks for embedding (knowledge_chunks schema)"""

    @staticmethod
    def load_chunks(json_path: str) -> List[Dict[str, Any]]:
        """Load chunks from JSON file (knowledge_chunks schema)"""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("chunks", [])

    @staticmethod
    def filter_chunks(
        chunks: List[Dict[str, Any]],
        min_words: int = 10,
        max_words: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Filter chunks by size

        Args:
            chunks: Input chunks
            min_words: Minimum word count (skip smaller chunks)
            max_words: Maximum word count (skip larger chunks)
        """
        filtered = [
            c
            for c in chunks
            if min_words <= c["metadata"]["word_count"] <= max_words
        ]

        skipped = len(chunks) - len(filtered)
        if skipped > 0:
            print(f"⚠️  Filtered out {skipped} chunks (too small or too large)")

        return filtered

    @staticmethod
    def prepare_for_embedding(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare chunks for embedding

        Returns chunks with:
        - Cleaned text
        - Metadata for context
        - Token counts
        """
        prepared = []

        for chunk in chunks:
            # Clean text
            text = chunk["content"].strip()

            # Remove excessive whitespace
            text = " ".join(text.split())

            prepared_chunk = {
                "chunk_index": chunk["chunk_index"],
                "text": text,
                "heading": chunk["heading"],
                "token_count": chunk["token_count"],
                "metadata": chunk["metadata"],
                "source_id": chunk.get("source_id"),  # If provided
            }

            prepared.append(prepared_chunk)

        return prepared

    @staticmethod
    def add_metadata_context(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Add section context to chunks for better embeddings

        This helps embeddings understand the chunk's context
        """
        for chunk in chunks:
            # Build context prefix from metadata
            context_parts = []

            if chunk["heading"]:
                context_parts.append(f"[Section: {chunk['heading']}]")

            if chunk["metadata"].get("is_procedure"):
                context_parts.append("[Procedure/Instructions]")

            if chunk["metadata"].get("is_table"):
                context_parts.append("[Table/Data]")

            section_context = " ".join(context_parts) + " " if context_parts else ""

            chunk["embedding_context"] = section_context
            chunk["text_with_context"] = section_context + chunk["text"]

        return chunks


class MockEmbeddingAPI:
    """Mock embedding API for testing (not a real API)"""

    @staticmethod
    def embed(text: str, model: str = "mock-embed-v1") -> List[float]:
        """
        Mock embedding function (1536 dims to match VECTOR(1536))

        In production, replace with real API calls:
        - OpenAI: text-embedding-3-small (1536 dims)
        - Cohere: embed-english-v3.0
        - HuggingFace: sentence-transformers/all-MiniLM-L6-v2
        """
        import hashlib

        hash_obj = hashlib.md5(text.encode())
        hash_int = int(hash_obj.hexdigest(), 16)

        # Generate deterministic but varied 1536-dim vector (matches VECTOR(1536))
        embedding = [
            ((hash_int + i) % 1000) / 1000.0 for i in range(1536)
        ]

        return embedding


class EmbeddingPipeline:
    """Complete pipeline from chunks to embeddings (matches database schema)"""

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
        use_mock: bool = True,
    ):
        """
        Initialize pipeline

        Args:
            embedding_model: Model to use for embeddings
            use_mock: If True, use mock embeddings (for testing)
        """
        self.embedding_model = embedding_model
        self.use_mock = use_mock
        self.prep = EmbeddingPrep()

    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Embed all chunks

        Returns chunks with embedding field populated (1536 dims)
        """
        print(f"Embedding {len(chunks)} chunks using {self.embedding_model}...")

        for i, chunk in enumerate(chunks):
            # Show progress
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i + 1}/{len(chunks)}")

            # Get text to embed
            text = chunk.get("text_with_context", chunk["text"])

            # Embed
            if self.use_mock:
                embedding = MockEmbeddingAPI.embed(text, self.embedding_model)
            else:
                embedding = self._embed_real(text)

            chunk["embedding"] = embedding

        return chunks

    def _embed_real(self, text: str) -> List[float]:
        """Call real embedding API (not implemented)"""
        raise NotImplementedError(
            "Real embedding API not implemented. Use use_mock=True or implement this method."
        )

    def process(
        self,
        chunks_json_path: str,
        filter_min_words: int = 10,
        filter_max_words: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Complete processing pipeline

        Args:
            chunks_json_path: Path to chunks.json file
            filter_min_words: Minimum chunk size
            filter_max_words: Maximum chunk size

        Returns:
            Chunks with embeddings ready for database insertion
        """
        # Load
        print(f"Loading chunks from {chunks_json_path}...")
        chunks = self.prep.load_chunks(chunks_json_path)
        print(f"  Loaded {len(chunks)} chunks")

        # Filter
        print(f"Filtering chunks (min: {filter_min_words} words, max: {filter_max_words} words)...")
        chunks = self.prep.filter_chunks(chunks, filter_min_words, filter_max_words)
        print(f"  {len(chunks)} chunks after filtering")

        # Prepare
        print("Preparing chunks for embedding...")
        chunks = self.prep.prepare_for_embedding(chunks)

        # Add context
        print("Adding section context...")
        chunks = self.prep.add_metadata_context(chunks)

        # Embed
        print(f"Embedding chunks ({self.embedding_model})...")
        chunks = self.embed_chunks(chunks)

        return chunks

    def save_embeddings(
        self,
        chunks: List[Dict[str, Any]],
        output_path: str,
        include_embedding_vectors: bool = True,
    ) -> None:
        """
        Save embeddings to JSON (ready for database insertion)
        
        Output format matches knowledge_chunks table schema
        """
        output = {
            "metadata": {
                "total_chunks": len(chunks),
                "embedding_model": self.embedding_model,
                "embedding_dimensions": 1536 if chunks else 0,
                "include_vectors": include_embedding_vectors,
            },
            "chunks": [],
        }

        for chunk in chunks:
            chunk_dict = {
                "chunk_index": chunk["chunk_index"],
                "heading": chunk["heading"],
                "content": chunk["text"],
                "token_count": chunk["token_count"],
                "metadata": chunk["metadata"],
            }

            # Include source_id if provided
            if chunk.get("source_id"):
                chunk_dict["source_id"] = chunk["source_id"]

            # Include embedding vector if requested
            if include_embedding_vectors:
                chunk_dict["embedding"] = chunk["embedding"]

            output["chunks"].append(chunk_dict)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        print(f"✓ Saved embeddings to {output_path}")
        print(f"  Format: knowledge_chunks table schema")
        print(f"  Embedding dimensions: {output['metadata']['embedding_dimensions']}")
        print(f"  Include vectors: {include_embedding_vectors}")


def main():
    parser = argparse.ArgumentParser(
        description="Chunk PDF text and prepare for embedding with database schema"
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input markdown file with extracted PDF text",
    )
    parser.add_argument(
        "-s",
        "--source-id",
        help="UUID of the knowledge source (for database insertion)",
    )
    parser.add_argument(
        "-c",
        "--chunks-output",
        required=True,
        help="Output JSON file for chunks",
    )
    parser.add_argument(
        "-e",
        "--embeddings-output",
        help="Output JSON file for embeddings",
    )
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-small",
        help="Embedding model (default: text-embedding-3-small)",
    )
    parser.add_argument(
        "--skip-embedding",
        action="store_true",
        help="Skip embedding step (only chunk)",
    )
    parser.add_argument(
        "--min-chunk-words",
        type=int,
        default=10,
        help="Minimum words per chunk",
    )
    parser.add_argument(
        "--max-chunk-words",
        type=int,
        default=5000,
        help="Maximum words per chunk",
    )
    parser.add_argument(
        "--use-mock-embeddings",
        action="store_true",
        default=True,
        help="Use mock embeddings (for testing)",
    )
    parser.add_argument(
        "--no-vectors",
        action="store_true",
        help="Don't include embedding vectors in output (save space)",
    )

    args = parser.parse_args()

    # Step 1: Chunk the PDF text
    print("=" * 80)
    print("STEP 1: Chunking PDF Text (knowledge_chunks schema)")
    print("=" * 80)

    from pdf_text_chunker import PDFTextChunkingPipeline

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1

    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    pipeline = PDFTextChunkingPipeline()
    chunks = pipeline.process(text)
    pipeline.save_chunks(chunks, args.chunks_output, source_id=args.source_id)

    print(f"\n✓ Chunks saved to {args.chunks_output}")

    # Step 2: Embedding (optional)
    if not args.skip_embedding:
        print("\n" + "=" * 80)
        print("STEP 2: Adding Embeddings (VECTOR(1536))")
        print("=" * 80)

        if not args.embeddings_output:
            args.embeddings_output = Path(args.chunks_output).stem + "_embeddings.json"

        embedding_pipeline = EmbeddingPipeline(
            embedding_model=args.embedding_model,
            use_mock=args.use_mock_embeddings,
        )

        chunks_with_embeddings = embedding_pipeline.process(
            args.chunks_output,
            filter_min_words=args.min_chunk_words,
            filter_max_words=args.max_chunk_words,
        )

        embedding_pipeline.save_embeddings(
            chunks_with_embeddings,
            args.embeddings_output,
            include_embedding_vectors=not args.no_vectors,
        )

        print(f"✓ Embeddings saved to {args.embeddings_output}")

    print("\n" + "=" * 80)
    print("✅ Complete!")
    print("=" * 80)
    print(f"\nDatabase Schema: knowledge_chunks")
    print(f"Fields: chunk_index, heading, content, token_count, metadata (JSONB), embedding (VECTOR(1536))")
    print(f"\nOutputs:")
    print(f"  Chunks: {args.chunks_output}")
    if args.embeddings_output and not args.skip_embedding:
        print(f"  Embeddings: {args.embeddings_output}")
    if args.source_id:
        print(f"  Source ID: {args.source_id}")

    return 0


if __name__ == "__main__":
    exit(main())
