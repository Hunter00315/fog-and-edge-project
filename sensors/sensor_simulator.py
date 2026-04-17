"""
Flood Monitoring System - Sensor Simulator
Generates mock IoT sensor data from 5 different sensor types
with configurable frequency and dispatch rates.
"""

import random
import time
import json
from datetime import datetime, timezone


class SensorSimulator:
    """Simulates IoT sensors for flood monitoring."""

    # Configuration for each sensor type: unit, value range, normal max, default frequency
    SENSOR_CONFIGS = {
        'water_level': {
            'unit': 'meters',
            'min': 0.5,
            'max': 15.0,
            'normal_max': 5.0,
            'frequency': 2.0
        },
        'rainfall': {
            'unit': 'mm/hr',
            'min': 0.0,
            'max': 100.0,
            'normal_max': 30.0,
            'frequency': 3.0
        },
        'flow_rate': {
            'unit': 'm3/s',
            'min': 0.1,
            'max': 50.0,
            'normal_max': 20.0,
            'frequency': 2.5
        },
        'soil_moisture': {
            'unit': '%',
            'min': 10.0,
            'max': 100.0,
            'normal_max': 70.0,
            'frequency': 5.0
        },
        'temperature': {
            'unit': 'celsius',
            'min': -5.0,
            'max': 45.0,
            'normal_max': 35.0,
            'frequency': 4.0
        }
    }

    def __init__(self, sensor_type, frequency=None, dispatch_rate=1):
        """
        Initialize sensor simulator.

        Args:
            sensor_type: One of water_level, rainfall, flow_rate, soil_moisture, temperature
            frequency: Seconds between readings (overrides default)
            dispatch_rate: Number of readings to buffer before dispatching
        """
        if sensor_type not in self.SENSOR_CONFIGS:
            raise ValueError(f"Unknown sensor type: {sensor_type}")

        self.sensor_type = sensor_type
        config = self.SENSOR_CONFIGS[sensor_type]
        self.unit = config['unit']
        self.min_val = config['min']
        self.max_val = config['max']
        self.normal_max = config['normal_max']
        self.frequency = frequency if frequency is not None else config['frequency']
        self.dispatch_rate = dispatch_rate
        self.buffer = []
        # Start with a normal value for smooth random walk
        self._previous_value = random.uniform(self.min_val, self.normal_max)

    def generate_reading(self):
        """Generate a single sensor reading with realistic variation using random walk."""
        # Smooth random walk for realistic time-series data
        delta = random.gauss(0, (self.max_val - self.min_val) * 0.05)

        # 5% chance of spike (simulating flood events)
        if random.random() < 0.05:
            delta += random.uniform(0, (self.max_val - self.normal_max) * 0.5)

        new_value = self._previous_value + delta
        new_value = max(self.min_val, min(self.max_val, new_value))
        self._previous_value = new_value

        return {
            'sensor_type': self.sensor_type,
            'value': round(new_value, 2),
            'unit': self.unit,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'sensor_id': f's-{self.sensor_type}'
        }

    def collect_readings(self):
        """
        Generate a reading and return a batch when dispatch_rate is reached.
        Returns a list of readings or None if batch is not yet full.
        """
        reading = self.generate_reading()
        self.buffer.append(reading)

        if len(self.buffer) >= self.dispatch_rate:
            batch = self.buffer.copy()
            self.buffer.clear()
            return batch
        return None
