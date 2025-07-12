import json
import boto3
import requests
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

def lambda_handler(event, context):
    """
    Lambda function để kiểm tra tổng thể health của tất cả microservices
    """
    try:
        # Lấy thông tin từ event
        deployment_context = event.get('deploymentContext', {})
        deployment_id = deployment_context.get('deployment_id')
        
        print(f"Performing final health check for deployment {deployment_id}")
        
        # Danh sách các services cần kiểm tra
        services = ['auth-service', 'menu-service', 'order-service', 'payment-service']
        
        # Khởi tạo AWS clients
        ecs_client = boto3.client('ecs')
        ec2_client = boto3.client('ec2')
        
        # Kiểm tra health của tất cả services song song
        health_results = {}
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_service = {
                executor.submit(check_service_health, ecs_client, ec2_client, service): service
                for service in services
            }
            
            for future in as_completed(future_to_service):
                service = future_to_service[future]
                try:
                    health_result = future.result()
                    health_results[service] = health_result
                except Exception as e:
                    print(f"Error checking {service}: {str(e)}")
                    health_results[service] = {
                        'healthy': False,
                        'error': str(e),
                        'check_time': datetime.now(timezone.utc).isoformat()
                    }
        
        # Kiểm tra inter-service connectivity
        connectivity_results = check_inter_service_connectivity(health_results)
        
        # Đánh giá tổng thể
        overall_assessment = evaluate_overall_health(health_results, connectivity_results)
        
        result = {
            'statusCode': 200,
            'deployment_id': deployment_id,
            'overall_status': overall_assessment['status'],
            'healthy_services': overall_assessment['healthy_count'],
            'total_services': overall_assessment['total_count'],
            'service_health_details': health_results,
            'connectivity_check': connectivity_results,
            'summary': overall_assessment['summary'],
            'recommendations': overall_assessment['recommendations'],
            'check_time': datetime.now(timezone.utc).isoformat(),
            'message': f'Final health check completed: {overall_assessment["status"]}'
        }
        
        print(f"Final health check result: {result['overall_status']}")
        print(f"Healthy services: {result['healthy_services']}/{result['total_services']}")
        
        return result
        
    except Exception as e:
        error_message = f"Error in final health check: {str(e)}"
        print(error_message)
        
        return {
            'statusCode': 500,
            'deployment_id': deployment_context.get('deployment_id') if deployment_context else None,
            'overall_status': 'unhealthy',
            'error': error_message,
            'check_time': datetime.now(timezone.utc).isoformat(),
            'message': 'Final health check failed'
        }

def check_service_health(ecs_client, ec2_client, service_name):
    """Kiểm tra health của một service cụ thể"""
    try:
        service_config = get_service_config(service_name)
        
        # 1. Kiểm tra ECS service status
        ecs_status = check_ecs_service_status(ecs_client, service_config)
        
        # 2. Lấy task IPs
        task_arns = get_running_tasks(ecs_client, service_config)
        task_ips = get_task_ips(ecs_client, ec2_client, service_config, task_arns)
        
        # 3. Kiểm tra health endpoints
        endpoint_results = []
        if task_ips:
            for ip in task_ips:
                endpoint_result = check_health_endpoint(ip, service_config)
                endpoint_results.append(endpoint_result)
        
        # 4. Đánh giá tổng thể cho service này
        healthy_endpoints = sum(1 for result in endpoint_results if result.get('healthy', False))
        total_endpoints = len(endpoint_results)
        
        service_healthy = (
            ecs_status.get('healthy', False) and 
            healthy_endpoints > 0 and 
            healthy_endpoints >= (total_endpoints * 0.5)  # Ít nhất 50% endpoints healthy
        )
        
        return {
            'healthy': service_healthy,
            'ecs_status': ecs_status,
            'endpoints': {
                'total': total_endpoints,
                'healthy': healthy_endpoints,
                'details': endpoint_results
            },
            'task_ips': task_ips,
            'check_time': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            'healthy': False,
            'error': str(e),
            'check_time': datetime.now(timezone.utc).isoformat()
        }

def check_inter_service_connectivity(health_results):
    """Kiểm tra connectivity giữa các services"""
    connectivity_tests = [
        {
            'from': 'menu-service',
            'to': 'auth-service',
            'endpoint': '/validate-token',
            'description': 'Menu service -> Auth service token validation'
        },
        {
            'from': 'order-service',
            'to': 'auth-service',
            'endpoint': '/validate-token',
            'description': 'Order service -> Auth service token validation'
        },
        {
            'from': 'order-service',
            'to': 'menu-service',
            'endpoint': '/menu/items',
            'description': 'Order service -> Menu service item lookup'
        },
        {
            'from': 'order-service',
            'to': 'payment-service',
            'endpoint': '/payment/process',
            'description': 'Order service -> Payment service payment processing'
        }
    ]
    
    connectivity_results = []
    
    for test in connectivity_tests:
        from_service = test['from']
        to_service = test['to']
        
        # Kiểm tra cả hai services có healthy không
        from_healthy = health_results.get(from_service, {}).get('healthy', False)
        to_healthy = health_results.get(to_service, {}).get('healthy', False)
        
        if not from_healthy or not to_healthy:
            connectivity_results.append({
                'test': test['description'],
                'status': 'skipped',
                'reason': f'Source or target service not healthy ({from_service}: {from_healthy}, {to_service}: {to_healthy})'
            })
            continue
        
        # Lấy IP của target service
        to_ips = health_results.get(to_service, {}).get('task_ips', [])
        if not to_ips:
            connectivity_results.append({
                'test': test['description'],
                'status': 'failed',
                'reason': f'No IPs found for {to_service}'
            })
            continue
        
        # Test connectivity với IP đầu tiên của target service
        target_ip = to_ips[0]
        to_service_config = get_service_config(to_service)
        
        connectivity_test_result = test_service_connectivity(
            target_ip, 
            to_service_config['port'], 
            test['endpoint']
        )
        
        connectivity_results.append({
            'test': test['description'],
            'status': 'success' if connectivity_test_result['connected'] else 'failed',
            'target_ip': target_ip,
            'response_time': connectivity_test_result.get('response_time'),
            'details': connectivity_test_result
        })
    
    return connectivity_results

def test_service_connectivity(ip, port, endpoint, timeout=5):
    """Test connectivity tới một service endpoint"""
    try:
        url = f"http://{ip}:{port}{endpoint}"
        
        start_time = time.time()
        response = requests.get(url, timeout=timeout)
        response_time = time.time() - start_time
        
        return {
            'connected': True,
            'status_code': response.status_code,
            'response_time': response_time,
            'url': url
        }
        
    except requests.exceptions.Timeout:
        return {
            'connected': False,
            'error': 'timeout',
            'url': url
        }
    except requests.exceptions.ConnectionError:
        return {
            'connected': False,
            'error': 'connection_refused',
            'url': url
        }
    except Exception as e:
        return {
            'connected': False,
            'error': str(e),
            'url': url
        }

def evaluate_overall_health(health_results, connectivity_results):
    """Đánh giá tổng thể health của deployment"""
    total_services = len(health_results)
    healthy_services = sum(1 for result in health_results.values() if result.get('healthy', False))
    
    # Đếm connectivity tests thành công
    connectivity_tests = len(connectivity_results)
    successful_connectivity = sum(1 for result in connectivity_results if result['status'] == 'success')
    
    # Xác định overall status
    if healthy_services == total_services and successful_connectivity >= (connectivity_tests * 0.7):
        overall_status = 'healthy'
    elif healthy_services >= (total_services * 0.75):
        overall_status = 'degraded'
    else:
        overall_status = 'unhealthy'
    
    # Tạo summary
    summary = f"{healthy_services}/{total_services} services healthy, {successful_connectivity}/{connectivity_tests} connectivity tests passed"
    
    # Tạo recommendations
    recommendations = []
    
    for service, result in health_results.items():
        if not result.get('healthy', False):
            recommendations.append(f"Investigate {service} - not responding to health checks")
    
    failed_connectivity = [test for test in connectivity_results if test['status'] == 'failed']
    if failed_connectivity:
        recommendations.append(f"Check network connectivity - {len(failed_connectivity)} inter-service connections failed")
    
    if not recommendations:
        recommendations.append("All services and connectivity checks passed")
    
    return {
        'status': overall_status,
        'healthy_count': healthy_services,
        'total_count': total_services,
        'connectivity_success_rate': successful_connectivity / max(connectivity_tests, 1),
        'summary': summary,
        'recommendations': recommendations
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
    
    return base_config.get(service_name, {})

# Reuse helper functions from health_checker.py
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
        
        if service['status'] != 'ACTIVE':
            return {'healthy': False, 'reason': f"Service status: {service['status']}"}
        
        deployments = service['deployments']
        primary_deployment = next((d for d in deployments if d['status'] == 'PRIMARY'), None)
        
        if not primary_deployment:
            return {'healthy': False, 'reason': 'No primary deployment found'}
        
        running_count = primary_deployment['runningCount']
        desired_count = primary_deployment['desiredCount']
        
        if running_count < desired_count:
            return {
                'healthy': False, 
                'reason': f'Not enough running tasks: {running_count}/{desired_count}'
            }
        
        return {'healthy': True, 'running_count': running_count, 'desired_count': desired_count}
        
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
        
        response = ecs_client.describe_tasks(
            cluster=service_config['cluster_name'],
            tasks=task_arns
        )
        
        task_ips = []
        for task in response['tasks']:
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'networkInterfaceId':
                            eni_id = detail['value']
                            
                            eni_response = ec2_client.describe_network_interfaces(
                                NetworkInterfaceIds=[eni_id]
                            )
                            
                            if eni_response['NetworkInterfaces']:
                                eni = eni_response['NetworkInterfaces'][0]
                                
                                if 'Association' in eni and 'PublicIp' in eni['Association']:
                                    task_ips.append(eni['Association']['PublicIp'])
                                elif 'PrivateIpAddress' in eni:
                                    task_ips.append(eni['PrivateIpAddress'])
        
        return task_ips
    except Exception as e:
        print(f"Error getting task IPs: {str(e)}")
        return []

def check_health_endpoint(ip_address, service_config, timeout=5):
    """Kiểm tra health endpoint của một task"""
    health_url = f"http://{ip_address}:{service_config['port']}{service_config['health_path']}"
    
    try:
        response = requests.get(health_url, timeout=timeout)
        
        if response.status_code == 200:
            return {
                'ip': ip_address,
                'healthy': True,
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds()
            }
        else:
            return {
                'ip': ip_address,
                'healthy': False,
                'status_code': response.status_code,
                'reason': f'HTTP {response.status_code}'
            }
            
    except Exception as e:
        return {
            'ip': ip_address,
            'healthy': False,
            'reason': str(e)
        } 