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

⚠️ **IMPORTANT**: The `GCP_SERVICE_ACCOUNT_JSON` value will be provided separately via secure channel.

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
- `rate(5 minutes)` - runs every 5 minutes

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

## Troubleshooting

**Timeout errors:**
- Increase Lambda timeout (max 15 minutes)

**Memory errors:**
- Increase Lambda memory allocation

**BigQuery authentication errors:**
- Verify `GCP_SERVICE_ACCOUNT_JSON` environment variable is set correctly
- Ensure service account has BigQuery permissions

**No new data loaded:**
- Normal if data already exists in BigQuery
- Check CloudWatch logs for "No new data to load" message

## Security Notes

- Service account JSON is stored as environment variable (consider migrating to AWS Secrets Manager for production)
- Never commit `service-account-key.json` to Git
- Rotate service account keys regularly
