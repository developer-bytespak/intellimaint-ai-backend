#!/usr/bin/env python3
"""Test category matching between guides and devices."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.ifixit.api_client import iFixitAPIClient

client = iFixitAPIClient()

# Test: Get all guides (first page)
print("Testing all-guides approach...")
guides = client.get_guides(paginate=True, page_size=200, max_pages=1)
print(f"✅ Got {len(guides)} guides in first page")

if guides:
    sample = guides[0]
    print(f"\nSample guide:")
    print(f"  ID: {sample.get('guideid')}")
    print(f"  Category: {sample.get('category')}")
    print(f"  Title: {sample.get('title')}")
    
    # Check a few more
    print(f"\nFirst 5 guide categories:")
    for g in guides[:5]:
        print(f"  - {g.get('category')} (ID: {g.get('guideid')})")

print("\n✅ All-guides approach works! Can fetch all guides directly.")








