#!/usr/bin/env python
"""Validate universal chunking output"""

import json
import re

def validate(filepath, name):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)
        chunks = data['chunks']

    print(f'=== {name} ===')
    print(f'Total chunks: {len(chunks)}')
    print()

    # Content type distribution
    types = {}
    for c in chunks:
        t = c['metadata']['content_type']
        types[t] = types.get(t, 0) + 1
    print('Content types:', types)
    print()

    # Embeddable count (narrative is embeddable)
    embeddable = sum(1 for c in chunks if c['metadata']['content_type'] == 'narrative')
    reference = len(chunks) - embeddable
    print(f'Embeddable (narrative): {embeddable} | Reference: {reference}')
    print()

    # Check for issues
    toc_chunks = sum(1 for c in chunks if '...' in c['content'])
    img_placeholders = sum(1 for c in chunks if 'image:' in c['content'].lower() and 'url:' in c['content'].lower())
    copyright_chunks = sum(1 for c in chunks if 'copyright' in c['content'].lower() or '©' in c['content'])
    table_placeholders = sum(1 for c in chunks if '[TABLE_PLACEHOLDER]' in c['content'])
    url_placeholders = sum(1 for c in chunks if re.search(r'\burl:\s*$', c['content'], re.MULTILINE | re.IGNORECASE))
    
    print(f'Quality checks:')
    print(f'  Chunks with dotted lines (TOC): {toc_chunks}')
    print(f'  Chunks with image placeholders: {img_placeholders}')
    print(f'  Chunks with copyright lines: {copyright_chunks}')
    print(f'  Chunks with [TABLE_PLACEHOLDER]: {table_placeholders}')
    print(f'  Chunks with "url:" placeholders: {url_placeholders}')
    
    # Check metadata structure
    first = chunks[0]
    print(f'  Metadata keys: {list(first["metadata"].keys())}')
    
    # Token range
    sizes = [c['token_count'] for c in chunks]
    print(f'  Token range: {min(sizes)} - {max(sizes)} (avg: {sum(sizes)//len(sizes)})')
    print()

    # Show first 3 narrative
    print('Sample NARRATIVE chunks (content_type=narrative):')
    count = 0
    for c in chunks:
        if c['metadata']['content_type'] == 'narrative' and count < 3:
            heading = c['heading'] or '(no heading)'
            content_preview = c['content'][:100].replace('\n', ' ')
            print(f'  [{c["chunk_index"]}] {heading[:50]}')
            print(f'      {content_preview}...')
            count += 1
    print()

    # Show first 3 reference
    print('Sample REFERENCE chunks (content_type=reference):')
    count = 0
    for c in chunks:
        if c['metadata']['content_type'] == 'reference' and count < 3:
            heading = c['heading'] or '(no heading)'
            content_preview = c['content'][:100].replace('\n', ' ')
            print(f'  [{c["chunk_index"]}] {heading[:50]}')
            print(f'      {content_preview}...')
            count += 1
    print()
    print('='*60)
    print()

# Validate both samples
validate('universal_sample2.json', 'WARRANTY MANUAL (sample2)')
validate('universal_sample3.json', 'PARTS CATALOG (sample3)')
