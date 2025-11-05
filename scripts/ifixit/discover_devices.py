#!/usr/bin/env python3
"""Discover and count all devices/machines in iFixit API

This script fetches all categories and devices from iFixit API to understand
the scope of data collection. It generates a summary report with device counts
by category and estimated guide counts.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict

from .api_client import iFixitAPIClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class iFixitDeviceDiscoverer:
    """Discover all devices in iFixit API"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize discoverer
        
        Args:
            output_dir: Directory to save discovery report (default: scripts/ifixit/)
        """
        self.client = iFixitAPIClient()
        
        if output_dir is None:
            output_dir = Path(__file__).parent
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.wikis: List[Dict[str, Any]] = []
        self.devices_by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.device_guide_counts: Dict[str, int] = {}
    
    def discover_all(self) -> Dict[str, Any]:
        """
        Discover all categories, devices, and estimate guide counts
        
        Returns:
            Dictionary with discovery results
        """
        logger.info("Starting iFixit device discovery...")
        
        # Step 1: Fetch all categories (wikis)
        logger.info("Step 1: Fetching all categories...")
        self.wikis = self.client.get_wikis()
        logger.info(f"Found {len(self.wikis)} categories")
        
        # Step 2: For each category, fetch devices
        logger.info("Step 2: Fetching devices for each category...")
        total_devices = 0
        
        for i, wiki in enumerate(self.wikis, 1):
            category = wiki.get("namespace") or wiki.get("title", "")
            logger.info(f"Processing category {i}/{len(self.wikis)}: {category}")
            
            devices = self.client.get_devices(category)
            if devices:
                self.devices_by_category[category] = devices
                total_devices += len(devices)
                logger.info(f"  Found {len(devices)} devices")
            
            # Estimate guide count for first few devices (sample)
            if i <= 5:  # Sample first 5 categories
                for device in devices[:3]:  # Sample first 3 devices per category
                    device_name = device.get("namespace") or device.get("title", "")
                    guides = self.client.get_guides(device_name=device_name)
                    guide_count = len(guides)
                    self.device_guide_counts[device_name] = guide_count
                    logger.debug(f"    Device '{device_name}': {guide_count} guides")
        
        # Step 3: Calculate statistics
        logger.info("Step 3: Calculating statistics...")
        
        # Calculate average guides per device (from sample)
        avg_guides_per_device = 0
        if self.device_guide_counts:
            avg_guides_per_device = sum(self.device_guide_counts.values()) / len(self.device_guide_counts)
        
        # Estimate total guides
        estimated_total_guides = int(total_devices * avg_guides_per_device) if avg_guides_per_device > 0 else 0
        
        # Build summary
        summary = {
            "discovery_date": datetime.now().isoformat(),
            "total_categories": len(self.wikis),
            "total_devices": total_devices,
            "categories_with_devices": len(self.devices_by_category),
            "average_guides_per_device": round(avg_guides_per_device, 2),
            "estimated_total_guides": estimated_total_guides,
            "categories": []
        }
        
        # Add category details
        for category, devices in self.devices_by_category.items():
            category_info = {
                "name": category,
                "device_count": len(devices),
                "estimated_guides": int(len(devices) * avg_guides_per_device) if avg_guides_per_device > 0 else 0,
                "sample_devices": [
                    {
                        "name": d.get("title") or d.get("namespace", ""),
                        "description": d.get("description", ""),
                        "url": d.get("url", "")
                    }
                    for d in devices[:5]  # First 5 devices as samples
                ]
            }
            summary["categories"].append(category_info)
        
        # Add sample device guide counts
        summary["sample_device_guide_counts"] = self.device_guide_counts
        
        logger.info(f"Discovery complete!")
        logger.info(f"  Total categories: {summary['total_categories']}")
        logger.info(f"  Total devices: {summary['total_devices']}")
        logger.info(f"  Estimated total guides: {summary['estimated_total_guides']}")
        
        return summary
    
    def save_report(self, summary: Dict[str, Any], filename: str = "ifixit_discovery_report.json"):
        """
        Save discovery report to JSON file
        
        Args:
            summary: Summary dictionary
            filename: Output filename
        """
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Discovery report saved to: {output_path}")
    
    def print_summary(self, summary: Dict[str, Any]):
        """
        Print formatted summary to console
        
        Args:
            summary: Summary dictionary
        """
        print("\n" + "="*80)
        print("iFixit Device Discovery Summary")
        print("="*80)
        print(f"Discovery Date: {summary['discovery_date']}")
        print(f"Total Categories: {summary['total_categories']}")
        print(f"Total Devices: {summary['total_devices']}")
        print(f"Categories with Devices: {summary['categories_with_devices']}")
        print(f"Average Guides per Device: {summary['average_guides_per_device']}")
        print(f"Estimated Total Guides: {summary['estimated_total_guides']}")
        print("\n" + "-"*80)
        print("Top Categories by Device Count:")
        print("-"*80)
        
        # Sort categories by device count
        sorted_categories = sorted(
            summary["categories"],
            key=lambda x: x["device_count"],
            reverse=True
        )
        
        for cat in sorted_categories[:10]:  # Top 10
            print(f"  {cat['name']}: {cat['device_count']} devices (~{cat['estimated_guides']} guides)")
        
        print("\n" + "="*80)


def main():
    """Main entry point"""
    discoverer = iFixitDeviceDiscoverer()
    
    try:
        summary = discoverer.discover_all()
        discoverer.save_report(summary)
        discoverer.print_summary(summary)
    except KeyboardInterrupt:
        logger.warning("Discovery interrupted by user")
    except Exception as e:
        logger.error(f"Error during discovery: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

