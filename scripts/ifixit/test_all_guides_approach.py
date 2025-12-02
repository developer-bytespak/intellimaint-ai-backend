#!/usr/bin/env python3
"""Test if we can query all guides directly instead of per-device."""

import json
import logging
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.ifixit.api_client import iFixitAPIClient
from scripts.ifixit.config import ENDPOINTS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_all_guides_query(client: iFixitAPIClient):
    """Test querying all guides without device filter."""
    logger.info("=" * 80)
    logger.info("Testing: Query ALL Guides (no device filter)")
    logger.info("=" * 80)
    
    try:
        # Query guides without device filter
        logger.info("Fetching first page of all guides...")
        guides = client.get_guides(
            device_name=None,  # No device filter
            paginate=True,
            page_size=100,
            max_pages=1,  # Just test first page
        )
        
        logger.info(f"Response type: {type(guides)}")
        logger.info(f"Number of guides in first page: {len(guides)}")
        
        if guides:
            logger.info("\nSample guide structure:")
            sample = guides[0]
            logger.info(f"  Keys: {list(sample.keys())}")
            
            # Check if guide summary includes device information
            logger.info("\nChecking for device information in guide summary:")
            device_fields = ["device", "devices", "device_id", "device_name", "applicable_devices"]
            found_device_info = False
            for field in device_fields:
                if field in sample:
                    logger.info(f"  ✅ Found '{field}': {sample.get(field)}")
                    found_device_info = True
            
            if not found_device_info:
                logger.info("  ❌ No device information found in guide summary")
                logger.info("  (Will need to fetch guide detail to get device info)")
            
            # Show full sample guide
            logger.info(f"\nFull sample guide (first 2000 chars):")
            logger.info(json.dumps(sample, indent=2)[:2000])
            
            # Check for guide IDs
            guide_ids = [g.get("guideid") for g in guides[:10] if g.get("guideid")]
            logger.info(f"\nFirst 10 guide IDs: {guide_ids}")
            
        return guides
        
    except Exception as e:
        logger.error(f"Error testing all guides query: {e}", exc_info=True)
        return None


def test_guide_detail_for_devices(client: iFixitAPIClient, guide_id: int):
    """Check if guide detail includes device information."""
    logger.info("=" * 80)
    logger.info(f"Testing: Guide Detail for Device Information (guide_id={guide_id})")
    logger.info("=" * 80)
    
    try:
        guide_detail = client.get_guide_detail(guide_id)
        
        if guide_detail:
            logger.info("Checking guide detail for device information:")
            device_fields = ["device", "devices", "device_id", "device_name", "applicable_devices", "subject"]
            
            found_device_info = False
            for field in device_fields:
                if field in guide_detail:
                    value = guide_detail.get(field)
                    logger.info(f"  ✅ Found '{field}': {value}")
                    found_device_info = True
            
            if not found_device_info:
                logger.info("  ❌ No device information found in guide detail")
                logger.info(f"  Available keys: {list(guide_detail.keys())[:20]}")
            
            # Check if there's a URL that might contain device info
            if "url" in guide_detail:
                url = guide_detail.get("url", "")
                logger.info(f"\nGuide URL: {url}")
                # iFixit URLs often have device info in the path
                if "/" in url:
                    parts = url.split("/")
                    logger.info(f"  URL parts: {parts}")
            
        return guide_detail
        
    except Exception as e:
        logger.error(f"Error testing guide detail: {e}", exc_info=True)
        return None


def test_category_filter(client: iFixitAPIClient):
    """Test if we can filter guides by category."""
    logger.info("=" * 80)
    logger.info("Testing: Query Guides by Category")
    logger.info("=" * 80)
    
    try:
        # Try querying guides with category parameter
        url = ENDPOINTS["guides"]
        logger.info(f"Testing URL: {url}")
        
        # Test different parameter combinations
        test_params = [
            {"category": "Mac"},
            {"category": "Phone"},
            {"limit": 10},  # Just test pagination
        ]
        
        for params in test_params:
            logger.info(f"\nTesting params: {params}")
            try:
                response = client._request_with_retry(url, params=params)
                data = response.json()
                logger.info(f"  Response type: {type(data)}")
                if isinstance(data, dict):
                    logger.info(f"  Keys: {list(data.keys())}")
                    if "data" in data or "results" in data:
                        items = data.get("data") or data.get("results", [])
                        logger.info(f"  ✅ Got {len(items)} items")
                    else:
                        logger.info(f"  Response: {json.dumps(data, indent=2)[:500]}")
                elif isinstance(data, list):
                    logger.info(f"  ✅ Got {len(data)} items")
            except Exception as e:
                logger.warning(f"  ❌ Failed with params {params}: {e}")
        
    except Exception as e:
        logger.error(f"Error testing category filter: {e}", exc_info=True)


def main():
    """Run all tests."""
    logger.info("Starting All Guides Approach Tests")
    logger.info(f"API Base URL: {ENDPOINTS.get('guides', 'N/A')}")
    
    client = iFixitAPIClient()
    
    # Test 1: Query all guides directly
    guides = test_all_guides_query(client)
    
    # Test 2: Check if guide detail has device info
    if guides and len(guides) > 0:
        guide_id = guides[0].get("guideid")
        if guide_id:
            test_guide_detail_for_devices(client, int(guide_id))
    
    # Test 3: Try category filter
    test_category_filter(client)
    
    logger.info("\n" + "=" * 80)
    logger.info("All Guides Approach Tests Complete")
    logger.info("=" * 80)
    logger.info("\n💡 Next Steps:")
    logger.info("  1. If guides can be queried without device filter, we can fetch all once")
    logger.info("  2. If guide detail includes device info, we can link guides to devices")
    logger.info("  3. This would be MUCH faster than querying per-device!")


if __name__ == "__main__":
    main()








