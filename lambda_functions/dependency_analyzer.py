import json
import yaml
from typing import Dict, List, Set, Tuple
from collections import defaultdict, deque

def lambda_handler(event, context):
    """
    Lambda function để phân tích dependencies và tạo deployment waves
    """
    try:
        # Lấy thông tin từ event
        services = event.get('services', [])
        deployment_context = event.get('deployment_context', {})
        strategy = event.get('strategy', 'parallel_optimized')
        
        print(f"Analyzing dependencies for {len(services)} services with strategy: {strategy}")
        
        # Load dependency configuration
        dependency_config = load_dependency_config()
        
        # Parse services và dependencies
        service_info = parse_service_dependencies(services, dependency_config)
        
        # Validate dependencies
        validation_result = validate_dependencies(service_info)
        if not validation_result['valid']:
            raise ValueError(f"Invalid dependencies: {validation_result['errors']}")
        
        # Tạo deployment waves dựa trên strategy
        if strategy == "parallel_optimized":
            waves = create_parallel_optimized_waves(service_info, dependency_config)
        elif strategy == "priority_based":
            waves = create_priority_based_waves(service_info, dependency_config)
        else:
            waves = create_sequential_waves(service_info)
        
        # Tạo detailed deployment plan
        deployment_plan = create_deployment_plan(waves, strategy, dependency_config)
        
        # Estimate deployment time
        estimated_time = estimate_total_deployment_time(deployment_plan)
        
        result = {
            "strategy": strategy,
            "total_services": len(services),
            "total_waves": len(waves),
            "deployment_waves": waves,
            "deployment_plan": deployment_plan,
            "estimated_time_seconds": estimated_time,
            "parallel_optimization": strategy != "sequential",
            "dependency_analysis": {
                "total_dependencies": sum(len(info["dependencies"]) for info in service_info.values()),
                "independent_services": len([s for s, info in service_info.items() if not info["dependencies"]]),
                "max_dependency_depth": calculate_max_dependency_depth(service_info)
            }
        }
        
        print(f"Created {len(waves)} deployment waves for {strategy} strategy")
        
        return {
            'statusCode': 200,
            'body': result
        }
        
    except Exception as e:
        print(f"Error in dependency analysis: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }

def load_dependency_config():
    """Load dependency configuration (simulated)"""
    # In thực tế, sẽ load từ S3 hoặc parameter store
    return {
        'services': {
            'auth-service': {
                'dependencies': [],
                'priority': 1,
                'parallel_group': 1,
                'estimated_deploy_time': 60
            },
            'menu-service': {
                'dependencies': ['auth-service'],
                'priority': 2,
                'parallel_group': 2,
                'estimated_deploy_time': 45
            },
            'order-service': {
                'dependencies': ['auth-service', 'menu-service'],
                'priority': 3,
                'parallel_group': 3,
                'estimated_deploy_time': 90
            },
            'payment-service': {
                'dependencies': ['auth-service'],
                'priority': 2,
                'parallel_group': 2,
                'estimated_deploy_time': 75
            },
            'notification-service': {
                'dependencies': ['auth-service'],
                'priority': 2,
                'parallel_group': 2,
                'estimated_deploy_time': 30
            },
            'analytics-service': {
                'dependencies': ['order-service', 'payment-service'],
                'priority': 4,
                'parallel_group': 4,
                'estimated_deploy_time': 60
            }
        },
        'deployment_strategies': {
            'parallel_optimized': {
                'allow_parallel': True,
                'max_concurrent_per_wave': 3
            },
            'priority_based': {
                'allow_parallel': True,
                'max_concurrent_per_wave': 2
            },
            'sequential': {
                'allow_parallel': False,
                'max_concurrent_per_wave': 1
            }
        }
    }

def parse_service_dependencies(services: List[str], config: Dict) -> Dict:
    """Parse service dependencies từ config"""
    service_info = {}
    
    for service in services:
        if service in config['services']:
            service_config = config['services'][service]
            service_info[service] = {
                'dependencies': service_config.get('dependencies', []),
                'priority': service_config.get('priority', 1),
                'parallel_group': service_config.get('parallel_group', 1),
                'estimated_deploy_time': service_config.get('estimated_deploy_time', 60)
            }
        else:
            # Default config cho services không có trong config
            service_info[service] = {
                'dependencies': [],
                'priority': 999,
                'parallel_group': 999,
                'estimated_deploy_time': 60
            }
    
    return service_info

def validate_dependencies(service_info: Dict) -> Dict:
    """Validate dependencies để tránh circular dependencies"""
    errors = []
    
    # Kiểm tra circular dependencies
    if has_circular_dependencies(service_info):
        errors.append("Circular dependencies detected")
    
    # Kiểm tra missing dependencies
    missing = check_missing_dependencies(service_info)
    if missing:
        errors.extend([f"Missing dependency: {dep}" for dep in missing])
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

def has_circular_dependencies(service_info: Dict) -> bool:
    """Kiểm tra circular dependencies sử dụng DFS"""
    visited = set()
    rec_stack = set()
    
    def dfs(service: str) -> bool:
        visited.add(service)
        rec_stack.add(service)
        
        if service in service_info:
            for dep in service_info[service]['dependencies']:
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True
        
        rec_stack.remove(service)
        return False
    
    for service in service_info:
        if service not in visited:
            if dfs(service):
                return True
    
    return False

def check_missing_dependencies(service_info: Dict) -> List[str]:
    """Kiểm tra dependencies không tồn tại"""
    all_services = set(service_info.keys())
    missing = []
    
    for service, info in service_info.items():
        for dep in info['dependencies']:
            if dep not in all_services:
                missing.append(dep)
    
    return list(set(missing))

def create_parallel_optimized_waves(service_info: Dict, config: Dict) -> List[Dict]:
    """Tạo deployment waves tối ưu cho parallel deployment"""
    waves = []
    deployed = set()
    remaining = set(service_info.keys())
    
    wave_number = 1
    
    while remaining:
        # Tìm services có thể deploy trong wave này
        current_wave_services = []
        
        # Group theo parallel_group
        groups = defaultdict(list)
        for service in remaining:
            info = service_info[service]
            # Kiểm tra dependencies đã được deploy chưa
            if all(dep in deployed or dep not in service_info for dep in info['dependencies']):
                groups[info['parallel_group']].append(service)
        
        # Lấy group có priority thấp nhất (deploy trước)
        if groups:
            min_group = min(groups.keys())
            current_wave_services = groups[min_group]
            
            # Tạo wave
            wave = {
                "wave_number": wave_number,
                "parallel_group": min_group,
                "services": current_wave_services,
                "allow_parallel": len(current_wave_services) > 1,
                "max_concurrent": min(len(current_wave_services), 
                                    config['deployment_strategies']['parallel_optimized']['max_concurrent_per_wave']),
                "estimated_time": max(service_info[s]['estimated_deploy_time'] for s in current_wave_services),
                "deployment_context": {
                    "wave_type": "parallel_optimized",
                    "dependencies_satisfied": True
                }
            }
            
            waves.append(wave)
            deployed.update(current_wave_services)
            remaining -= set(current_wave_services)
            wave_number += 1
        else:
            # Không có service nào có thể deploy
            raise ValueError(f"Cannot resolve dependencies for remaining services: {remaining}")
    
    return waves

def create_priority_based_waves(service_info: Dict, config: Dict) -> List[Dict]:
    """Tạo deployment waves theo priority"""
    waves = []
    deployed = set()
    remaining = set(service_info.keys())
    
    wave_number = 1
    
    while remaining:
        # Tìm services có thể deploy
        deployable = []
        for service in remaining:
            info = service_info[service]
            if all(dep in deployed or dep not in service_info for dep in info['dependencies']):
                deployable.append((service, info))
        
        if not deployable:
            raise ValueError(f"Cannot resolve dependencies for remaining services: {remaining}")
        
        # Group theo priority
        priority_groups = defaultdict(list)
        for service, info in deployable:
            priority_groups[info['priority']].append(service)
        
        # Deploy priority thấp nhất trước
        min_priority = min(priority_groups.keys())
        current_wave_services = priority_groups[min_priority]
        
        wave = {
            "wave_number": wave_number,
            "priority": min_priority,
            "services": current_wave_services,
            "allow_parallel": len(current_wave_services) > 1,
            "max_concurrent": min(len(current_wave_services), 
                                config['deployment_strategies']['priority_based']['max_concurrent_per_wave']),
            "estimated_time": max(service_info[s]['estimated_deploy_time'] for s in current_wave_services),
            "deployment_context": {
                "wave_type": "priority_based",
                "priority_level": min_priority
            }
        }
        
        waves.append(wave)
        deployed.update(current_wave_services)
        remaining -= set(current_wave_services)
        wave_number += 1
    
    return waves

def create_sequential_waves(service_info: Dict) -> List[Dict]:
    """Tạo deployment waves tuần tự"""
    # Topological sort
    in_degree = {service: 0 for service in service_info}
    
    for service, info in service_info.items():
        for dep in info['dependencies']:
            if dep in in_degree:
                in_degree[service] += 1
    
    queue = deque([service for service, degree in in_degree.items() if degree == 0])
    waves = []
    wave_number = 1
    
    while queue:
        current = queue.popleft()
        
        wave = {
            "wave_number": wave_number,
            "services": [current],
            "allow_parallel": False,
            "max_concurrent": 1,
            "estimated_time": service_info[current]['estimated_deploy_time'],
            "deployment_context": {
                "wave_type": "sequential"
            }
        }
        
        waves.append(wave)
        
        # Cập nhật in_degree của các services phụ thuộc current
        for service, info in service_info.items():
            if current in info['dependencies']:
                in_degree[service] -= 1
                if in_degree[service] == 0:
                    queue.append(service)
        
        wave_number += 1
    
    return waves

def create_deployment_plan(waves: List[Dict], strategy: str, config: Dict) -> Dict:
    """Tạo deployment plan chi tiết"""
    total_estimated_time = sum(wave['estimated_time'] for wave in waves)
    
    # Với parallel deployment, một số waves có thể chạy song song
    if strategy == "parallel_optimized":
        # Tính toán optimized time
        optimized_time = max(wave['estimated_time'] for wave in waves) if waves else 0
        time_savings = total_estimated_time - optimized_time
    else:
        optimized_time = total_estimated_time
        time_savings = 0
    
    return {
        "strategy": strategy,
        "total_waves": len(waves),
        "total_services": sum(len(wave['services']) for wave in waves),
        "estimated_sequential_time": total_estimated_time,
        "estimated_optimized_time": optimized_time,
        "time_savings_seconds": time_savings,
        "time_savings_percentage": (time_savings / total_estimated_time * 100) if total_estimated_time > 0 else 0,
        "parallel_efficiency": calculate_parallel_efficiency(waves),
        "waves": waves
    }

def calculate_max_dependency_depth(service_info: Dict) -> int:
    """Tính độ sâu tối đa của dependency chain"""
    def get_depth(service: str, visited: Set[str] = None) -> int:
        if visited is None:
            visited = set()
        
        if service in visited:
            return 0  # Tránh circular dependency
        
        visited.add(service)
        
        if service not in service_info or not service_info[service]['dependencies']:
            return 1
        
        max_dep_depth = 0
        for dep in service_info[service]['dependencies']:
            dep_depth = get_depth(dep, visited.copy())
            max_dep_depth = max(max_dep_depth, dep_depth)
        
        return max_dep_depth + 1
    
    return max(get_depth(service) for service in service_info.keys())

def calculate_parallel_efficiency(waves: List[Dict]) -> float:
    """Tính hiệu quả parallel deployment"""
    if not waves:
        return 0.0
    
    parallel_waves = sum(1 for wave in waves if wave.get('allow_parallel', False))
    total_waves = len(waves)
    
    # Efficiency = % waves có thể chạy parallel
    efficiency = (parallel_waves / total_waves) * 100
    
    # Bonus cho waves với nhiều services
    concurrent_bonus = sum(len(wave['services']) - 1 for wave in waves if wave.get('allow_parallel', False))
    total_services = sum(len(wave['services']) for wave in waves)
    
    if total_services > 0:
        efficiency += (concurrent_bonus / total_services) * 20  # 20% bonus max
    
    return min(efficiency, 100.0)  # Cap at 100%

def estimate_total_deployment_time(deployment_plan: Dict) -> int:
    """Ước tính tổng thời gian deployment"""
    strategy = deployment_plan['strategy']
    
    if strategy == "sequential":
        return deployment_plan['estimated_sequential_time']
    else:
        # Parallel strategies
        return deployment_plan['estimated_optimized_time'] 