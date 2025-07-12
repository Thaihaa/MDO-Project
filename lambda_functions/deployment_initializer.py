import json
import boto3
import uuid
from datetime import datetime, timezone
import os

def lambda_handler(event, context):
    """
    Lambda function để khởi tạo deployment context
    """
    try:
        # Tạo deployment ID duy nhất
        deployment_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Lấy thông tin từ event
        environment = event.get('environment', 'staging')
        version = event.get('version', 'latest')
        region = event.get('region', os.environ.get('AWS_REGION', 'us-east-1'))
        
        # Tạo deployment context
        deployment_context = {
            "deployment_id": deployment_id,
            "timestamp": timestamp,
            "environment": environment,
            "version": version,
            "region": region,
            "status": "initialized",
            "services": {
                "auth-service": {"status": "pending", "deployment_time": None},
                "menu-service": {"status": "pending", "deployment_time": None},
                "order-service": {"status": "pending", "deployment_time": None},
                "payment-service": {"status": "pending", "deployment_time": None}
            },
            "rollback_required": False
        }
        
        # Log deployment khởi tạo
        print(f"Deployment initialized: {deployment_id}")
        print(f"Environment: {environment}")
        print(f"Version: {version}")
        
        # Ghi log vào CloudWatch
        cloudwatch_logs = boto3.client('logs')
        log_group = '/aws/stepfunctions/restaurant-deployment'
        
        try:
            cloudwatch_logs.put_log_events(
                logGroupName=log_group,
                logStreamName=f'deployment-{deployment_id}',
                logEvents=[
                    {
                        'timestamp': int(datetime.now().timestamp() * 1000),
                        'message': json.dumps({
                            'event': 'deployment_initialized',
                            'deployment_id': deployment_id,
                            'environment': environment,
                            'version': version
                        })
                    }
                ]
            )
        except Exception as log_error:
            print(f"CloudWatch logging error: {str(log_error)}")
        
        return {
            'statusCode': 200,
            'deployment_context': deployment_context,
            'message': 'Deployment initialized successfully'
        }
        
    except Exception as e:
        error_message = f"Error initializing deployment: {str(e)}"
        print(error_message)
        
        return {
            'statusCode': 500,
            'error': error_message,
            'message': 'Failed to initialize deployment'
        } 