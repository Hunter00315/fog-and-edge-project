"""
AWS Lambda Function - Data Ingester
Triggered by SQS events. Parses sensor data messages and stores them in DynamoDB.
Part of the scalable cloud backend for the Flood Monitoring System.
"""

import json
import boto3
import os
from decimal import Decimal

# Initialize DynamoDB resource (uses Lambda's AWS_REGION automatically)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'FloodSensorData'))


def handler(event, context):
    """
    SQS event handler - processes batches of sensor data messages.
    Each SQS record body contains a JSON-encoded sensor reading from the fog node.
    """
    records_processed = 0
    errors = 0

    for record in event.get('Records', []):
        try:
            # Parse with Decimal for DynamoDB compatibility
            body = json.loads(record['body'], parse_float=Decimal)

            # Validate required keys
            if 'sensor_type' not in body or 'timestamp' not in body:
                print(f"Skipping record with missing keys: {list(body.keys())}")
                continue

            # Store in DynamoDB
            table.put_item(Item=body)
            records_processed += 1

        except Exception as e:
            errors += 1
            print(f"Error processing record: {e}")
            print(f"Record body: {record.get('body', 'N/A')[:200]}")

    print(f"Processed: {records_processed}, Errors: {errors}")
    return {
        'statusCode': 200,
        'body': json.dumps({
            'records_processed': records_processed,
            'errors': errors
        })
    }
