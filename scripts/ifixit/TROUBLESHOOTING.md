# iFixit Collector Troubleshooting Guide

## Common Issues and Solutions

### 1. Database Connection Errors

**Error**: `DatabaseConnectionError: DATABASE_URL is not set`

**Solution**:
- Ensure `DATABASE_URL` environment variable is set in your `.env` file or environment
- Format: `postgresql://user:password@host:port/database`
- Verify database is accessible and credentials are correct

**Error**: `psycopg2.OperationalError: could not connect to server`

**Solution**:
- Check database server is running
- Verify network connectivity
- Check firewall rules
- Ensure database host and port are correct

### 2. API Connection Issues

**Error**: `404 Client Error: Not Found`

**Solution**:
- Verify iFixit API endpoints are correct (should be `/api/2.0/...`)
- Check if the device/category path exists in iFixit
- Some endpoints may not be available for all categories

**Error**: `429 Too Many Requests`

**Solution**:
- Reduce `--concurrency` value (default is 4)
- Increase rate limiting delay in `scripts/ifixit/config.py`
- Consider using `IFIXIT_API_KEY` for higher rate limits
- Add delays between requests

**Error**: `Connection timeout` or `Request timeout`

**Solution**:
- Check internet connectivity
- Increase `IFIXIT_REQUEST_TIMEOUT` in config
- Verify iFixit API is accessible from your network

### 3. Content Extraction Issues

**Warning**: `Guide {id} has very short content`

**Solution**:
- This is a warning, not an error - guide will still be processed
- Some guides may have minimal content
- Check the guide on iFixit website to verify

**Error**: `Guide summary missing guideid`

**Solution**:
- This indicates an API response structure issue
- Check if iFixit API structure has changed
- Verify API endpoint is returning expected format
- Run `test_api_structure.py` to inspect API responses

**Error**: `Content validation failed for guide {id}`

**Solution**:
- Guide content is empty or too short (< 10 characters)
- Guide will be skipped automatically
- Check if guide has actual content on iFixit website

### 4. UUID Generation Issues

**Issue**: UUIDs don't match expected format

**Solution**:
- UUIDs are now generated with format: `ifixit/family/{path}`, `ifixit/model/{path}`, `ifixit/guide/{id}`
- If you have existing data with old UUID format, you may need to migrate
- Old format was: `family:{path}`, `model:{path}`, `guide:{id}`
- UUIDs are deterministic, so same input always produces same UUID

### 5. Progress Tracking Issues

**Issue**: Resume doesn't work correctly

**Solution**:
- Check `scripts/ifixit/state/ingest_state.csv` exists and is readable
- Verify CSV format is correct (should have headers)
- Delete state file if corrupted: `rm scripts/ifixit/state/ingest_state.csv`
- Start fresh or manually edit CSV if needed

**Issue**: Checkpoints not being created

**Solution**:
- Check `--checkpoint-interval` value (default is 50)
- Verify `scripts/ifixit/checkpoints/` directory is writable
- Set `--checkpoint-interval 0` to disable if not needed

### 6. Device Processing Errors

**Error**: `DeviceProcessingError: Failed to fetch guides`

**Solution**:
- Device path may be incorrect
- API may not have guides for this device
- Check device path format matches iFixit structure
- Verify device exists: `python -m scripts.ifixit.discover_devices`

**Error**: `Database error saving device`

**Solution**:
- Check database schema matches expected structure
- Verify all required fields are present
- Check database connection is stable
- Review database logs for specific SQL errors

### 7. Guide Processing Errors

**Error**: `GuideProcessingError: API error fetching guide detail`

**Solution**:
- Guide ID may be invalid or guide may have been removed
- Check if guide exists on iFixit website
- API may be temporarily unavailable - retry later
- Verify guide ID is numeric

**Error**: `GuideProcessingError: Database error saving guide`

**Solution**:
- Check `knowledge_sources` table schema
- Verify `metadata` field accepts JSON
- Check for data type mismatches
- Review database constraints and foreign keys

### 8. Performance Issues

**Issue**: Collection is very slow

**Solution**:
- Reduce `--concurrency` if hitting rate limits
- Increase rate limiting delay
- Use `--max-devices-per-category` and `--max-guides-per-device` for testing
- Consider running during off-peak hours
- Check network latency to iFixit API

**Issue**: High memory usage

**Solution**:
- Reduce `--concurrency` to process fewer devices simultaneously
- Process categories separately using `--category` flag
- Check for memory leaks in long-running processes

### 9. Data Quality Issues

**Issue**: Missing guide content

**Solution**:
- Some guides may have minimal content (warnings will be logged)
- Check guide on iFixit website to verify
- Run with `--log-level DEBUG` to see detailed extraction logs
- Verify API response structure using `test_api_structure.py`

**Issue**: Incorrect metadata

**Solution**:
- Metadata structure matches iFixit API response
- Check `api_response_sample.json` for actual API structure
- Verify API hasn't changed structure
- Review metadata in database to see what was captured

### 10. Testing and Validation

**Before running full collection**:
1. Test API connectivity: `python -m scripts.ifixit.test_api_structure`
2. Run discovery: `python -m scripts.ifixit.discover_devices`
3. Test with dry-run: `python -m scripts.ifixit.collect_ifixit_data --dry-run --max-devices-per-category 1`
4. Verify database connection and schema
5. Check extracted data quality

**Validation checklist**:
- [ ] API endpoints are accessible
- [ ] Database connection works
- [ ] Sample extraction completes successfully
- [ ] Content is properly formatted
- [ ] Metadata is captured correctly
- [ ] UUIDs are generated correctly
- [ ] Progress tracking works
- [ ] Error handling provides useful messages

## Getting Help

1. **Check logs**: Review log output with appropriate log level (`--log-level DEBUG`)
2. **Review checkpoints**: Check `scripts/ifixit/checkpoints/` for state snapshots
3. **Check failed devices**: Review `scripts/ifixit/state/failed_devices.json`
4. **Test API structure**: Run `python -m scripts.ifixit.test_api_structure` to inspect API responses
5. **Verify configuration**: Check `scripts/ifixit/config.py` for rate limits and timeouts
6. **Review documentation**: See `OPERATIONS.md` and `storage_mapping.md`

## Debug Mode

Run with maximum verbosity:
```bash
python -m scripts.ifixit.collect_ifixit_data \
  --dry-run \
  --log-level DEBUG \
  --log-format text \
  --max-devices-per-category 1 \
  --max-guides-per-device 1 \
  --category Phone
```

This will show detailed information about:
- API requests and responses
- Content extraction process
- Validation checks
- Database operations (in dry-run mode, shows what would be written)

