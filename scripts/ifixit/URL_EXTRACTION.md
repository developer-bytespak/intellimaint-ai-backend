# iFixit URL Extraction Documentation

This document details all URLs and download links that are extracted and stored from iFixit guides.

## URLs Extracted and Stored

### 1. Guide URLs
- **Guide URL**: Full URL to the guide page on iFixit
  - Location: `metadata.ifixit.url`
  - Example: `https://www.ifixit.com/Guide/PowerBook+G3+Wallstreet+Keyboard+Replacement/1`
  - **Status**: ✅ Extracted and normalized

### 2. Part URLs
- **Part URLs**: URLs to iFixit item/product pages
  - Location: `metadata.ifixit.parts[].url` and `metadata.ifixit.parts[].full_url`
  - Example: `/Item/G3_WallStreet_Keyboard` → `https://www.ifixit.com/Item/G3_WallStreet_Keyboard`
  - **Status**: ✅ Extracted, normalized (relative URLs converted to absolute), and stored

### 3. Document URLs
- **Featured Document URLs**:
  - Location: `metadata.ifixit.featured_document`
  - Fields:
    - `embed_url`: Embed URL for featured document
    - `thumbnail_url`: Thumbnail URL for featured document
    - `document_id`: Document ID
    - `detail_url`: API endpoint URL to fetch document details (`https://www.ifixit.com/api/2.0/documents/{id}`)
  - **Status**: ✅ Extracted and normalized

- **Document URLs Array**:
  - Location: `metadata.ifixit.documents[]`
  - Each document includes:
    - `id`: Document ID or GUID
    - `detail_url`: API endpoint to fetch document details (`https://www.ifixit.com/api/2.0/documents/{id}`)
    - `url`: Document URL (if available)
    - `download_url`: Direct download URL (if available)
    - `title`: Document title (if available)
    - `filename`: Document filename (if available)
    - `raw_data`: Complete document data from API
  - **Status**: ✅ Extracted, normalized, and stored with all available fields

### 4. Image URLs
- **Step-level Images**:
  - Location: `metadata.ifixit.step_images[]`
  - Each image includes:
    - `step_id`: Step number
    - `image_id`: Image ID
    - `guid`: Image GUID
    - `urls`: Object with multiple image sizes:
      - `thumbnail`: Thumbnail URL
      - `medium`: Medium size URL
      - `large`: Large size URL
      - `original`: Original/full size URL
  - **Status**: ✅ All image URLs extracted and normalized

- **Guide Header Image**:
  - Location: `metadata.ifixit.summary_data.image` (in summary)
  - Contains multiple size URLs (mini, thumbnail, medium, large, original)
  - **Status**: ✅ Stored in summary_data

### 5. Author URLs
- **Author Profile URL**:
  - Location: `metadata.ifixit.author.url`
  - Example: `https://www.ifixit.com/User/1/iRobot`
  - **Status**: ✅ Extracted and normalized

- **Author Image URLs**:
  - Location: `metadata.ifixit.author.image`
  - Contains multiple size URLs (mini, thumbnail, medium, original, full)
  - **Status**: ✅ All image URLs normalized

### 6. Prerequisite URLs
- **Prerequisite Guide URLs**:
  - Location: `metadata.ifixit.prerequisites[]`
  - Contains links to prerequisite guides
  - **Status**: ✅ Stored (structure depends on API response)

## URL Normalization

All relative URLs are automatically converted to absolute URLs:
- Relative URLs starting with `/` → `https://www.ifixit.com{url}`
- Absolute URLs (starting with `http://` or `https://`) → Kept as-is
- Example: `/Item/G3_WallStreet_Keyboard` → `https://www.ifixit.com/Item/G3_WallStreet_Keyboard`

## Document Download Links

To get actual download URLs for documents, you can:

1. **Use the document detail URL**: 
   - From `metadata.ifixit.documents[].detail_url` or `metadata.ifixit.featured_document.detail_url`
   - Call: `GET https://www.ifixit.com/api/2.0/documents/{id}`
   - Response includes `download_url` field

2. **Check if already extracted**:
   - Some documents may already have `download_url` in `metadata.ifixit.documents[].download_url`
   - This depends on what the API returns in the guide detail response

## Complete URL Inventory

For each guide, the following URLs are stored:

| URL Type | Location in Metadata | Normalized | Download Link |
|----------|---------------------|------------|---------------|
| Guide page | `ifixit.url` | ✅ | N/A |
| Part/item pages | `ifixit.parts[].url` | ✅ | N/A |
| Featured doc embed | `ifixit.featured_document.embed_url` | ✅ | N/A |
| Featured doc thumbnail | `ifixit.featured_document.thumbnail_url` | ✅ | N/A |
| Featured doc API | `ifixit.featured_document.detail_url` | ✅ | Can fetch download URL |
| Document URLs | `ifixit.documents[].url` | ✅ | May include download_url |
| Document API | `ifixit.documents[].detail_url` | ✅ | Can fetch download URL |
| Step images | `ifixit.step_images[].urls.*` | ✅ | Direct image URLs |
| Author profile | `ifixit.author.url` | ✅ | N/A |
| Author images | `ifixit.author.image.*` | ✅ | Direct image URLs |

## Verification

To verify all URLs are being extracted:

1. Run the collector on a test guide
2. Check the database: `SELECT metadata FROM knowledge_sources WHERE source_type = 'ifixit' LIMIT 1;`
3. Inspect the JSON metadata for all URL fields listed above
4. Use `test_api_structure.py` to see what URLs are available in the API response

## Notes

- **Image URLs**: All image URLs are direct links to images (not download links, but can be used to download)
- **Document URLs**: May require an additional API call to get the actual download URL
- **Part URLs**: Link to product/item pages, not direct downloads
- **All URLs are normalized**: Relative URLs are converted to absolute URLs for consistency

