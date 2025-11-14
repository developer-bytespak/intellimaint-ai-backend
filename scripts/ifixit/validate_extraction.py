#!/usr/bin/env python3
"""Validate extracted iFixit data quality in the database."""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.db_client import DatabaseClient, DatabaseConnectionError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExtractionValidator:
    """Validate extracted iFixit data quality."""
    
    def __init__(self, db_client: DatabaseClient):
        self.db = db_client
        self.issues: List[Dict[str, Any]] = []
    
    def validate_equipment_families(self) -> Dict[str, Any]:
        """Validate equipment families."""
        logger.info("Validating Equipment Families...")
        stats = {
            "total": 0,
            "with_description": 0,
            "with_metadata": 0,
            "issues": []
        }
        
        with self.db.transaction() as cur:
            cur.execute("SELECT id, name, description, metadata FROM equipment_families")
            rows = cur.fetchall()
            stats["total"] = len(rows)
            
            for row in rows:
                family_id, name, description, metadata = row
                
                if not name or not name.strip():
                    stats["issues"].append({
                        "type": "missing_name",
                        "family_id": str(family_id),
                        "message": "Family missing name"
                    })
                
                if description:
                    stats["with_description"] += 1
                
                if metadata:
                    stats["with_metadata"] += 1
                    try:
                        meta_dict = metadata if isinstance(metadata, dict) else json.loads(metadata)
                        if "ifixit" not in meta_dict:
                            stats["issues"].append({
                                "type": "missing_ifixit_metadata",
                                "family_id": str(family_id),
                                "message": "Family metadata missing 'ifixit' key"
                            })
                    except (json.JSONDecodeError, TypeError):
                        stats["issues"].append({
                            "type": "invalid_metadata",
                            "family_id": str(family_id),
                            "message": "Family metadata is not valid JSON"
                        })
        
        logger.info(f"  Total families: {stats['total']}")
        logger.info(f"  With description: {stats['with_description']}")
        logger.info(f"  With metadata: {stats['with_metadata']}")
        logger.info(f"  Issues found: {len(stats['issues'])}")
        
        return stats
    
    def validate_equipment_models(self) -> Dict[str, Any]:
        """Validate equipment models."""
        logger.info("Validating Equipment Models...")
        stats = {
            "total": 0,
            "with_manufacturer": 0,
            "with_model_name": 0,
            "with_description": 0,
            "with_metadata": 0,
            "orphaned": 0,
            "issues": []
        }
        
        with self.db.transaction() as cur:
            cur.execute("""
                SELECT id, family_id, manufacturer, model_name, model_number, 
                       description, metadata 
                FROM equipment_models
            """)
            rows = cur.fetchall()
            stats["total"] = len(rows)
            
            for row in rows:
                model_id, family_id, manufacturer, model_name, model_number, description, metadata = row
                
                if not model_name or not model_name.strip():
                    stats["issues"].append({
                        "type": "missing_model_name",
                        "model_id": str(model_id),
                        "message": "Model missing model_name"
                    })
                else:
                    stats["with_model_name"] += 1
                
                if manufacturer:
                    stats["with_manufacturer"] += 1
                
                if description:
                    stats["with_description"] += 1
                
                if metadata:
                    stats["with_metadata"] += 1
                    try:
                        meta_dict = metadata if isinstance(metadata, dict) else json.loads(metadata)
                        if "ifixit" not in meta_dict:
                            stats["issues"].append({
                                "type": "missing_ifixit_metadata",
                                "model_id": str(model_id),
                                "message": "Model metadata missing 'ifixit' key"
                            })
                    except (json.JSONDecodeError, TypeError):
                        stats["issues"].append({
                            "type": "invalid_metadata",
                            "model_id": str(model_id),
                            "message": "Model metadata is not valid JSON"
                        })
                
                # Check for orphaned models (family_id doesn't exist)
                cur.execute("SELECT 1 FROM equipment_families WHERE id = %s", (family_id,))
                if not cur.fetchone():
                    stats["orphaned"] += 1
                    stats["issues"].append({
                        "type": "orphaned_model",
                        "model_id": str(model_id),
                        "family_id": str(family_id),
                        "message": "Model references non-existent family"
                    })
        
        logger.info(f"  Total models: {stats['total']}")
        logger.info(f"  With manufacturer: {stats['with_manufacturer']}")
        logger.info(f"  With model_name: {stats['with_model_name']}")
        logger.info(f"  With description: {stats['with_description']}")
        logger.info(f"  With metadata: {stats['with_metadata']}")
        logger.info(f"  Orphaned models: {stats['orphaned']}")
        logger.info(f"  Issues found: {len(stats['issues'])}")
        
        return stats
    
    def validate_knowledge_sources(self) -> Dict[str, Any]:
        """Validate knowledge sources."""
        logger.info("Validating Knowledge Sources...")
        stats = {
            "total": 0,
            "ifixit_sources": 0,
            "with_content": 0,
            "with_metadata": 0,
            "with_model": 0,
            "orphaned": 0,
            "short_content": 0,
            "issues": []
        }
        
        with self.db.transaction() as cur:
            cur.execute("""
                SELECT id, title, source_type, raw_content, model_id, word_count, metadata
                FROM knowledge_sources
            """)
            rows = cur.fetchall()
            stats["total"] = len(rows)
            
            for row in rows:
                source_id, title, source_type, raw_content, model_id, word_count, metadata = row
                
                if source_type == "ifixit":
                    stats["ifixit_sources"] += 1
                
                if not title or not title.strip():
                    stats["issues"].append({
                        "type": "missing_title",
                        "source_id": str(source_id),
                        "message": "Knowledge source missing title"
                    })
                
                if raw_content:
                    stats["with_content"] += 1
                    content_len = len(raw_content.strip())
                    if content_len < 10:
                        stats["short_content"] += 1
                        stats["issues"].append({
                            "type": "short_content",
                            "source_id": str(source_id),
                            "content_length": content_len,
                            "message": f"Content too short ({content_len} chars)"
                        })
                else:
                    stats["issues"].append({
                        "type": "missing_content",
                        "source_id": str(source_id),
                        "message": "Knowledge source missing raw_content"
                    })
                
                if model_id:
                    stats["with_model"] += 1
                    # Check if model exists
                    cur.execute("SELECT 1 FROM equipment_models WHERE id = %s", (model_id,))
                    if not cur.fetchone():
                        stats["orphaned"] += 1
                        stats["issues"].append({
                            "type": "orphaned_source",
                            "source_id": str(source_id),
                            "model_id": str(model_id),
                            "message": "Source references non-existent model"
                        })
                
                if metadata:
                    stats["with_metadata"] += 1
                    try:
                        meta_dict = metadata if isinstance(metadata, dict) else json.loads(metadata)
                        if source_type == "ifixit":
                            if "ifixit" not in meta_dict:
                                stats["issues"].append({
                                    "type": "missing_ifixit_metadata",
                                    "source_id": str(source_id),
                                    "message": "iFixit source missing 'ifixit' metadata key"
                                })
                            else:
                                ifixit_meta = meta_dict.get("ifixit", {})
                                if "guide_id" not in ifixit_meta:
                                    stats["issues"].append({
                                        "type": "missing_guide_id",
                                        "source_id": str(source_id),
                                        "message": "iFixit metadata missing guide_id"
                                    })
                    except (json.JSONDecodeError, TypeError):
                        stats["issues"].append({
                            "type": "invalid_metadata",
                            "source_id": str(source_id),
                            "message": "Metadata is not valid JSON"
                        })
        
        logger.info(f"  Total sources: {stats['total']}")
        logger.info(f"  iFixit sources: {stats['ifixit_sources']}")
        logger.info(f"  With content: {stats['with_content']}")
        logger.info(f"  With metadata: {stats['with_metadata']}")
        logger.info(f"  With model: {stats['with_model']}")
        logger.info(f"  Orphaned sources: {stats['orphaned']}")
        logger.info(f"  Short content (<10 chars): {stats['short_content']}")
        logger.info(f"  Issues found: {len(stats['issues'])}")
        
        return stats
    
    def validate_data_relationships(self) -> Dict[str, Any]:
        """Validate data relationships and integrity."""
        logger.info("Validating Data Relationships...")
        stats = {
            "families_with_models": 0,
            "models_with_sources": 0,
            "issues": []
        }
        
        with self.db.transaction() as cur:
            # Check families with models
            cur.execute("""
                SELECT DISTINCT family_id FROM equipment_models
            """)
            families_with_models = len(cur.fetchall())
            stats["families_with_models"] = families_with_models
            
            # Check models with knowledge sources
            cur.execute("""
                SELECT DISTINCT model_id FROM knowledge_sources 
                WHERE model_id IS NOT NULL
            """)
            models_with_sources = len(cur.fetchall())
            stats["models_with_sources"] = models_with_sources
            
            # Find families without models
            cur.execute("""
                SELECT f.id, f.name 
                FROM equipment_families f
                LEFT JOIN equipment_models m ON m.family_id = f.id
                WHERE m.id IS NULL
            """)
            orphaned_families = cur.fetchall()
            for family_id, name in orphaned_families:
                stats["issues"].append({
                    "type": "family_without_models",
                    "family_id": str(family_id),
                    "name": name,
                    "message": f"Family '{name}' has no models"
                })
        
        logger.info(f"  Families with models: {stats['families_with_models']}")
        logger.info(f"  Models with sources: {stats['models_with_sources']}")
        logger.info(f"  Issues found: {len(stats['issues'])}")
        
        return stats
    
    def run_validation(self) -> Dict[str, Any]:
        """Run all validation checks."""
        logger.info("=" * 80)
        logger.info("Starting iFixit Data Validation")
        logger.info("=" * 80)
        
        results = {
            "families": self.validate_equipment_families(),
            "models": self.validate_equipment_models(),
            "sources": self.validate_knowledge_sources(),
            "relationships": self.validate_data_relationships(),
        }
        
        # Aggregate issues
        all_issues = []
        for section, stats in results.items():
            if "issues" in stats:
                for issue in stats["issues"]:
                    issue["section"] = section
                    all_issues.append(issue)
        
        results["summary"] = {
            "total_issues": len(all_issues),
            "issues_by_type": {},
            "issues_by_section": {}
        }
        
        for issue in all_issues:
            issue_type = issue["type"]
            section = issue["section"]
            
            results["summary"]["issues_by_type"][issue_type] = \
                results["summary"]["issues_by_type"].get(issue_type, 0) + 1
            results["summary"]["issues_by_section"][section] = \
                results["summary"]["issues_by_section"].get(section, 0) + 1
        
        logger.info("\n" + "=" * 80)
        logger.info("Validation Summary")
        logger.info("=" * 80)
        logger.info(f"Total issues found: {results['summary']['total_issues']}")
        logger.info(f"Issues by type: {json.dumps(results['summary']['issues_by_type'], indent=2)}")
        logger.info(f"Issues by section: {json.dumps(results['summary']['issues_by_section'], indent=2)}")
        
        return results


def main():
    """Main entry point."""
    try:
        db_client = DatabaseClient()
    except DatabaseConnectionError as exc:
        logger.error(f"Database connection failed: {exc}")
        logger.error("Ensure DATABASE_URL environment variable is set")
        return 1
    
    validator = ExtractionValidator(db_client)
    results = validator.run_validation()
    
    # Save results to file
    output_file = Path(__file__).parent / "validation_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"\nValidation report saved to: {output_file}")
    
    if results["summary"]["total_issues"] > 0:
        logger.warning(f"\n⚠️  Found {results['summary']['total_issues']} issues - review validation_report.json")
        return 1
    else:
        logger.info("\n✅ No issues found - data quality looks good!")
        return 0


if __name__ == "__main__":
    sys.exit(main())

