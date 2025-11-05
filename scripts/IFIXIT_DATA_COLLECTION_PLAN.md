# iFixit Data Collection Plan

## Phase 1: Discovery - Count All Machines in iFixit

### Objective
Create a script to discover and count all devices/machines available in iFixit API to understand the scope of data collection.

### Implementation Steps

1. **Create Discovery Script** (`scripts/discover_ifixit_devices.py`)
   - Use iFixit API to fetch all categories
   - For each category, fetch all devices
   - Count total devices and categorize by type
   - Generate summary report with:
     - Total device count
     - Count by category
     - Sample device list
     - Estimated guide count

2. **iFixit API Endpoints to Use**
   - `GET /api/2.0/wikis` - Get all categories
   - `GET /api/2.0/wikis/{category}/devices` - Get devices in category
   - `GET /api/2.0/guides?device={device_id}` - Get guides for device (for estimation)

3. **Output Format**
   - JSON report: `scripts/ifixit_discovery_report.json`
   - Summary console output with counts and statistics

### Key Files to Create
- `scripts/discover_ifixit_devices.py` - Main discovery script
- `scripts/ifixit_api_client.py` - Reusable iFixit API client wrapper
- `scripts/config/ifixit_config.py` - API configuration (API key, endpoints)

## Phase 2: Data Collection Strategy

### Objective
After discovering the scope, create a comprehensive data collection script to fetch and store all guide data.

### Mapping Strategy
- **iFixit Categories** → `EquipmentFamily` (name, description)
- **iFixit Devices** → `EquipmentModel` (manufacturer, modelName, modelNumber, description, imageUrls)
- **iFixit Guides** → `KnowledgeSource` (title, rawContent, sourceType='ifixit', metadata)

### Implementation Steps

1. **Create Data Collection Script** (`scripts/collect_ifixit_data.py`)
   - Fetch all categories from iFixit
   - For each category:
     - Create/update EquipmentFamily record
     - Fetch devices in category
     - For each device:
       - Create/update EquipmentModel record (linked to family)
       - Fetch guides for device
       - For each guide:
         - Fetch full guide content (steps, images, etc.)
         - Create KnowledgeSource record (linked to model)
         - Store guide metadata (guide_id, url, difficulty, etc.)

2. **Data Processing**
   - Handle rate limiting (respect API limits)
   - Add retry logic for failed requests
   - Progress tracking and resumable collection
   - Error logging for failed devices/guides

3. **Database Integration**
   - Use Prisma client (via Python) or direct PostgreSQL connection
   - Handle duplicates (upsert logic)
   - Maintain referential integrity
   - Batch inserts for performance

### Key Files to Create/Modify
- `scripts/collect_ifixit_data.py` - Main data collection script
- `scripts/ifixit_api_client.py` - Enhanced API client with rate limiting
- `scripts/db_client.py` - Database operations helper
- `scripts/models/ifixit_models.py` - Data models for iFixit responses
- `.env.example` - Add IFIXIT_API_KEY configuration

## Phase 3: Data Structure & Storage

### Database Schema Mapping

**EquipmentFamily**
- `name`: iFixit category title
- `description`: Category description

**EquipmentModel**
- `familyId`: Link to EquipmentFamily
- `manufacturer`: Extracted from device name or metadata
- `modelName`: Device name
- `modelNumber`: Device model number (if available)
- `description`: Device description
- `imageUrls`: Array of device images from iFixit

**KnowledgeSource**
- `title`: Guide title
- `sourceType`: 'ifixit'
- `rawContent`: Full guide content (HTML or markdown)
- `modelId`: Link to EquipmentModel
- `metadata`: JSON with guide_id, url, difficulty, author, views, etc.
- `wordCount`: Calculated from content

## Technical Considerations

1. **Rate Limiting**
   - Implement exponential backoff
   - Respect iFixit API rate limits
   - Add delays between requests

2. **Error Handling**
   - Log failed devices/guides
   - Resume from last successful point
   - Handle API errors gracefully

3. **Performance**
   - Batch database operations
   - Use async/await for concurrent API calls (where allowed)
   - Progress tracking for long-running jobs

4. **Data Quality**
   - Validate data before insertion
   - Handle missing fields gracefully
   - Normalize manufacturer/model names

## Dependencies

- `requests` - HTTP client for API calls
- `python-dotenv` - Environment variable management
- `psycopg2` or `prisma-client-py` - Database connection
- `tqdm` - Progress bars
- `tenacity` - Retry logic

## Next Steps After Discovery

1. Review discovery report to understand scope
2. Adjust collection strategy based on device count
3. Set up scheduled sync (optional) for updates
4. Create embeddings for KnowledgeSource content (separate process)

