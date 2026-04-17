"""
Flood Monitoring System - Fog Node
Receives sensor data, performs edge processing (aggregation, risk assessment),
and dispatches processed payloads to the AWS cloud backend via SQS.
"""

import json
import statistics
import boto3
from datetime import datetime, timezone


class FogNode:
    """Fog computing node that processes sensor data before cloud dispatch."""

    # Flood risk thresholds per sensor type
    FLOOD_THRESHOLDS = {
        'water_level': {'warning': 5.0, 'danger': 10.0},
        'rainfall': {'warning': 30.0, 'danger': 60.0},
        'flow_rate': {'warning': 20.0, 'danger': 35.0},
        'soil_moisture': {'warning': 70.0, 'danger': 90.0},
        'temperature': {'warning': 35.0, 'danger': 42.0}
    }

    def __init__(self, node_id, sqs_queue_url, region='eu-north-1'):
        """
        Initialize fog node.

        Args:
            node_id: Unique identifier for this fog node
            sqs_queue_url: AWS SQS queue URL for cloud dispatch
            region: AWS region
        """
        self.node_id = node_id
        self.sqs_queue_url = sqs_queue_url
        self.region = region
        self.sqs = boto3.client('sqs', region_name=region)
        self.data_buffer = {}  # Running window of values per sensor type

    def process_sensor_data(self, readings):
        """
        Process raw sensor readings at the fog layer:
        - Maintains a sliding window of values per sensor type
        - Computes aggregation statistics (mean, min, max)
        - Performs flood risk assessment based on thresholds

        Args:
            readings: List of raw sensor reading dicts

        Returns:
            List of processed reading dicts with added fog-layer metadata
        """
        processed = []
        for reading in readings:
            sensor_type = reading['sensor_type']
            value = reading['value']

            # Maintain sliding window (last 10 readings)
            if sensor_type not in self.data_buffer:
                self.data_buffer[sensor_type] = []
            self.data_buffer[sensor_type].append(value)
            if len(self.data_buffer[sensor_type]) > 10:
                self.data_buffer[sensor_type] = self.data_buffer[sensor_type][-10:]

            values = self.data_buffer[sensor_type]
            avg_value = statistics.mean(values)

            # Flood risk assessment
            thresholds = self.FLOOD_THRESHOLDS.get(
                sensor_type, {'warning': 50, 'danger': 80}
            )
            if value >= thresholds['danger']:
                risk_level = 'DANGER'
            elif value >= thresholds['warning']:
                risk_level = 'WARNING'
            else:
                risk_level = 'NORMAL'

            processed_reading = {
                'sensor_type': sensor_type,
                'sensor_id': reading.get('sensor_id', f's-{sensor_type}'),
                'value': value,
                'unit': reading.get('unit', ''),
                'timestamp': reading['timestamp'],
                'fog_node_id': self.node_id,
                'processed_value': round(avg_value, 2),
                'risk_level': risk_level,
                'readings_count': len(values),
                'min_value': round(min(values), 2),
                'max_value': round(max(values), 2),
                'processed_at': datetime.now(timezone.utc).isoformat()
            }
            processed.append(processed_reading)

        return processed

    def dispatch_to_cloud(self, processed_data):
        """
        Send processed data to AWS SQS queue for cloud backend ingestion.

        Args:
            processed_data: List of processed sensor reading dicts

        Returns:
            Number of messages successfully sent
        """
        sent_count = 0
        for data in processed_data:
            try:
                self.sqs.send_message(
                    QueueUrl=self.sqs_queue_url,
                    MessageBody=json.dumps(data, default=str),
                    MessageAttributes={
                        'sensor_type': {
                            'StringValue': data['sensor_type'],
                            'DataType': 'String'
                        },
                        'risk_level': {
                            'StringValue': data['risk_level'],
                            'DataType': 'String'
                        }
                    }
                )
                sent_count += 1
            except Exception as e:
                print(f"  [ERROR] Failed to send {data['sensor_type']}: {e}")
        return sent_count
