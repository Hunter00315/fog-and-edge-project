"""
Flood Monitoring System - AWS Backend Deployment Script
Deploys all cloud infrastructure: SQS, DynamoDB, Lambda, API Gateway, and S3 dashboard.
Region: eu-north-1 (Stockholm)
"""

import boto3
import json
import time
import zipfile
import io
import os
import sys

REGION = 'eu-north-1'
PROJECT_PREFIX = 'flood-monitoring'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_account_id():
    """Get AWS account ID from STS."""
    sts = boto3.client('sts', region_name=REGION)
    return sts.get_caller_identity()['Account']


def create_sqs_queue(sqs_client):
    """Create SQS queue for sensor data ingestion."""
    print("\n[1/7] Creating SQS Queue...")
    queue_name = f'{PROJECT_PREFIX}-queue'

    try:
        response = sqs_client.create_queue(
            QueueName=queue_name,
            Attributes={
                'VisibilityTimeout': '60',
                'MessageRetentionPeriod': '86400',
                'ReceiveMessageWaitTimeSeconds': '5'
            }
        )
        queue_url = response['QueueUrl']
    except sqs_client.exceptions.QueueNameExists:
        queue_url = sqs_client.get_queue_url(QueueName=queue_name)['QueueUrl']

    attrs = sqs_client.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['QueueArn']
    )
    queue_arn = attrs['Attributes']['QueueArn']

    print(f"  Queue URL: {queue_url}")
    print(f"  Queue ARN: {queue_arn}")
    return queue_url, queue_arn


def create_dynamodb_table(dynamodb_client):
    """Create DynamoDB table with on-demand capacity (auto-scaling)."""
    print("\n[2/7] Creating DynamoDB Table...")
    table_name = 'FloodSensorData'

    try:
        dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'sensor_type', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'sensor_type', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        print(f"  Waiting for table '{table_name}' to become active...")
        waiter = dynamodb_client.get_waiter('table_exists')
        waiter.wait(TableName=table_name)
        print(f"  Table '{table_name}' is active.")
    except dynamodb_client.exceptions.ResourceInUseException:
        print(f"  Table '{table_name}' already exists.")

    table_info = dynamodb_client.describe_table(TableName=table_name)
    table_arn = table_info['Table']['TableArn']
    print(f"  Table ARN: {table_arn}")
    return table_arn


def create_lambda_role(iam_client, account_id):
    """Create IAM execution role for Lambda functions."""
    print("\n[3/7] Creating IAM Role for Lambda...")
    role_name = f'{PROJECT_PREFIX}-lambda-role'

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='Lambda execution role for flood monitoring system'
        )
        role_arn = response['Role']['Arn']
        print(f"  Created role: {role_name}")

        # Attach managed policies for Lambda, DynamoDB, and SQS access
        policies = [
            'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
            'arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess',
            'arn:aws:iam::aws:policy/AmazonSQSFullAccess'
        ]
        for policy_arn in policies:
            iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
            print(f"  Attached: {policy_arn.split('/')[-1]}")

        print("  Waiting 15s for IAM role propagation...")
        time.sleep(15)

    except iam_client.exceptions.EntityAlreadyExistsException:
        role_arn = f'arn:aws:iam::{account_id}:role/{role_name}'
        print(f"  Role '{role_name}' already exists.")

    print(f"  Role ARN: {role_arn}")
    return role_arn


def create_lambda_zip(code_string):
    """Create in-memory ZIP deployment package for Lambda."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('lambda_function.py', code_string)
    zip_buffer.seek(0)
    return zip_buffer.read()


def deploy_lambda_function(lambda_client, function_name, role_arn, code_path, env_vars=None):
    """Deploy a single Lambda function."""
    print(f"  Deploying: {function_name}...")

    with open(code_path, 'r') as f:
        code = f.read()

    zip_bytes = create_lambda_zip(code)

    # Delete existing function if present
    try:
        lambda_client.delete_function(FunctionName=function_name)
        print(f"  Deleted existing function '{function_name}'")
        time.sleep(3)
    except lambda_client.exceptions.ResourceNotFoundException:
        pass

    config = {
        'FunctionName': function_name,
        'Runtime': 'python3.12',
        'Role': role_arn,
        'Handler': 'lambda_function.handler',
        'Code': {'ZipFile': zip_bytes},
        'Timeout': 30,
        'MemorySize': 256
    }
    if env_vars:
        config['Environment'] = {'Variables': env_vars}

    # Retry in case IAM role hasn't fully propagated
    for attempt in range(5):
        try:
            response = lambda_client.create_function(**config)
            break
        except lambda_client.exceptions.InvalidParameterValueException as e:
            if 'role' in str(e).lower() and attempt < 4:
                print(f"  IAM role not ready, retrying in 10s (attempt {attempt + 1})...")
                time.sleep(10)
            else:
                raise

    # Wait for function to be active
    waiter = lambda_client.get_waiter('function_active_v2')
    waiter.wait(FunctionName=function_name)

    function_arn = response['FunctionArn']
    print(f"  Deployed: {function_name} -> {function_arn}")
    return function_arn


def deploy_lambda_functions(lambda_client, role_arn):
    """Deploy all Lambda functions."""
    print("\n[4/7] Deploying Lambda Functions...")

    env_vars = {'DYNAMODB_TABLE': 'FloodSensorData'}

    ingester_path = os.path.join(SCRIPT_DIR, 'aws_backend', 'lambda_ingester.py')
    dashboard_path = os.path.join(SCRIPT_DIR, 'aws_backend', 'lambda_dashboard.py')

    ingester_arn = deploy_lambda_function(
        lambda_client, 'flood-data-ingester', role_arn, ingester_path, env_vars
    )
    dashboard_arn = deploy_lambda_function(
        lambda_client, 'flood-dashboard-api', role_arn, dashboard_path, env_vars
    )
    return ingester_arn, dashboard_arn


def create_sqs_trigger(lambda_client, ingester_arn, queue_arn):
    """Create SQS event source mapping to trigger the ingester Lambda."""
    print("\n[5/7] Creating SQS -> Lambda Trigger...")

    # Remove any existing event source mappings
    existing = lambda_client.list_event_source_mappings(
        FunctionName='flood-data-ingester',
        EventSourceArn=queue_arn
    )
    for mapping in existing.get('EventSourceMappings', []):
        lambda_client.delete_event_source_mapping(UUID=mapping['UUID'])
        print(f"  Deleted old mapping: {mapping['UUID']}")
        time.sleep(2)

    response = lambda_client.create_event_source_mapping(
        EventSourceArn=queue_arn,
        FunctionName=ingester_arn,
        BatchSize=10,
        Enabled=True
    )
    print(f"  Event source mapping: {response['UUID']}")
    return response['UUID']


def create_api_gateway(apigw_client, lambda_client, dashboard_arn, account_id):
    """Create API Gateway HTTP API for the dashboard."""
    print("\n[6/7] Creating API Gateway...")

    # Delete existing API with same name
    existing_apis = apigw_client.get_apis()
    for api in existing_apis.get('Items', []):
        if api['Name'] == f'{PROJECT_PREFIX}-api':
            apigw_client.delete_api(ApiId=api['ApiId'])
            print(f"  Deleted old API: {api['ApiId']}")
            time.sleep(2)

    # Create HTTP API with CORS
    api = apigw_client.create_api(
        Name=f'{PROJECT_PREFIX}-api',
        ProtocolType='HTTP',
        CorsConfiguration={
            'AllowOrigins': ['*'],
            'AllowMethods': ['GET', 'OPTIONS'],
            'AllowHeaders': ['Content-Type'],
            'MaxAge': 3600
        }
    )
    api_id = api['ApiId']
    print(f"  API ID: {api_id}")

    # Create Lambda integration
    integration = apigw_client.create_integration(
        ApiId=api_id,
        IntegrationType='AWS_PROXY',
        IntegrationUri=dashboard_arn,
        PayloadFormatVersion='2.0'
    )
    integration_id = integration['IntegrationId']

    # Create routes
    routes = ['GET /api/latest', 'GET /api/history', 'GET /api/all-history']
    for route_key in routes:
        apigw_client.create_route(
            ApiId=api_id,
            RouteKey=route_key,
            Target=f'integrations/{integration_id}'
        )
        print(f"  Route: {route_key}")

    # Create auto-deploy stage
    apigw_client.create_stage(
        ApiId=api_id,
        StageName='$default',
        AutoDeploy=True
    )

    # Grant API Gateway permission to invoke Lambda
    try:
        lambda_client.add_permission(
            FunctionName='flood-dashboard-api',
            StatementId='apigateway-invoke',
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=f'arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*'
        )
    except lambda_client.exceptions.ResourceConflictException:
        pass

    api_url = f'https://{api_id}.execute-api.{REGION}.amazonaws.com'
    print(f"  API URL: {api_url}")
    return api_url


def deploy_dashboard(s3_client, api_url, account_id):
    """Deploy the static dashboard to S3 with website hosting."""
    print("\n[7/7] Deploying Dashboard to S3...")

    bucket_name = f'{PROJECT_PREFIX}-dash-{account_id[-6:]}'

    # Create bucket
    try:
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )
        print(f"  Created bucket: {bucket_name}")
    except s3_client.exceptions.BucketAlreadyOwnedByYou:
        print(f"  Bucket '{bucket_name}' already exists.")
    except s3_client.exceptions.BucketAlreadyExists:
        print(f"  Bucket '{bucket_name}' already exists (owned by another account).")
        # Try with longer suffix
        bucket_name = f'{PROJECT_PREFIX}-dash-{account_id}'
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )
        print(f"  Created bucket: {bucket_name}")

    # Disable Block Public Access
    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': False,
            'IgnorePublicAcls': False,
            'BlockPublicPolicy': False,
            'RestrictPublicBuckets': False
        }
    )

    # Enable static website hosting
    s3_client.put_bucket_website(
        Bucket=bucket_name,
        WebsiteConfiguration={
            'IndexDocument': {'Suffix': 'index.html'},
            'ErrorDocument': {'Key': 'index.html'}
        }
    )

    # Add public read policy
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket_name}/*"
        }]
    }
    s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(bucket_policy))

    # Read dashboard HTML and inject API URL
    dashboard_path = os.path.join(SCRIPT_DIR, 'dashboard', 'index.html')
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    html_content = html_content.replace('{{API_BASE_URL}}', api_url)

    # Upload to S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key='index.html',
        Body=html_content.encode('utf-8'),
        ContentType='text/html'
    )

    dashboard_url = f'http://{bucket_name}.s3-website.{REGION}.amazonaws.com'
    print(f"  Dashboard URL: {dashboard_url}")
    return dashboard_url, bucket_name


def main():
    print("=" * 60)
    print("  FLOOD MONITORING SYSTEM - AWS Deployment")
    print(f"  Region: {REGION}")
    print("=" * 60)

    # Get AWS account ID
    account_id = get_account_id()
    print(f"\n  AWS Account: {account_id}")

    # Initialize all AWS clients
    sqs = boto3.client('sqs', region_name=REGION)
    dynamodb = boto3.client('dynamodb', region_name=REGION)
    iam = boto3.client('iam')
    lambda_client = boto3.client('lambda', region_name=REGION)
    apigw = boto3.client('apigatewayv2', region_name=REGION)
    s3 = boto3.client('s3', region_name=REGION)

    # Deploy all resources
    queue_url, queue_arn = create_sqs_queue(sqs)
    table_arn = create_dynamodb_table(dynamodb)
    role_arn = create_lambda_role(iam, account_id)
    ingester_arn, dashboard_arn = deploy_lambda_functions(lambda_client, role_arn)
    create_sqs_trigger(lambda_client, ingester_arn, queue_arn)
    api_url = create_api_gateway(apigw, lambda_client, dashboard_arn, account_id)
    dashboard_url, bucket_name = deploy_dashboard(s3, api_url, account_id)

    # Save deployment config
    config = {
        'region': REGION,
        'account_id': account_id,
        'sqs_queue_url': queue_url,
        'sqs_queue_arn': queue_arn,
        'dynamodb_table': 'FloodSensorData',
        'dynamodb_table_arn': table_arn,
        'lambda_ingester_arn': ingester_arn,
        'lambda_dashboard_arn': dashboard_arn,
        'api_gateway_url': api_url,
        'dashboard_url': dashboard_url,
        's3_bucket': bucket_name
    }

    config_path = os.path.join(SCRIPT_DIR, 'config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print("\n" + "=" * 60)
    print("  DEPLOYMENT COMPLETE!")
    print("=" * 60)
    print(f"\n  Dashboard:   {dashboard_url}")
    print(f"  API Gateway: {api_url}")
    print(f"  SQS Queue:   {queue_url}")
    print(f"\n  Config saved: {config_path}")
    print(f"\n  Next step: python run_simulation.py")
    print("=" * 60)


if __name__ == '__main__':
    main()
