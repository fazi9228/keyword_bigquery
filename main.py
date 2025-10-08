"""
AWS Lambda Function for automated Google Trends data extraction
Triggered weekly by EventBridge (CloudWatch Events)
"""

import os
import json
from datetime import datetime, timedelta
import pandas as pd
from pytrends.request import TrendReq
from google.cloud import bigquery
from google.oauth2 import service_account
import time

# Configuration
MARKETS_CONFIG = {
    'HK': {'geo_code': 'HK', 'keywords': ['pepperstone', 'exness', 'ic markets', 'xm', 'tmgm', 'fbs', 'hfm', 'fx pro', 'vantage', 'qrs']},
    'SG': {'geo_code': 'SG', 'keywords': ['pepperstone', 'exness', 'ic markets', 'xm', 'tmgm', 'fbs', 'hfm', 'fx pro', 'vantage', 'qrs']},
    'CN': {'geo_code': 'CN', 'keywords': ['exness', 'ic markets', 'tmgm', 'xm', 'pepperstone', 'fbs', 'hfm', 'fx pro', 'qrs', 'vantage']},
    'MY': {'geo_code': 'MY', 'keywords': ['hfm', 'xm', 'exness', 'fbs', 'ic markets', 'pepperstone', 'fx pro', 'tmgm', 'vantage', 'qrs']},
    'TH': {'geo_code': 'TH', 'keywords': ['exness', 'xm', 'fbs', 'ic markets', 'hfm', 'pepperstone', 'fx pro', 'tmgm', 'vantage', 'qrs']},
    'TW': {'geo_code': 'TW', 'keywords': ['pepperstone', 'exness', 'ic markets', 'xm', 'tmgm', 'fbs', 'hfm', 'fx pro', 'vantage', 'qrs']},
    'MN': {'geo_code': 'MN', 'keywords': ['xm', 'pepperstone', 'exness', 'ic markets', 'fx pro', 'fbs', 'hfm', 'vantage', 'qrs', 'tmgm']},
    'VN': {'geo_code': 'VN', 'keywords': ['exness', 'xm', 'ic markets', 'fbs', 'hfm', 'pepperstone', 'fx pro', 'tmgm', 'vantage', 'qrs']},
    'PH': {'geo_code': 'PH', 'keywords': ['fbs', 'xm', 'exness', 'ic markets', 'hfm', 'pepperstone', 'qrs', 'fx pro', 'vantage', 'tmgm']},
    'ID': {'geo_code': 'ID', 'keywords': ['exness', 'hfm', 'fbs', 'xm', 'ic markets', 'fx pro', 'pepperstone', 'tmgm', 'qrs', 'vantage']},
    'IN': {'geo_code': 'IN', 'keywords': ['exness', 'xm', 'fbs', 'ic markets', 'qrs', 'hfm', 'pepperstone', 'fx pro', 'vantage', 'tmgm']},
    'MO': {'geo_code': 'MO', 'keywords': ['pepperstone', 'exness', 'ic markets', 'xm', 'qrs', 'vantage', 'fx pro', 'fbs', 'hfm', 'tmgm']}
}

PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'keyword-planner-etl')
DATASET_ID = os.getenv('BIGQUERY_DATASET', 'keyword_data')
TABLE_ID = 'trends_data'

def get_bigquery_client():
    """Initialize BigQuery client with service account from environment variable"""
    credentials_json = os.getenv('GCP_SERVICE_ACCOUNT_JSON')
    
    if not credentials_json:
        raise ValueError("GCP_SERVICE_ACCOUNT_JSON environment variable not set")
    
    # Parse JSON credentials
    credentials_info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_info)
    
    return bigquery.Client(credentials=credentials, project=PROJECT_ID)

def get_trends_data(pytrends, keywords, geo_code, timeframe='now 7-d'):
    """Fetch Google Trends data for keywords in a specific market"""
    try:
        pytrends.build_payload(
            kw_list=keywords,
            cat=0,
            timeframe=timeframe,
            geo=geo_code,
            gprop=''
        )
        
        interest_over_time = pytrends.interest_over_time()
        
        if interest_over_time.empty:
            return pd.DataFrame()
        
        if 'isPartial' in interest_over_time.columns:
            interest_over_time = interest_over_time.drop('isPartial', axis=1)
        
        df_long = interest_over_time.reset_index().melt(
            id_vars=['date'],
            var_name='keyword',
            value_name='interest_score'
        )
        
        return df_long
        
    except Exception as e:
        print(f"Error fetching trends for {geo_code}: {e}")
        return pd.DataFrame()

def get_latest_date_in_bigquery(bq_client):
    """Check the latest date already in BigQuery to avoid duplicates"""
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
    
    try:
        query = f"SELECT MAX(DATE(date)) as max_date FROM `{table_ref}`"
        result = bq_client.query(query).result()
        max_date = list(result)[0].max_date
        
        if max_date:
            print(f"Latest date in BigQuery: {max_date}")
            return max_date
        else:
            print("No existing data in BigQuery")
            return None
    except Exception as e:
        print(f"Could not check existing data: {e}")
        return None

def lambda_handler(event, context):
    """
    AWS Lambda handler function
    Triggered by EventBridge (CloudWatch Events) via HTTP
    
    Args:
        event: Lambda event object
        context: Lambda context object
    
    Returns:
        dict: Response with statusCode and body
    """
    print(f"Starting Google Trends ETL - {datetime.now()}")
    print(f"Event: {json.dumps(event)}")
    
    try:
        # Initialize clients
        pytrends = TrendReq(hl='en-US', tz=480)
        bq_client = get_bigquery_client()
        
        all_trends_data = []
        
        # Extract data from all markets
        for market, config in MARKETS_CONFIG.items():
            print(f"Processing {market}...")
            
            keywords = config['keywords']
            geo_code = config['geo_code']
            
            # Split into batches of 5 keywords
            for i in range(0, len(keywords), 5):
                batch = keywords[i:i+5]
                
                df = get_trends_data(pytrends, batch, geo_code, timeframe='now 7-d')
                
                if not df.empty:
                    df['market'] = market
                    df['geo_code'] = geo_code
                    df['extracted_at'] = datetime.utcnow()
                    all_trends_data.append(df)
                    print(f"  Retrieved {len(df)} data points for {', '.join(batch)}")
                
                # Rate limiting
                time.sleep(2)
        
        if not all_trends_data:
            print("No data extracted")
            return {
                'statusCode': 200,
                'body': json.dumps('No data extracted')
            }
        
        # Combine all data
        combined_trends = pd.concat(all_trends_data, ignore_index=True)
        
        # Filter out incomplete current week (last 3 days)
        combined_trends['date'] = pd.to_datetime(combined_trends['date'])
        cutoff_date = datetime.now() - timedelta(days=3)
        combined_trends = combined_trends[combined_trends['date'] < cutoff_date]
        
        if combined_trends.empty:
            print("No complete week data available")
            return {
                'statusCode': 200,
                'body': json.dumps('No complete week data available')
            }
        
        # Check for existing data and filter duplicates
        latest_date = get_latest_date_in_bigquery(bq_client)
        
        if latest_date:
            df_new = combined_trends[combined_trends['date'].dt.date > latest_date]
            
            if df_new.empty:
                print("No new data to load (all dates already exist)")
                return {
                    'statusCode': 200,
                    'body': json.dumps('No new data - all dates already exist in BigQuery')
                }
            
            print(f"Filtered {len(combined_trends)} rows to {len(df_new)} new rows")
            combined_trends = df_new
        
        # Load to BigQuery
        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
        
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
            autodetect=True
        )
        
        print(f"Loading {len(combined_trends)} rows to BigQuery...")
        job = bq_client.load_table_from_dataframe(combined_trends, table_ref, job_config=job_config)
        job.result()
        
        print(f"Successfully loaded {len(combined_trends)} rows")
        
        return {
            'statusCode': 200,
            'body': json.dumps(f'ETL completed: {len(combined_trends)} rows loaded')
        }
        
    except Exception as e:
        print(f"Error in Lambda execution: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }


# For local testing
if __name__ == "__main__":
    # Load environment from .env file for local testing
    from dotenv import load_dotenv
    load_dotenv()
    
    # Mock Lambda event and context
    test_event = {}
    test_context = {}
    
    result = lambda_handler(test_event, test_context)
    print(result)
