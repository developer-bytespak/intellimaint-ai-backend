import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    "postgresql://neondb_owner:npg_VZPm1zThv7Or@ep-sweet-term-a400zy46-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"
)
cur = conn.cursor(cursor_factory=RealDictCursor)

umair_source_id = "d9c555ff-4ab2-482d-9f7f-89e4c5c4d094"

print("=== CHECKING IF CGPA GETS TRUNCATED ===")
cur.execute("""
    SELECT 
        chunk_index,
        content,
        LENGTH(content) as content_length
    FROM knowledge_chunks
    WHERE source_id = %s
    ORDER BY chunk_index
""", (umair_source_id,))

chunks = cur.fetchall()
for c in chunks:
    content = c['content']
    print(f"\nChunk {c['chunk_index']}: {c['content_length']} chars")
    
    # Check if CGPA is in this chunk
    if 'CGPA' in content:
        cgpa_pos = content.find('CGPA')
        print(f"  ✓ CGPA found at position {cgpa_pos}")
        print(f"  First 600 chars would include CGPA: {cgpa_pos < 600}")
        print(f"\n  First 600 chars:")
        print("  " + content[:600].replace('\n', '\n  '))
        print(f"\n  ...TRUNCATED... (remaining {c['content_length']-600} chars)")
        if cgpa_pos >= 600:
            print(f"\n  ⚠️ CGPA IS AFTER 600 CHARS - IT WOULD BE TRUNCATED!")
            print(f"     CGPA context: ...{content[cgpa_pos-50:cgpa_pos+50]}...")
    else:
        print(f"  ✗ No CGPA in this chunk")

conn.close()

conn.close()
