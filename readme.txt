Flood Monitoring IoT System - README
======================================

A scalable IoT flood monitoring system using fog/edge computing
with an AWS cloud backend.

Architecture
------------
  Sensors (5 types) -> Fog Node (processing) -> SQS -> Lambda -> DynamoDB
                                                                    |
                                        S3 Dashboard <- API Gateway <-

AWS Services Used:
  - Amazon SQS: Message queue for decoupled data ingestion
  - AWS Lambda: Serverless functions (FaaS) for auto-scaling processing
  - Amazon DynamoDB: NoSQL database with on-demand (auto-scaling) capacity
  - Amazon API Gateway: Managed REST API for dashboard
  - Amazon S3: Static website hosting for the dashboard

Region: eu-north-1 (Stockholm)

Sensor Types:
  1. Water Level (meters)
  2. Rainfall (mm/hr)
  3. Flow Rate (m3/s)
  4. Soil Moisture (%)
  5. Temperature (celsius)

Prerequisites
-------------
  - Python 3.8 or higher
  - AWS CLI configured with credentials (run: aws configure)
  - IAM user with AdministratorAccess permissions

Installation & Deployment
--------------------------
1. Install Python dependencies:
     pip install boto3

2. Deploy the AWS backend infrastructure:
     python deploy.py

   This creates: SQS queue, DynamoDB table, Lambda functions,
   API Gateway, and S3-hosted dashboard.
   Configuration is saved to config.json.

3. Run the IoT simulation (sensors + fog node):
     python run_simulation.py

   This starts generating sensor data, processing it at the
   fog layer, and dispatching to the cloud backend via SQS.

4. Open the dashboard URL (printed by deploy.py) in a web browser
   to view real-time sensor data and flood risk indicators.

Project Structure
-----------------
  sensors/
    sensor_simulator.py    - IoT sensor data generation (5 types)
  fog_node/
    fog_node.py            - Fog layer processing and cloud dispatch
  aws_backend/
    lambda_ingester.py     - Lambda: SQS -> DynamoDB ingestion
    lambda_dashboard.py    - Lambda: API Gateway dashboard endpoints
  dashboard/
    index.html             - Real-time web dashboard (Chart.js)
  deploy.py                - AWS infrastructure deployment script
  run_simulation.py        - Main simulation runner
  config.json              - Generated deployment configuration
  FloodMonitoringSimulation.java - iFogSim simulation model
  result.txt               - iFogSim simulation results

Stopping
--------
  Press Ctrl+C to stop the simulation.

Cleanup
-------
  To remove AWS resources, delete via the AWS Console or CLI:
  - SQS queue: flood-monitoring-queue
  - DynamoDB table: FloodSensorData
  - Lambda functions: flood-data-ingester, flood-dashboard-api
  - API Gateway: flood-monitoring-api
  - S3 bucket: flood-monitoring-dash-*
  - IAM role: flood-monitoring-lambda-role
