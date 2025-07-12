import json
import boto3
import time
from datetime import datetime, timezone
import os

def lambda_handler(event, context):
    """
    Lambda function để deploy microservice
    """
    try:
        # Lấy thông tin từ event
        service_name = event.get('service_name')
        deployment_context = event.get('deployment_context')
        
        if not service_name or not deployment_context:
            raise ValueError("Missing required parameters: service_name or deployment_context")
        
        deployment_id = deployment_context.get('deployment_id')
        environment = deployment_context.get('environment', 'staging')
        version = deployment_context.get('version', 'latest')
        
        print(f"Deploying {service_name} for deployment {deployment_id}")
        
        # Khởi tạo AWS clients
        ecs_client = boto3.client('ecs')
        ecr_client = boto3.client('ecr')
        
        # Cấu hình service
        service_config = get_service_config(service_name, environment)
        
        # 1. Kiểm tra image trong ECR
        image_uri = check_and_get_image(ecr_client, service_config, version)
        
        # 2. Cập nhật task definition
        task_definition_arn = update_task_definition(ecs_client, service_config, image_uri, deployment_id)
        
        # 3. Deploy service lên ECS
        service_arn = deploy_to_ecs(ecs_client, service_config, task_definition_arn, environment)
        
        # 4. Chờ deployment hoàn thành
        deployment_status = wait_for_deployment(ecs_client, service_config['cluster_name'], service_config['service_name'])
        
        result = {
            'statusCode': 200,
            'service_name': service_name,
            'deployment_id': deployment_id,
            'task_definition_arn': task_definition_arn,
            'service_arn': service_arn,
            'deployment_status': deployment_status,
            'image_uri': image_uri,
            'deployment_time': datetime.now(timezone.utc).isoformat(),
            'message': f'{service_name} deployed successfully'
        }
        
        print(f"Successfully deployed {service_name}")
        return result
        
    except Exception as e:
        error_message = f"Error deploying {service_name}: {str(e)}"
        print(error_message)
        
        return {
            'statusCode': 500,
            'error': error_message,
            'service_name': service_name,
            'deployment_id': deployment_context.get('deployment_id') if deployment_context else None,
            'message': f'Failed to deploy {service_name}'
        }

def get_service_config(service_name, environment):
    """Lấy cấu hình cho service"""
    base_config = {
        'auth-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'auth-service-{environment}',
            'repository_name': 'restaurant/auth-service',
            'port': 8080,
            'cpu': 256,
            'memory': 512,
            'desired_count': 2
        },
        'menu-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'menu-service-{environment}',
            'repository_name': 'restaurant/menu-service',
            'port': 8081,
            'cpu': 256,
            'memory': 512,
            'desired_count': 2
        },
        'order-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'order-service-{environment}',
            'repository_name': 'restaurant/order-service',
            'port': 8082,
            'cpu': 512,
            'memory': 1024,
            'desired_count': 3
        },
        'payment-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'payment-service-{environment}',
            'repository_name': 'restaurant/payment-service',
            'port': 8083,
            'cpu': 256,
            'memory': 512,
            'desired_count': 2
        }
    }
    
    if service_name not in base_config:
        raise ValueError(f"Unknown service: {service_name}")
    
    return base_config[service_name]

def check_and_get_image(ecr_client, service_config, version):
    """Kiểm tra và lấy image URI từ ECR"""
    try:
        repository_name = service_config['repository_name']
        
        # Lấy thông tin image
        response = ecr_client.describe_images(
            repositoryName=repository_name,
            imageIds=[{'imageTag': version}]
        )
        
        if not response['imageDetails']:
            raise ValueError(f"Image {repository_name}:{version} not found in ECR")
        
        # Lấy registry ID từ response
        registry_id = response['imageDetails'][0]['registryId']
        region = ecr_client.meta.region_name
        
        image_uri = f"{registry_id}.dkr.ecr.{region}.amazonaws.com/{repository_name}:{version}"
        print(f"Found image: {image_uri}")
        
        return image_uri
        
    except ecr_client.exceptions.RepositoryNotFoundException:
        raise ValueError(f"ECR repository {repository_name} not found")
    except Exception as e:
        raise ValueError(f"Error checking ECR image: {str(e)}")

def update_task_definition(ecs_client, service_config, image_uri, deployment_id):
    """Tạo hoặc cập nhật task definition"""
    try:
        task_def_name = f"{service_config['service_name']}-{deployment_id}"
        
        task_definition = {
            'family': task_def_name,
            'networkMode': 'awsvpc',
            'requiresCompatibilities': ['FARGATE'],
            'cpu': str(service_config['cpu']),
            'memory': str(service_config['memory']),
            'executionRoleArn': os.environ.get('TASK_EXECUTION_ROLE_ARN'),
            'taskRoleArn': os.environ.get('TASK_ROLE_ARN'),
            'containerDefinitions': [
                {
                    'name': service_config['service_name'],
                    'image': image_uri,
                    'cpu': service_config['cpu'],
                    'memory': service_config['memory'],
                    'essential': True,
                    'portMappings': [
                        {
                            'containerPort': service_config['port'],
                            'protocol': 'tcp'
                        }
                    ],
                    'logConfiguration': {
                        'logDriver': 'awslogs',
                        'options': {
                            'awslogs-group': f'/ecs/{service_config["service_name"]}',
                            'awslogs-region': os.environ.get('AWS_REGION', 'us-east-1'),
                            'awslogs-stream-prefix': 'ecs'
                        }
                    },
                    'environment': [
                        {
                            'name': 'ENVIRONMENT',
                            'value': 'production'
                        },
                        {
                            'name': 'PORT',
                            'value': str(service_config['port'])
                        }
                    ]
                }
            ]
        }
        
        response = ecs_client.register_task_definition(**task_definition)
        task_definition_arn = response['taskDefinition']['taskDefinitionArn']
        
        print(f"Registered task definition: {task_definition_arn}")
        return task_definition_arn
        
    except Exception as e:
        raise ValueError(f"Error creating task definition: {str(e)}")

def deploy_to_ecs(ecs_client, service_config, task_definition_arn, environment):
    """Deploy service lên ECS cluster"""
    try:
        cluster_name = service_config['cluster_name']
        service_name = service_config['service_name']
        
        # Kiểm tra service đã tồn tại chưa
        try:
            services_response = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            service_exists = len(services_response['services']) > 0 and \
                           services_response['services'][0]['status'] != 'INACTIVE'
            
        except Exception:
            service_exists = False
        
        if service_exists:
            # Cập nhật service hiện tại
            response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=task_definition_arn,
                desiredCount=service_config['desired_count']
            )
            print(f"Updated existing service: {service_name}")
        else:
            # Tạo service mới
            response = ecs_client.create_service(
                cluster=cluster_name,
                serviceName=service_name,
                taskDefinition=task_definition_arn,
                desiredCount=service_config['desired_count'],
                launchType='FARGATE',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': os.environ.get('SUBNET_IDS', '').split(','),
                        'securityGroups': [os.environ.get('SECURITY_GROUP_ID')],
                        'assignPublicIp': 'ENABLED'
                    }
                }
            )
            print(f"Created new service: {service_name}")
        
        return response['service']['serviceArn']
        
    except Exception as e:
        raise ValueError(f"Error deploying to ECS: {str(e)}")

def wait_for_deployment(ecs_client, cluster_name, service_name, max_wait_time=300):
    """Chờ deployment hoàn thành"""
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            service = response['services'][0]
            deployments = service['deployments']
            
            # Tìm deployment PRIMARY
            primary_deployment = None
            for deployment in deployments:
                if deployment['status'] == 'PRIMARY':
                    primary_deployment = deployment
                    break
            
            if primary_deployment:
                running_count = primary_deployment['runningCount']
                desired_count = primary_deployment['desiredCount']
                
                print(f"Deployment status: {running_count}/{desired_count} tasks running")
                
                if running_count == desired_count:
                    return {
                        'status': 'STABLE',
                        'running_count': running_count,
                        'desired_count': desired_count
                    }
            
            time.sleep(10)
            
        except Exception as e:
            print(f"Error checking deployment status: {str(e)}")
            time.sleep(10)
    
    return {
        'status': 'TIMEOUT',
        'message': f'Deployment did not stabilize within {max_wait_time} seconds'
    } 