#!/usr/bin/env python3
"""Test script to verify iFixit API endpoints and inspect response structures."""

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


def test_categories_endpoint(client: iFixitAPIClient):
    """Test the categories endpoint and show structure."""
    logger.info("=" * 80)
    logger.info("Testing Categories Endpoint")
    logger.info("=" * 80)
    
    try:
        categories = client.get_categories()
        logger.info(f"Categories response type: {type(categories)}")
        
        if isinstance(categories, dict):
            logger.info(f"Top-level categories: {list(categories.keys())[:10]}")
            logger.info(f"Total top-level categories: {len(categories)}")
            
            # Show structure of one category
            if categories:
                first_key = list(categories.keys())[0]
                first_value = categories[first_key]
                logger.info(f"\nSample category '{first_key}':")
                logger.info(f"  Type: {type(first_value)}")
                if isinstance(first_value, dict):
                    logger.info(f"  Subcategories/devices: {list(first_value.keys())[:5]}")
        
        return categories
    except Exception as e:
        logger.error(f"Error testing categories endpoint: {e}", exc_info=True)
        return None


def test_devices_from_tree(categories: dict, category: str = "Phone"):
    """Extract devices from category tree (as the collector does)."""
    logger.info("=" * 80)
    logger.info(f"Extracting Devices from Category Tree: {category}")
    logger.info("=" * 80)
    
    try:
        if category not in categories:
            logger.warning(f"Category '{category}' not found in categories")
            return []
        
        # Extract devices from tree (same logic as collector)
        def extract_devices(tree, prefix=""):
            devices = []
            for key, value in tree.items():
                current_path = f"{prefix}/{key}" if prefix else key
                if value is None:
                    devices.append({
                        "title": key,
                        "namespace": current_path,
                        "path": current_path,
                    })
                elif isinstance(value, dict):
                    devices.extend(extract_devices(value, current_path))
            return devices
        
        category_tree = categories.get(category, {})
        devices = extract_devices(category_tree, category)
        
        logger.info(f"Number of devices found: {len(devices)}")
        
        if devices:
            logger.info(f"\nSample device structure:")
            sample = devices[0]
            logger.info(f"  Keys: {list(sample.keys())}")
            logger.info(f"  Sample device: {json.dumps(sample, indent=2)}")
        
        return devices
    except Exception as e:
        logger.error(f"Error extracting devices: {e}", exc_info=True)
        return None


def test_guides_endpoint(client: iFixitAPIClient, device_name: str = "Phone/iPhone/iPhone 4"):
    """Test the guides endpoint for a device."""
    logger.info("=" * 80)
    logger.info(f"Testing Guides Endpoint for device: {device_name}")
    logger.info("=" * 80)
    
    try:
        guides = client.get_guides(device_name=device_name)
        logger.info(f"Guides response type: {type(guides)}")
        logger.info(f"Number of guides: {len(guides)}")
        
        if guides:
            logger.info(f"\nSample guide summary structure:")
            sample = guides[0]
            logger.info(f"  Keys: {list(sample.keys())}")
            logger.info(f"  Sample guide: {json.dumps(sample, indent=2)[:1000]}")
            
            # Get guide ID for detail test
            guide_id = sample.get("guideid")
            if guide_id:
                return int(guide_id)
        
        return None
    except Exception as e:
        logger.error(f"Error testing guides endpoint: {e}", exc_info=True)
        return None


def test_guide_detail_endpoint(client: iFixitAPIClient, guide_id: int):
    """Test the guide detail endpoint and show full structure."""
    logger.info("=" * 80)
    logger.info(f"Testing Guide Detail Endpoint for guide_id: {guide_id}")
    logger.info("=" * 80)
    
    try:
        guide_detail = client.get_guide_detail(guide_id)
        
        if guide_detail:
            logger.info(f"Guide detail response type: {type(guide_detail)}")
            logger.info(f"Top-level keys: {list(guide_detail.keys())}")
            
            # Save full structure to file for inspection
            output_file = Path(__file__).parent / "api_response_sample.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(guide_detail, f, indent=2, ensure_ascii=False)
            logger.info(f"\nFull guide detail saved to: {output_file}")
            
            # Analyze structure
            logger.info("\n" + "=" * 80)
            logger.info("Guide Detail Structure Analysis")
            logger.info("=" * 80)
            
            # Check for steps
            steps = guide_detail.get("steps", [])
            logger.info(f"Number of steps: {len(steps)}")
            
            if steps:
                logger.info("\nStep structure analysis:")
                sample_step = steps[0]
                logger.info(f"  Step keys: {list(sample_step.keys())}")
                
                # Check for lines in step
                lines = sample_step.get("lines", [])
                logger.info(f"  Number of lines in first step: {len(lines)}")
                
                if lines:
                    logger.info("\n  Line types found:")
                    line_types = set()
                    for line in lines[:20]:  # Check first 20 lines
                        line_type = line.get("type")
                        if line_type:
                            line_types.add(line_type)
                    logger.info(f"    {sorted(line_types)}")
                    
                    # Show sample of each line type
                    logger.info("\n  Sample lines by type:")
                    for line_type in sorted(line_types):
                        sample_line = next((l for l in lines if l.get("type") == line_type), None)
                        if sample_line:
                            logger.info(f"    {line_type}: {json.dumps(sample_line, indent=6)[:200]}")
                
                # Check for images in step
                if "media" in sample_step or "images" in sample_step:
                    logger.info(f"  Step contains media/images")
                
                # Check for tools/parts in step
                if "tools" in sample_step:
                    logger.info(f"  Step contains tools: {sample_step.get('tools')}")
                if "parts" in sample_step:
                    logger.info(f"  Step contains parts: {sample_step.get('parts')}")
            
            # Check for guide-level tools and parts
            if "tools" in guide_detail:
                tools = guide_detail.get("tools", [])
                logger.info(f"\nGuide-level tools: {len(tools)} items")
                if tools:
                    logger.info(f"  Sample tool: {json.dumps(tools[0], indent=2)[:200]}")
            
            if "parts" in guide_detail:
                parts = guide_detail.get("parts", [])
                logger.info(f"Guide-level parts: {len(parts)} items")
                if parts:
                    logger.info(f"  Sample part: {json.dumps(parts[0], indent=2)[:200]}")
            
            # Check for other metadata
            metadata_fields = ["author", "views", "rating", "difficulty", "time_required", "url"]
            logger.info("\nOther metadata fields:")
            for field in metadata_fields:
                if field in guide_detail:
                    logger.info(f"  {field}: {guide_detail.get(field)}")
        
        return guide_detail
    except Exception as e:
        logger.error(f"Error testing guide detail endpoint: {e}", exc_info=True)
        return None


def main():
    """Run all API tests."""
    logger.info("Starting iFixit API Structure Tests")
    logger.info(f"API Base URL: {ENDPOINTS.get('categories', 'N/A')}")
    
    client = iFixitAPIClient()
    
    # Test categories
    categories = test_categories_endpoint(client)
    
    # Test devices (extract from tree like the collector does)
    if categories and isinstance(categories, dict):
        # Try Phone category first as it's likely to have devices
        test_category = "Phone" if "Phone" in categories else list(categories.keys())[0]
        devices = test_devices_from_tree(categories, test_category)
        
        # Test guides (use first device if available)
        if devices and len(devices) > 0:
            device_path = devices[0].get("path") or devices[0].get("namespace") or devices[0].get("title")
            if device_path:
                logger.info(f"\nUsing device path: {device_path}")
                guide_id = test_guides_endpoint(client, device_path)
                
                # Test guide detail
                if guide_id:
                    test_guide_detail_endpoint(client, guide_id)
                else:
                    # Try a known device path
                    logger.info("\nTrying known device path: Phone/iPhone/iPhone 4")
                    guide_id = test_guides_endpoint(client, "Phone/iPhone/iPhone 4")
                    if guide_id:
                        test_guide_detail_endpoint(client, guide_id)
    
    logger.info("\n" + "=" * 80)
    logger.info("API Structure Tests Complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

