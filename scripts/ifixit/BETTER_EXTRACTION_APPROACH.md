# Better Extraction Approach

## Current Problem

**Current Approach (Inefficient):**
- Query guides per device: `/guides?device=Time Capsule A1470`
- Returns 10,000+ guides (hitting safety limit)
- Many guides are unrelated to the device
- Same guides appear for multiple devices
- Very slow and wasteful

**Time Estimate:**
- 1,000 devices × 10,000 guides = 10,000,000 guide queries (hitting limit)
- Even with duplicate detection, this is extremely slow

## Better Approach

### Option 1: Query All Guides Directly (Recommended)

**Strategy:**
1. Query ALL guides without device filter: `/guides` (no params)
2. Use guide summary's `category` field to link to devices
3. Process each guide once, link to all applicable devices

**Benefits:**
- ✅ Fetch all guides once (no repetition)
- ✅ No 10,000 limit per device
- ✅ Much faster (one query instead of thousands)
- ✅ Process each guide only once

**How It Works:**
```python
# Step 1: Fetch all guides (paginated)
all_guides = api_client.get_guides(paginate=True, page_size=200)

# Step 2: For each guide, check its category
for guide in all_guides:
    category = guide.get("category")  # e.g., "PowerBook G3 Wallstreet"
    
    # Step 3: Find matching devices
    matching_devices = find_devices_by_category(category)
    
    # Step 4: Process guide once, link to all matching devices
    process_guide(guide, applicable_devices=matching_devices)
```

**Time Estimate:**
- Total guides in iFixit: ~50,000-100,000
- With page_size=200: ~250-500 API calls (vs 10,000,000+)
- **1000x faster!**

### Option 2: Query by Category

**Strategy:**
1. Query guides by category: `/guides?category=Mac`
2. Process guides for that category
3. Link to devices within that category

**Benefits:**
- ✅ More focused than per-device
- ✅ Still faster than current approach
- ✅ Can process category by category

**Limitation:**
- Still need to query multiple categories
- Less efficient than Option 1

## Implementation Plan

### Phase 1: Test Category Matching
1. Verify guide `category` field matches device paths
2. Test matching logic (exact match vs partial match)
3. Handle edge cases (category variations)

### Phase 2: Implement All-Guides Approach
1. Add method to fetch all guides (no device filter)
2. Add method to match guides to devices by category
3. Update collector to use new approach
4. Keep duplicate detection as safety net

### Phase 3: Optimize
1. Use larger page_size (200) for fewer API calls
2. Process guides in batches
3. Cache device lookups

## Example: Guide Category Matching

**Guide Summary:**
```json
{
  "guideid": 1,
  "category": "PowerBook G3 Wallstreet",
  "title": "PowerBook G3 Wallstreet Keyboard Replacement"
}
```

**Matching Devices:**
- `Mac/PowerBook/PowerBook G3 Wallstreet` ✅ Match
- `Mac/PowerBook/PowerBook G3 Lombard` ❌ No match

**Matching Logic:**
```python
def find_devices_for_guide(guide_category: str, all_devices: List[Dict]) -> List[str]:
    """Find devices that match guide category."""
    matching = []
    for device in all_devices:
        device_path = device.get("path", "")
        # Check if device path contains category
        if guide_category.lower() in device_path.lower():
            matching.append(device_path)
    return matching
```

## Expected Results

**Current Approach:**
- 1,000 devices × 10,000 guides = 10,000,000+ guide queries
- Time: Days/weeks

**Better Approach:**
- ~50,000-100,000 total guides
- ~250-500 API calls (page_size=200)
- Time: Hours

**Speed Improvement: 1000x faster!** 🚀

## Next Steps

1. ✅ Test all-guides query (DONE - works!)
2. ⏳ Test category matching logic
3. ⏳ Implement new collector approach
4. ⏳ Test with small dataset
5. ⏳ Run full extraction

Would you like me to implement this better approach?



