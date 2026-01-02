#!/usr/bin/env python3
"""
Test Chunking with Overlap
===========================

Process a sample markdown file and output JSON with overlap chunks.

Usage:
    python test_chunking_overlap.py pdf_samples/sample1.md output_chunks.json
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, '.')
from pdf_universal_chunker import UniversalChunkingPipeline


def main():
    if len(sys.argv) < 3:
        print("Usage: python test_chunking_overlap.py <input_file.md> <output_file.json>")
        print("\nExamples:")
        print("  python test_chunking_overlap.py pdf_samples/sample1.md chunks.json")
        print("  python test_chunking_overlap.py pdf_samples/sample2.md results.json")
        return 1
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Check input exists
    if not Path(input_file).exists():
        print(f"❌ Input file not found: {input_file}")
        return 1
    
    try:
        print(f"\n📖 Processing: {input_file}")
        
        # Read file
        with open(input_file, 'r', encoding='utf-8') as f:
            text = f.read()
        
        print(f"   File size: {len(text)} chars")
        
        # Process through pipeline
        pipeline = UniversalChunkingPipeline()
        chunks = pipeline.process(text)
        
        print(f"   ✓ Created {len(chunks)} chunks")
        
        # Build JSON output
        output_data = {
            "source_file": input_file,
            "chunks": [],
            "summary": {
                "total_chunks": len(chunks),
                "total_tokens": sum(c.token_count for c in chunks),
                "total_chars": sum(len(c.content) for c in chunks),
                "has_overlap": any("has_overlap" in c.metadata for c in chunks),
            }
        }
        
        # Add each chunk
        for chunk in chunks:
            chunk_data = {
                "chunk_index": chunk.chunk_index,
                "heading": chunk.heading,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata,
            }
            output_data["chunks"].append(chunk_data)
        
        # Save to JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Success!")
        print(f"   Output: {output_file}")
        print(f"\n📊 Summary:")
        print(f"   Total chunks: {output_data['summary']['total_chunks']}")
        print(f"   Total tokens: {output_data['summary']['total_tokens']}")
        print(f"   Has overlap: {output_data['summary']['has_overlap']}")
        
        # Show first 3 chunks
        print(f"\n📝 First 3 chunks:")
        for chunk in chunks[:3]:
            heading = chunk.heading or "(no heading)"
            overlap = " [OVERLAP]" if chunk.metadata.get("has_overlap") else ""
            print(f"   [{chunk.chunk_index}] {heading}{overlap} ({chunk.token_count} tokens)")
            print(f"       Content: {chunk.content[:80]}...")
        
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
