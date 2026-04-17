"""
Flood Monitoring System - Simulation Runner
Orchestrates IoT sensor data generation, fog node processing,
and dispatch to the AWS cloud backend.

Usage: python run_simulation.py
"""

import json
import time
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sensors.sensor_simulator import SensorSimulator
from fog_node.fog_node import FogNode

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


def load_config():
    """Load deployment configuration (SQS queue URL, region)."""
    if not os.path.exists(CONFIG_FILE):
        print("ERROR: config.json not found. Run 'python deploy.py' first.")
        sys.exit(1)
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def main():
    print("=" * 60)
    print("  FLOOD MONITORING - IoT Simulation")
    print("  Sensors -> Fog Node -> AWS Cloud Backend")
    print("=" * 60)

    # Load deployment config
    config = load_config()
    sqs_queue_url = config['sqs_queue_url']
    region = config.get('region', 'eu-north-1')

    print(f"\n  Region:    {region}")
    print(f"  SQS Queue: {sqs_queue_url}")
    print(f"  Dashboard: {config.get('dashboard_url', 'N/A')}")

    # Initialize 5 sensor types with configurable frequency and dispatch rates
    sensor_types = ['water_level', 'rainfall', 'flow_rate', 'soil_moisture', 'temperature']
    sensors = {}
    print("\n  Initializing sensors:")
    for stype in sensor_types:
        sensors[stype] = SensorSimulator(stype, dispatch_rate=1)
        print(f"    [{stype}] frequency={sensors[stype].frequency}s, dispatch_rate={sensors[stype].dispatch_rate}")

    # Initialize fog node
    fog = FogNode(
        node_id='fog-node-1',
        sqs_queue_url=sqs_queue_url,
        region=region
    )
    print(f"\n  Fog node 'fog-node-1' initialized")
    print(f"  Dispatching processed data to cloud...\n")
    print("-" * 60)

    iteration = 0
    total_sent = 0
    try:
        while True:
            iteration += 1
            print(f"\n  --- Iteration {iteration} ---")

            # Collect readings from all sensors
            all_readings = []
            for stype, sensor in sensors.items():
                batch = sensor.collect_readings()
                if batch:
                    for reading in batch:
                        print(f"    [SENSOR] {reading['sensor_type']:15s} = {reading['value']:8.2f} {reading['unit']}")
                        all_readings.append(reading)

            if all_readings:
                # Fog node processes the data (aggregation + risk assessment)
                processed = fog.process_sensor_data(all_readings)

                for p in processed:
                    risk = p['risk_level']
                    indicator = "OK" if risk == 'NORMAL' else ("WARN" if risk == 'WARNING' else "DANGER!")
                    print(f"    [FOG]    {p['sensor_type']:15s}   avg={p['processed_value']:8.2f}  risk={indicator}")

                # Dispatch to AWS cloud backend via SQS
                sent = fog.dispatch_to_cloud(processed)
                total_sent += sent
                print(f"    [CLOUD]  Dispatched {sent} readings to SQS (total: {total_sent})")

            # Wait before next iteration
            time.sleep(3)

    except KeyboardInterrupt:
        print(f"\n\n{'=' * 60}")
        print(f"  Simulation stopped by user.")
        print(f"  Total iterations: {iteration}")
        print(f"  Total readings sent to cloud: {total_sent}")
        print(f"  View dashboard: {config.get('dashboard_url', 'N/A')}")
        print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
