import json
import boto3
import requests
import time
from datetime import datetime, timezone

def lambda_handler(event, context):
    """
    Lambda function để kiểm tra health của microservice
    """
    try:
        # Lấy thông tin từ event
        service_name = event.get('service_name')
        deployment_result = event.get('deployment_result')
        
        if not service_name or not deployment_result:
            raise ValueError("Missing required parameters: service_name or deployment_result")
        
        print(f"Checking health for {service_name}")
        
        # Lấy thông tin deployment
        service_arn = deployment_result.get('service_arn')
        deployment_id = deployment_result.get('deployment_id')
        
        # Khởi tạo AWS clients
        ecs_client = boto3.client('ecs')
        ec2_client = boto3.client('ec2')
        
        # Lấy cấu hình service
        service_config = get_service_config(service_name)
        
        # 1. Kiểm tra ECS service status
        ecs_status = check_ecs_service_status(ecs_client, service_config)
        if not ecs_status['healthy']:
            return create_unhealthy_response(service_name, "ECS service not stable", ecs_status)
        
        # 2. Lấy danh sách tasks đang chạy
        task_arns = get_running_tasks(ecs_client, service_config)
        if not task_arns:
            return create_unhealthy_response(service_name, "No running tasks found", {})
        
        # 3. Lấy IP addresses của các tasks
        task_ips = get_task_ips(ecs_client, ec2_client, service_config, task_arns)
        if not task_ips:
            return create_unhealthy_response(service_name, "No task IPs found", {})
        
        # 4. Kiểm tra health endpoint của từng task
        health_results = []
        for task_ip in task_ips:
            health_result = check_health_endpoint(task_ip, service_config)
            health_results.append(health_result)
        
        # 5. Đánh giá tổng thể
        healthy_count = sum(1 for result in health_results if result['healthy'])
        total_count = len(health_results)
        
        # Service được coi là healthy nếu ít nhất 50% tasks healthy
        overall_healthy = healthy_count >= (total_count * 0.5)
        
        result = {
            'statusCode': 200,
            'service_name': service_name,
            'deployment_id': deployment_id,
            'status': 'healthy' if overall_healthy else 'unhealthy',
            'healthy_tasks': healthy_count,
            'total_tasks': total_count,
            'health_details': health_results,
            'ecs_status': ecs_status,
            'check_time': datetime.now(timezone.utc).isoformat(),
            'message': f'Health check completed for {service_name}'
        }
        
        print(f"Health check result for {service_name}: {result['status']} ({healthy_count}/{total_count})")
        return result
        
    except Exception as e:
        error_message = f"Error checking health for {service_name}: {str(e)}"
        print(error_message)
        
        return {
            'statusCode': 500,
            'service_name': service_name,
            'status': 'unhealthy',
            'error': error_message,
            'check_time': datetime.now(timezone.utc).isoformat(),
            'message': f'Health check failed for {service_name}'
        }

def get_service_config(service_name):
    """Lấy cấu hình cho service"""
    base_config = {
        'auth-service': {
            'cluster_name': 'restaurant-staging',
            'service_name': 'auth-service-staging',
            'port': 8080,
            'health_path': '/health'
        },
        'menu-service': {
            'cluster_name': 'restaurant-staging',
            'service_name': 'menu-service-staging',
            'port': 8081,
            'health_path': '/health'
        },
        'order-service': {
            'cluster_name': 'restaurant-staging',
            'service_name': 'order-service-staging',
            'port': 8082,
            'health_path': '/health'
        },
        'payment-service': {
            'cluster_name': 'restaurant-staging',
            'service_name': 'payment-service-staging',
            'port': 8083,
            'health_path': '/health'
        }
    }
    
    if service_name not in base_config:
        raise ValueError(f"Unknown service: {service_name}")
    
    return base_config[service_name]

def check_ecs_service_status(ecs_client, service_config):
    """Kiểm tra trạng thái ECS service"""
    try:
        response = ecs_client.describe_services(
            cluster=service_config['cluster_name'],
            services=[service_config['service_name']]
        )
        
        if not response['services']:
            return {'healthy': False, 'reason': 'Service not found'}
        
        service = response['services'][0]
        
        # Kiểm tra service status
        if service['status'] != 'ACTIVE':
            return {'healthy': False, 'reason': f"Service status: {service['status']}"}
        
        # Kiểm tra deployments
        deployments = service['deployments']
        primary_deployment = None
        
        for deployment in deployments:
            if deployment['status'] == 'PRIMARY':
                primary_deployment = deployment
                break
        
        if not primary_deployment:
            return {'healthy': False, 'reason': 'No primary deployment found'}
        
        # Kiểm tra running vs desired count
        running_count = primary_deployment['runningCount']
        desired_count = primary_deployment['desiredCount']
        
        if running_count < desired_count:
            return {
                'healthy': False, 
                'reason': f'Not enough running tasks: {running_count}/{desired_count}'
            }
        
        return {
            'healthy': True,
            'running_count': running_count,
            'desired_count': desired_count,
            'deployment_status': primary_deployment['status']
        }
        
    except Exception as e:
        return {'healthy': False, 'reason': f'ECS check error: {str(e)}'}

def get_running_tasks(ecs_client, service_config):
    """Lấy danh sách tasks đang chạy"""
    try:
        response = ecs_client.list_tasks(
            cluster=service_config['cluster_name'],
            serviceName=service_config['service_name'],
            desiredStatus='RUNNING'
        )
        
        return response['taskArns']
        
    except Exception as e:
        print(f"Error getting running tasks: {str(e)}")
        return []

def get_task_ips(ecs_client, ec2_client, service_config, task_arns):
    """Lấy IP addresses của các tasks"""
    try:
        if not task_arns:
            return []
        
        # Lấy thông tin chi tiết của tasks
        response = ecs_client.describe_tasks(
            cluster=service_config['cluster_name'],
            tasks=task_arns
        )
        
        task_ips = []
        
        for task in response['tasks']:
            # Lấy ENI ID từ task
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'networkInterfaceId':
                            eni_id = detail['value']
                            
                            # Lấy public IP từ ENI
                            eni_response = ec2_client.describe_network_interfaces(
                                NetworkInterfaceIds=[eni_id]
                            )
                            
                            if eni_response['NetworkInterfaces']:
                                eni = eni_response['NetworkInterfaces'][0]
                                
                                # Ưu tiên public IP, fallback về private IP
                                if 'Association' in eni and 'PublicIp' in eni['Association']:
                                    task_ips.append(eni['Association']['PublicIp'])
                                elif 'PrivateIpAddress' in eni:
                                    task_ips.append(eni['PrivateIpAddress'])
        
        return task_ips
        
    except Exception as e:
        print(f"Error getting task IPs: {str(e)}")
        return []

def check_health_endpoint(ip_address, service_config, timeout=10, retries=3):
    """Kiểm tra health endpoint của một task"""
    health_url = f"http://{ip_address}:{service_config['port']}{service_config['health_path']}"
    
    for attempt in range(retries):
        try:
            print(f"Checking health endpoint: {health_url} (attempt {attempt + 1})")
            
            response = requests.get(health_url, timeout=timeout)
            
            if response.status_code == 200:
                # Kiểm tra response content nếu có
                try:
                    health_data = response.json()
                    if health_data.get('status') == 'healthy':
                        return {
                            'ip': ip_address,
                            'healthy': True,
                            'status_code': response.status_code,
                            'response_time': response.elapsed.total_seconds(),
                            'health_data': health_data
                        }
                except:
                    # Nếu không parse được JSON, coi response 200 là healthy
                    return {
                        'ip': ip_address,
                        'healthy': True,
                        'status_code': response.status_code,
                        'response_time': response.elapsed.total_seconds(),
                        'health_data': {'raw_response': response.text[:200]}
                    }
            
            # Status code khác 200
            return {
                'ip': ip_address,
                'healthy': False,
                'status_code': response.status_code,
                'reason': f'HTTP {response.status_code}',
                'response_text': response.text[:200]
            }
            
        except requests.exceptions.Timeout:
            if attempt == retries - 1:  # Last attempt
                return {
                    'ip': ip_address,
                    'healthy': False,
                    'reason': f'Timeout after {timeout}s'
                }
            time.sleep(2)  # Wait before retry
            
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:  # Last attempt
                return {
                    'ip': ip_address,
                    'healthy': False,
                    'reason': 'Connection refused'
                }
            time.sleep(2)  # Wait before retry
            
        except Exception as e:
            if attempt == retries - 1:  # Last attempt
                return {
                    'ip': ip_address,
                    'healthy': False,
                    'reason': f'Request error: {str(e)}'
                }
            time.sleep(2)  # Wait before retry
    
    return {
        'ip': ip_address,
        'healthy': False,
        'reason': 'All retry attempts failed'
    }

def create_unhealthy_response(service_name, reason, details):
    """Tạo response cho trường hợp unhealthy"""
    return {
        'statusCode': 200,
        'service_name': service_name,
        'status': 'unhealthy',
        'reason': reason,
        'details': details,
        'check_time': datetime.now(timezone.utc).isoformat(),
        'message': f'Health check failed for {service_name}: {reason}'
    } 