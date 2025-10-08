# Google Trends ETL - AWS Lambda Deployment

Automated weekly extraction of Google Trends data for competitor keywords across APAC markets, storing results in Google BigQuery.

## Prerequisites

- AWS Account with Lambda access
- GCP Service Account JSON (provided separately for security)

## Deployment Steps

### 1. Create Lambda Layer (for dependencies)

```bash
# Install dependencies
mkdir python
pip install -r requirements.txt -t python/

# Create layer package
zip -r lambda-layer.zip python/

# Upload to AWS Lambda Layers
# Go to AWS Console → Lambda → Layers → Create Layer
# Upload lambda-layer.zip
# Compatible runtime: Python 3.11
```

**Note**: If you encounter issues with the layer size, consider using a Docker container deployment instead (see Alternative Deployment below).

### 2. Create Lambda Function

**Console:**
- Function name: `google-trends-etl`
- Runtime: Python 3.11
- Architecture: x86_64
- Handler: `main.lambda_handler`

**Upload Code:**
```bash
zip lambda-function.zip main.py
# Upload via Console → Code → Upload from .zip
```

### 3. Configure Lambda Settings

**General Configuration:**
- Timeout: **900 seconds (15 minutes)**
- Memory: **512 MB**

**Environment Variables:**

⚠️ **IMPORTANT**: The `GCP_SERVICE_ACCOUNT_JSON` value is provided separately via secure channel (not in this Git repo for security reasons).

When you receive the service account JSON:
1. Convert it to a single-line string (remove all line breaks)
2. Paste the entire JSON string into the Lambda environment variable
3. Format should be: `{"type":"service_account","project_id":"...","private_key":"...",...}`

```
GCP_PROJECT_ID=keyword-planner-etl
BIGQUERY_DATASET=keyword_data
GCP_SERVICE_ACCOUNT_JSON=<paste service account JSON here as single-line string>
```

**Attach Lambda Layer:**
- Layers → Add a layer → Custom layers
- Select the layer created in Step 1

### 4. Set Up EventBridge Trigger

**Create Rule:**
- AWS Console → EventBridge → Rules → Create rule
- Name: `weekly-trends-sync`
- Rule type: Schedule
- Schedule pattern: `cron(0 2 ? * MON *)` (Every Monday at 2 AM UTC)
- Target: Lambda function `google-trends-etl`

**For testing, use:**
- `rate(10 minutes)` - runs every 10 minutes (minimum recommended due to rate limits)
- **Important**: Disable the test rule after confirming it works to avoid hitting API rate limits

### 5. Test the Function

1. Go to Lambda Console → Test tab
2. Create new test event with empty JSON: `{}`
3. Click "Test"
4. Check CloudWatch Logs for output

## What It Does

- Extracts search interest data for 10 competitor keywords across 12 APAC markets
- Fetches data from last 7 days (incremental updates)
- Filters out incomplete weeks (last 3 days)
- Deduplicates against existing BigQuery data
- Loads new data to BigQuery table: `keyword-planner-etl.keyword_data.trends_data`

## Markets Covered

HK, SG, CN, MY, TH, TW, MN, VN, PH, ID, IN, MO

## Keywords Tracked

pepperstone, exness, ic markets, xm, tmgm, fbs, hfm, fx pro, vantage, qrs

## Monitoring

Check CloudWatch Logs:
- AWS Console → CloudWatch → Log groups → `/aws/lambda/google-trends-etl`

## Important Notes

⚠️ **Rate Limiting**: The pytrends library has strict rate limits. **Do NOT run the function multiple times in quick succession** or you'll get temporarily blocked by Google (429 errors). The scheduled weekly run is sufficient.

⚠️ **Testing**: When testing, wait at least 10 minutes between test runs to avoid rate limit issues.

⚠️ **Service Account Key**: The GCP service account JSON key is provided separately via secure channel (not in Git for security). You'll need to paste it into the Lambda environment variable `GCP_SERVICE_ACCOUNT_JSON`.

## Troubleshooting

**Rate limit errors (429 Too Many Requests):**
- Wait 10-30 minutes before retrying
- Don't run the function manually if the scheduled run already executed
- Consider increasing the `time.sleep(2)` delay in the code if issues persist

**Timeout errors:**
- Increase Lambda timeout (max 15 minutes)

**Memory errors:**
- Increase Lambda memory allocation

**BigQuery authentication errors:**
- Verify `GCP_SERVICE_ACCOUNT_JSON` environment variable is set correctly (should be a single-line JSON string)
- Ensure service account has BigQuery Data Editor permissions

**No new data loaded:**
- Normal if data already exists in BigQuery
- Check CloudWatch logs for "No new data to load" message

## Security Notes

- **Service account JSON is NOT in this Git repo** - it will be provided separately via secure channel (encrypted email or password manager)
- Service account key is stored as Lambda environment variable (consider migrating to AWS Secrets Manager for production)
- Never commit `service-account-key.json` to Git
- Rotate service account keys regularly (every 90 days recommended)

## Alternative Deployment (Docker Container)

If the Lambda Layer approach has issues (file size, dependency conflicts), you can deploy using a Docker container:

```dockerfile
FROM public.ecr.aws/lambda/python:3.11
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ${LAMBDA_TASK_ROOT}
CMD ["main.lambda_handler"]
```

Then build and push to ECR, and create Lambda function from the container image.
