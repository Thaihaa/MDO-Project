import json
import boto3
import time
from datetime import datetime, timezone

def lambda_handler(event, context):
    """
    Lambda function để thực hiện rollback deployment
    """
    try:
        # Lấy thông tin từ event
        deployment_context = event.get('deploymentContext', {})
        error = event.get('error', {})
        
        deployment_id = deployment_context.get('deployment_id')
        environment = deployment_context.get('environment', 'staging')
        
        print(f"Starting rollback for deployment {deployment_id}")
        
        # Khởi tạo AWS clients
        ecs_client = boto3.client('ecs')
        
        # Lấy danh sách services cần rollback
        services_to_rollback = ['auth-service', 'menu-service', 'order-service', 'payment-service']
        
        rollback_results = {}
        rollback_success = True
        
        for service_name in services_to_rollback:
            try:
                print(f"Rolling back {service_name}...")
                
                rollback_result = rollback_service(
                    ecs_client, 
                    service_name, 
                    environment, 
                    deployment_id
                )
                
                rollback_results[service_name] = rollback_result
                
                if not rollback_result.get('success', False):
                    rollback_success = False
                    print(f"Rollback failed for {service_name}: {rollback_result.get('error')}")
                else:
                    print(f"Rollback successful for {service_name}")
                
            except Exception as e:
                error_message = f"Error rolling back {service_name}: {str(e)}"
                print(error_message)
                
                rollback_results[service_name] = {
                    'success': False,
                    'error': error_message
                }
                rollback_success = False
        
        # Ghi log rollback
        log_rollback_activity(deployment_context, rollback_results, rollback_success)
        
        # Gửi thông báo về kết quả rollback
        send_rollback_notification(deployment_context, rollback_results, rollback_success)
        
        result = {
            'statusCode': 200,
            'deployment_id': deployment_id,
            'rollback_status': 'completed' if rollback_success else 'partially_failed',
            'services_rollback_results': rollback_results,
            'rollback_success': rollback_success,
            'rollback_time': datetime.now(timezone.utc).isoformat(),
            'original_error': error,
            'message': 'Rollback completed' if rollback_success else 'Rollback completed with some failures'
        }
        
        print(f"Rollback completed for deployment {deployment_id}. Success: {rollback_success}")
        return result
        
    except Exception as e:
        error_message = f"Critical error during rollback: {str(e)}"
        print(error_message)
        
        return {
            'statusCode': 500,
            'deployment_id': deployment_context.get('deployment_id') if deployment_context else None,
            'rollback_status': 'failed',
            'error': error_message,
            'rollback_time': datetime.now(timezone.utc).isoformat(),
            'message': 'Rollback process failed'
        }

def rollback_service(ecs_client, service_name, environment, deployment_id):
    """Rollback một service cụ thể về version trước đó"""
    try:
        service_config = get_service_config(service_name, environment)
        cluster_name = service_config['cluster_name']
        service_name_full = service_config['service_name']
        
        # 1. Lấy thông tin service hiện tại
        current_service_info = get_current_service_info(ecs_client, cluster_name, service_name_full)
        if not current_service_info:
            return {'success': False, 'error': 'Service not found'}
        
        # 2. Tìm task definition trước đó
        previous_task_def = find_previous_task_definition(
            ecs_client, 
            current_service_info['taskDefinition'],
            deployment_id
        )
        
        if not previous_task_def:
            return {'success': False, 'error': 'No previous task definition found for rollback'}
        
        # 3. Cập nhật service với task definition cũ
        rollback_result = update_service_to_previous_version(
            ecs_client,
            cluster_name,
            service_name_full,
            previous_task_def,
            current_service_info['desiredCount']
        )
        
        if not rollback_result['success']:
            return rollback_result
        
        # 4. Chờ rollback hoàn thành
        wait_result = wait_for_rollback_completion(
            ecs_client,
            cluster_name,
            service_name_full,
            max_wait_time=300
        )
        
        return {
            'success': True,
            'previous_task_definition': previous_task_def,
            'current_task_definition': current_service_info['taskDefinition'],
            'rollback_deployment_status': wait_result,
            'rollback_time': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'rollback_time': datetime.now(timezone.utc).isoformat()
        }

def get_service_config(service_name, environment):
    """Lấy cấu hình cho service"""
    base_config = {
        'auth-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'auth-service-{environment}',
            'family_prefix': 'auth-service'
        },
        'menu-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'menu-service-{environment}',
            'family_prefix': 'menu-service'
        },
        'order-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'order-service-{environment}',
            'family_prefix': 'order-service'
        },
        'payment-service': {
            'cluster_name': f'restaurant-{environment}',
            'service_name': f'payment-service-{environment}',
            'family_prefix': 'payment-service'
        }
    }
    
    return base_config.get(service_name, {})

def get_current_service_info(ecs_client, cluster_name, service_name):
    """Lấy thông tin service hiện tại"""
    try:
        response = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not response['services']:
            return None
        
        service = response['services'][0]
        
        return {
            'serviceName': service['serviceName'],
            'taskDefinition': service['taskDefinition'],
            'desiredCount': service['desiredCount'],
            'runningCount': service['runningCount'],
            'status': service['status']
        }
        
    except Exception as e:
        print(f"Error getting current service info: {str(e)}")
        return None

def find_previous_task_definition(ecs_client, current_task_def_arn, deployment_id):
    """Tìm task definition trước đó để rollback"""
    try:
        # Extract family name từ current task definition ARN
        # Format: arn:aws:ecs:region:account:task-definition/family:revision
        family_name = current_task_def_arn.split('/')[-1].split(':')[0]
        
        # Loại bỏ deployment ID khỏi family name nếu có
        if deployment_id in family_name:
            base_family = family_name.replace(f'-{deployment_id}', '')
        else:
            base_family = family_name
        
        # Liệt kê các task definitions của family
        response = ecs_client.list_task_definitions(
            familyPrefix=base_family,
            status='ACTIVE',
            sort='DESC'  # Sắp xếp theo thứ tự mới nhất trước
        )
        
        task_definitions = response['taskDefinitionArns']
        
        # Tìm task definition gần nhất không phải là của deployment hiện tại
        for task_def_arn in task_definitions:
            if deployment_id not in task_def_arn and task_def_arn != current_task_def_arn:
                print(f"Found previous task definition for rollback: {task_def_arn}")
                return task_def_arn
        
        # Nếu không tìm thấy, thử tìm task definition cũ nhất
        if len(task_definitions) > 1:
            # Lấy task definition cũ nhất (không phải current)
            for task_def_arn in reversed(task_definitions):
                if task_def_arn != current_task_def_arn:
                    print(f"Using oldest available task definition for rollback: {task_def_arn}")
                    return task_def_arn
        
        print("No suitable task definition found for rollback")
        return None
        
    except Exception as e:
        print(f"Error finding previous task definition: {str(e)}")
        return None

def update_service_to_previous_version(ecs_client, cluster_name, service_name, previous_task_def, desired_count):
    """Cập nhật service về version trước đó"""
    try:
        print(f"Updating service {service_name} to previous task definition: {previous_task_def}")
        
        response = ecs_client.update_service(
            cluster=cluster_name,
            service=service_name,
            taskDefinition=previous_task_def,
            desiredCount=desired_count,
            forceNewDeployment=True  # Force deployment để đảm bảo rollback
        )
        
        return {
            'success': True,
            'deployment_id': response['service']['deployments'][0]['id'],
            'task_definition': previous_task_def
        }
        
    except Exception as e:
        error_message = f"Error updating service to previous version: {str(e)}"
        print(error_message)
        return {
            'success': False,
            'error': error_message
        }

def wait_for_rollback_completion(ecs_client, cluster_name, service_name, max_wait_time=300):
    """Chờ rollback hoàn thành"""
    start_time = time.time()
    
    print(f"Waiting for rollback completion of {service_name}...")
    
    while time.time() - start_time < max_wait_time:
        try:
            response = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if not response['services']:
                return {'status': 'ERROR', 'message': 'Service not found'}
            
            service = response['services'][0]
            deployments = service['deployments']
            
            # Tìm PRIMARY deployment
            primary_deployment = next(
                (d for d in deployments if d['status'] == 'PRIMARY'), 
                None
            )
            
            if primary_deployment:
                running_count = primary_deployment['runningCount']
                desired_count = primary_deployment['desiredCount']
                
                print(f"Rollback progress: {running_count}/{desired_count} tasks")
                
                # Kiểm tra xem còn deployment cũ nào đang PENDING không
                pending_deployments = [d for d in deployments if d['status'] == 'PENDING']
                
                if running_count == desired_count and not pending_deployments:
                    return {
                        'status': 'COMPLETED',
                        'running_count': running_count,
                        'desired_count': desired_count,
                        'deployment_id': primary_deployment['id']
                    }
            
            time.sleep(10)
            
        except Exception as e:
            print(f"Error checking rollback status: {str(e)}")
            time.sleep(10)
    
    return {
        'status': 'TIMEOUT',
        'message': f'Rollback did not complete within {max_wait_time} seconds'
    }

def log_rollback_activity(deployment_context, rollback_results, rollback_success):
    """Ghi log rollback activity"""
    try:
        cloudwatch_logs = boto3.client('logs')
        log_group = '/aws/stepfunctions/restaurant-deployment'
        log_stream = f'rollback-{deployment_context.get("deployment_id")}'
        
        log_event = {
            'timestamp': int(datetime.now().timestamp() * 1000),
            'message': json.dumps({
                'event': 'deployment_rollback',
                'deployment_id': deployment_context.get('deployment_id'),
                'environment': deployment_context.get('environment'),
                'rollback_success': rollback_success,
                'rollback_results': rollback_results,
                'rollback_timestamp': datetime.now(timezone.utc).isoformat()
            }, indent=2)
        }
        
        try:
            cloudwatch_logs.create_log_stream(
                logGroupName=log_group,
                logStreamName=log_stream
            )
        except cloudwatch_logs.exceptions.ResourceAlreadyExistsException:
            pass
        
        cloudwatch_logs.put_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            logEvents=[log_event]
        )
        
        print(f"Rollback activity logged to CloudWatch")
        
    except Exception as e:
        print(f"Error logging rollback activity: {str(e)}")

def send_rollback_notification(deployment_context, rollback_results, rollback_success):
    """Gửi thông báo về kết quả rollback"""
    try:
        # Gọi deployment notifier để gửi thông báo rollback
        lambda_client = boto3.client('lambda')
        
        notification_payload = {
            'status': 'ROLLBACK_SUCCESS' if rollback_success else 'ROLLBACK_PARTIAL',
            'deployment_context': deployment_context,
            'rollback_results': rollback_results,
            'rollback_success': rollback_success
        }
        
        response = lambda_client.invoke(
            FunctionName='deployment-notifier',
            InvocationType='Event',  # Async invoke
            Payload=json.dumps(notification_payload)
        )
        
        print(f"Rollback notification sent")
        
    except Exception as e:
        print(f"Error sending rollback notification: {str(e)}")

def cleanup_failed_task_definitions(ecs_client, deployment_id):
    """Dọn dẹp các task definitions không sử dụng từ deployment thất bại"""
    try:
        # Tìm tất cả task definitions có chứa deployment_id
        families = ['auth-service', 'menu-service', 'order-service', 'payment-service']
        
        for family in families:
            response = ecs_client.list_task_definitions(
                familyPrefix=f'{family}-{deployment_id}',
                status='ACTIVE'
            )
            
            for task_def_arn in response['taskDefinitionArns']:
                try:
                    # Deregister task definition
                    ecs_client.deregister_task_definition(
                        taskDefinition=task_def_arn
                    )
                    print(f"Deregistered task definition: {task_def_arn}")
                    
                except Exception as e:
                    print(f"Error deregistering task definition {task_def_arn}: {str(e)}")
        
        print(f"Cleanup completed for deployment {deployment_id}")
        
    except Exception as e:
        print(f"Error during cleanup: {str(e)}") 