"""
AWS Lambda Function - Dashboard API
Provides REST API endpoints for the Flood Monitoring dashboard.
Queries DynamoDB and returns sensor data as JSON with CORS headers.
Invoked via API Gateway HTTP API.
"""

import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB (uses Lambda's AWS_REGION automatically)
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'FloodSensorData'))

SENSOR_TYPES = ['water_level', 'rainfall', 'flow_rate', 'soil_moisture', 'temperature']


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle DynamoDB Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def build_response(status_code, body):
    """Build HTTP response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }


def get_latest_readings():
    """Query the most recent reading for each sensor type."""
    results = {}
    for sensor_type in SENSOR_TYPES:
        try:
            resp = table.query(
                KeyConditionExpression=Key('sensor_type').eq(sensor_type),
                ScanIndexForward=False,
                Limit=1
            )
            results[sensor_type] = resp['Items'][0] if resp['Items'] else None
        except Exception as e:
            print(f"Error querying {sensor_type}: {e}")
            results[sensor_type] = None
    return results


def get_sensor_history(sensor_type, limit=50):
    """Query historical readings for a specific sensor type."""
    try:
        resp = table.query(
            KeyConditionExpression=Key('sensor_type').eq(sensor_type),
            ScanIndexForward=False,
            Limit=int(limit)
        )
        # Reverse to chronological order
        return list(reversed(resp['Items']))
    except Exception as e:
        print(f"Error querying history for {sensor_type}: {e}")
        return []


def handler(event, context):
    """
    API Gateway HTTP API event handler.
    Routes:
        GET /api/latest      - Latest reading for each sensor type
        GET /api/history     - Historical data for a sensor (query: sensor_type, limit)
        GET /api/all-history - Historical data for all sensors (query: limit)
    """
    path = event.get('rawPath', event.get('path', '/'))
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    params = event.get('queryStringParameters') or {}

    # Handle CORS preflight
    if method == 'OPTIONS':
        return build_response(200, {})

    try:
        if path == '/api/latest':
            data = get_latest_readings()
            return build_response(200, data)

        elif path == '/api/history':
            sensor_type = params.get('sensor_type', 'water_level')
            limit = params.get('limit', '50')
            data = get_sensor_history(sensor_type, limit)
            return build_response(200, {
                'sensor_type': sensor_type,
                'readings': data
            })

        elif path == '/api/all-history':
            limit = int(params.get('limit', '30'))
            all_data = {}
            for sensor_type in SENSOR_TYPES:
                all_data[sensor_type] = get_sensor_history(sensor_type, limit)
            return build_response(200, all_data)

        else:
            return build_response(404, {'error': 'Not found', 'path': path})

    except Exception as e:
        print(f"Error handling request: {e}")
        return build_response(500, {'error': str(e)})
