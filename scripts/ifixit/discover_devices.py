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
    
    def _count_devices_in_tree(self, tree: Dict[str, Any], path: str = "") -> int:
        """Recursively count devices in the nested category tree"""
        count = 0
        for key, value in tree.items():
            current_path = f"{path}/{key}" if path else key
            if value is None:
                # This is a device
                count += 1
            elif isinstance(value, dict):
                # This is a category, recurse
                count += self._count_devices_in_tree(value, current_path)
        return count
    
    def _extract_devices_from_tree(self, tree: Dict[str, Any], path: str = "") -> List[Dict[str, Any]]:
        """Recursively extract all devices from the nested category tree"""
        devices = []
        for key, value in tree.items():
            current_path = f"{path}/{key}" if path else key
            if value is None:
                # This is a device
                devices.append({
                    "title": key,
                    "namespace": current_path,
                    "path": current_path
                })
            elif isinstance(value, dict):
                # This is a category, recurse
                devices.extend(self._extract_devices_from_tree(value, current_path))
        return devices
    
    def _extract_categories_from_tree(self, tree: Dict[str, Any], path: str = "") -> List[Dict[str, Any]]:
        """Recursively extract all categories from the nested tree"""
        categories = []
        for key, value in tree.items():
            current_path = f"{path}/{key}" if path else key
            if isinstance(value, dict) and value:
                # This is a category (has children)
                categories.append({
                    "title": key,
                    "namespace": current_path,
                    "path": current_path,
                    "device_count": self._count_devices_in_tree(value, current_path)
                })
                # Recurse into subcategories
                categories.extend(self._extract_categories_from_tree(value, current_path))
        return categories
    
    def discover_all(self) -> Dict[str, Any]:
        """
        Discover all categories, devices, and estimate guide counts
        
        Returns:
            Dictionary with discovery results
        """
        logger.info("Starting iFixit device discovery...")
        
        # Step 1: Fetch all categories (nested tree structure)
        logger.info("Step 1: Fetching all categories...")
        categories_tree = self.client.get_categories()
        logger.info(f"Fetched category tree structure")
        
        # Step 2: Extract all devices from the tree
        logger.info("Step 2: Extracting devices from category tree...")
        all_devices = self._extract_devices_from_tree(categories_tree)
        total_devices = len(all_devices)
        logger.info(f"Found {total_devices} total devices")
        
        # Step 3: Extract categories with device counts
        logger.info("Step 3: Extracting categories...")
        categories_list = self._extract_categories_from_tree(categories_tree)
        logger.info(f"Found {len(categories_list)} categories")
        
        # Step 4: Group devices by top-level category for reporting
        for device in all_devices:
            path_parts = device["path"].split("/")
            if len(path_parts) > 0:
                top_category = path_parts[0]
                if top_category not in self.devices_by_category:
                    self.devices_by_category[top_category] = []
                self.devices_by_category[top_category].append(device)
        
        # Step 5: Estimate guide count for a sample of devices
        logger.info("Step 4: Sampling guide counts (this may take a while)...")
        sample_size = min(20, total_devices)  # Sample up to 20 devices
        sample_devices = all_devices[:sample_size]
        
        for i, device in enumerate(sample_devices, 1):
            device_name = device.get("namespace") or device.get("title", "")
            logger.info(f"  Sampling device {i}/{sample_size}: {device_name}")
            guides = self.client.get_guides(device_name=device_name)
            guide_count = len(guides)
            self.device_guide_counts[device_name] = guide_count
            logger.debug(f"    Found {guide_count} guides")
        
        # Step 6: Calculate statistics
        logger.info("Step 5: Calculating statistics...")
        
        # Calculate average guides per device (from sample)
        avg_guides_per_device = 0
        if self.device_guide_counts:
            avg_guides_per_device = sum(self.device_guide_counts.values()) / len(self.device_guide_counts)
        
        # Estimate total guides
        estimated_total_guides = int(total_devices * avg_guides_per_device) if avg_guides_per_device > 0 else 0
        
        # Build summary
        summary = {
            "discovery_date": datetime.now().isoformat(),
            "total_categories": len(categories_list),
            "total_devices": total_devices,
            "categories_with_devices": len(self.devices_by_category),
            "average_guides_per_device": round(avg_guides_per_device, 2),
            "estimated_total_guides": estimated_total_guides,
            "sample_size": len(sample_devices),
            "categories": []
        }
        
        # Add category details (top-level categories)
        for category, devices in sorted(self.devices_by_category.items(), key=lambda x: len(x[1]), reverse=True):
            category_info = {
                "name": category,
                "device_count": len(devices),
                "estimated_guides": int(len(devices) * avg_guides_per_device) if avg_guides_per_device > 0 else 0,
                "sample_devices": [
                    {
                        "name": d.get("title") or d.get("namespace", ""),
                        "path": d.get("path", ""),
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

