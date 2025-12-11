from scripts.ifixit.api_client import iFixitAPIClient
import json

client = iFixitAPIClient()

# Test 1: Check raw API response structure
print("=" * 80)
print("TEST 1: Raw API Response Structure")
print("=" * 80)
response = client._request_with_retry("https://www.ifixit.com/api/2.0/guides", params={"limit": 10, "offset": 0})
data = response.json()

print(f"Response type: {type(data)}")
print(f"Response keys (if dict): {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
print("\nFull response structure (first 2000 chars):")
print(json.dumps(data, indent=2)[:2000])

# Check for total count in various possible locations
print("\n" + "=" * 80)
print("TEST 2: Looking for Total Count")
print("=" * 80)
if isinstance(data, dict):
    print(f"  'total': {data.get('total')}")
    print(f"  'count': {data.get('count')}")
    print(f"  'totalResults': {data.get('totalResults')}")
    print(f"  'total_count': {data.get('total_count')}")
    print(f"  'totalItems': {data.get('totalItems')}")
    
    # Check if there's a results/data array
    if 'results' in data:
        print(f"\n  'results' array length: {len(data['results'])}")
    if 'data' in data:
        print(f"  'data' array length: {len(data['data'])}")
    if 'items' in data:
        print(f"  'items' array length: {len(data['items'])}")
else:
    print(f"  Response is a list with {len(data)} items")

# Test 3: Use the pagination method to see what it extracts
print("\n" + "=" * 80)
print("TEST 3: What Pagination Extracts")
print("=" * 80)
items, total = client._extract_results(data)
print(f"Extracted items: {len(items)}")
print(f"Extracted total: {total}")

# Test 4: Fetch multiple pages to see if total appears
print("\n" + "=" * 80)
print("TEST 4: Fetching Multiple Pages")
print("=" * 80)
all_collected = []
page_count = 0
for page in client.paginate("https://www.ifixit.com/api/2.0/guides", params={}, page_size=10000):
    all_collected.extend(page)
    page_count += 1
    print(f"Page {page_count}: Collected {len(page)} guides, Total so far: {len(all_collected)}")

print(f"\n✅ Total guides collected from {page_count} pages: {len(all_collected)}")
print("=" * 80)