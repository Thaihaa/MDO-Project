#!/usr/bin/env python3
"""
Dependency Manager cho Microservices Deployment Orchestration

Module này quản lý dependencies động giữa các microservices và tối ưu hóa
thứ tự deployment để có thể deploy song song khi có thể.
"""

import yaml
import json
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict, deque


@dataclass
class ServiceInfo:
    """Thông tin về một service"""
    name: str
    dependencies: List[str]
    priority: int
    parallel_group: int


class DependencyManager:
    """Class quản lý dependencies cho microservices deployment"""
    
    def __init__(self, dependencies_file: str = "config/service_dependencies.yaml"):
        """Khởi tạo dependency manager"""
        self.dependencies_file = dependencies_file
        self.config = self.load_dependencies_config()
        self.services = self._parse_services()
        
    def load_dependencies_config(self) -> Dict:
        """Load cấu hình dependencies từ YAML file"""
        try:
            with open(self.dependencies_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Error loading dependencies config: {str(e)}")
    
    def _parse_services(self) -> Dict[str, ServiceInfo]:
        """Parse thông tin services từ config"""
        services = {}
        
        for service_name, config in self.config['services'].items():
            services[service_name] = ServiceInfo(
                name=service_name,
                dependencies=config.get('dependencies', []),
                priority=config.get('priority', 1),
                parallel_group=config.get('parallel_group', 1)
            )
            
        return services
    
    def validate_dependencies(self) -> Tuple[bool, List[str]]:
        """Validate dependencies để tránh circular dependencies"""
        errors = []
        
        # Kiểm tra circular dependencies
        if self._has_circular_dependencies():
            errors.append("Circular dependencies detected")
        
        # Kiểm tra missing dependencies
        missing = self._check_missing_dependencies()
        if missing:
            errors.extend([f"Missing dependency: {dep}" for dep in missing])
        
        return len(errors) == 0, errors
    
    def _has_circular_dependencies(self) -> bool:
        """Kiểm tra circular dependencies sử dụng DFS"""
        visited = set()
        rec_stack = set()
        
        def dfs(service: str) -> bool:
            visited.add(service)
            rec_stack.add(service)
            
            if service in self.services:
                for dep in self.services[service].dependencies:
                    if dep not in visited:
                        if dfs(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            
            rec_stack.remove(service)
            return False
        
        for service in self.services:
            if service not in visited:
                if dfs(service):
                    return True
        
        return False
    
    def _check_missing_dependencies(self) -> List[str]:
        """Kiểm tra dependencies không tồn tại"""
        all_services = set(self.services.keys())
        missing = []
        
        for service in self.services.values():
            for dep in service.dependencies:
                if dep not in all_services:
                    missing.append(dep)
        
        return list(set(missing))
    
    def get_deployment_order(self, strategy: str = "parallel_optimized", 
                           services_to_deploy: Optional[List[str]] = None) -> List[List[str]]:
        """
        Tính toán thứ tự deployment cho các services
        Returns: List of deployment waves (mỗi wave có thể deploy song song)
        """
        # Validate dependencies trước
        is_valid, errors = self.validate_dependencies()
        if not is_valid:
            raise ValueError(f"Invalid dependencies: {', '.join(errors)}")
        
        # Nếu không chỉ định services, deploy tất cả
        if services_to_deploy is None:
            services_to_deploy = list(self.services.keys())
        
        # Lọc services theo input
        filtered_services = {name: info for name, info in self.services.items() 
                           if name in services_to_deploy}
        
        strategy_config = self.config['deployment_strategies'].get(strategy, {})
        allow_parallel = strategy_config.get('allow_parallel', False)
        
        if not allow_parallel or strategy == "sequential":
            return self._get_sequential_order(filtered_services)
        elif strategy == "parallel_optimized":
            return self._get_parallel_optimized_order(filtered_services)
        elif strategy == "priority_based":
            return self._get_priority_based_order(filtered_services)
        else:
            raise ValueError(f"Unknown deployment strategy: {strategy}")
    
    def _get_sequential_order(self, services: Dict[str, ServiceInfo]) -> List[List[str]]:
        """Tính deployment order tuần tự (topological sort)"""
        # Topological sort
        in_degree = {service: 0 for service in services}
        
        for service_info in services.values():
            for dep in service_info.dependencies:
                if dep in in_degree:
                    in_degree[service_info.name] += 1
        
        queue = deque([service for service, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            current = queue.popleft()
            result.append([current])  # Mỗi service một wave
            
            # Cập nhật in_degree của các services phụ thuộc current
            for service_info in services.values():
                if current in service_info.dependencies:
                    in_degree[service_info.name] -= 1
                    if in_degree[service_info.name] == 0:
                        queue.append(service_info.name)
        
        return result
    
    def _get_parallel_optimized_order(self, services: Dict[str, ServiceInfo]) -> List[List[str]]:
        """Tính deployment order với parallel optimization theo groups"""
        waves = []
        deployed = set()
        remaining = set(services.keys())
        
        while remaining:
            current_wave = []
            
            # Group services theo parallel_group
            groups = defaultdict(list)
            for service_name in remaining:
                service = services[service_name]
                # Kiểm tra dependencies đã được deploy chưa
                if all(dep in deployed or dep not in services for dep in service.dependencies):
                    groups[service.parallel_group].append(service_name)
            
            # Lấy group có priority thấp nhất (deploy trước)
            if groups:
                min_group = min(groups.keys())
                current_wave = groups[min_group]
                
                deployed.update(current_wave)
                remaining -= set(current_wave)
                waves.append(current_wave)
            else:
                # Nếu không có service nào có thể deploy, có vấn đề với dependencies
                raise ValueError(f"Cannot resolve dependencies for remaining services: {remaining}")
        
        return waves
    
    def _get_priority_based_order(self, services: Dict[str, ServiceInfo]) -> List[List[str]]:
        """Deployment theo priority, song song trong cùng priority level"""
        waves = []
        deployed = set()
        remaining = set(services.keys())
        
        while remaining:
            # Tìm services có thể deploy (dependencies đã satisfied)
            deployable = []
            for service_name in remaining:
                service = services[service_name]
                if all(dep in deployed or dep not in services for dep in service.dependencies):
                    deployable.append(service)
            
            if not deployable:
                raise ValueError(f"Cannot resolve dependencies for remaining services: {remaining}")
            
            # Group theo priority
            priority_groups = defaultdict(list)
            for service in deployable:
                priority_groups[service.priority].append(service.name)
            
            # Deploy priority thấp nhất trước
            min_priority = min(priority_groups.keys())
            current_wave = priority_groups[min_priority]
            
            deployed.update(current_wave)
            remaining -= set(current_wave)
            waves.append(current_wave)
        
        return waves
    
    def get_rollback_order(self, deployed_services: List[str]) -> List[str]:
        """Tính toán thứ tự rollback (reverse của deployment)"""
        rollback_config = self.config.get('rollback_order', [])
        
        # Lọc chỉ những services đã được deploy
        rollback_order = [service for service in rollback_config if service in deployed_services]
        
        # Thêm các services không có trong config vào cuối
        remaining = set(deployed_services) - set(rollback_order)
        rollback_order.extend(list(remaining))
        
        return rollback_order
    
    def get_health_check_dependencies(self, service: str) -> List[str]:
        """Lấy danh sách services cần health check trước khi check service này"""
        return self.config.get('health_check_dependencies', {}).get(service, [])
    
    def can_deploy_parallel(self, services: List[str]) -> bool:
        """Kiểm tra xem có thể deploy song song các services này không"""
        # Kiểm tra dependencies giữa các services trong list
        service_set = set(services)
        
        for service_name in services:
            if service_name in self.services:
                service = self.services[service_name]
                # Nếu có dependency trong cùng list, không thể deploy song song
                if any(dep in service_set for dep in service.dependencies):
                    return False
        
        return True
    
    def get_deployment_plan(self, strategy: str = "parallel_optimized", 
                           services_to_deploy: Optional[List[str]] = None) -> Dict:
        """Tạo deployment plan chi tiết"""
        waves = self.get_deployment_order(strategy, services_to_deploy)
        strategy_config = self.config['deployment_strategies'].get(strategy, {})
        
        plan = {
            "strategy": strategy,
            "total_waves": len(waves),
            "max_concurrent": strategy_config.get('max_concurrent', 1),
            "allow_parallel": strategy_config.get('allow_parallel', False),
            "waves": []
        }
        
        for i, wave in enumerate(waves):
            wave_info = {
                "wave_number": i + 1,
                "services": wave,
                "estimated_time": self._estimate_wave_time(wave),
                "dependencies_satisfied": self._check_wave_dependencies(wave, i, waves)
            }
            plan["waves"].append(wave_info)
        
        return plan
    
    def _estimate_wave_time(self, services: List[str]) -> int:
        """Ước tính thời gian deploy cho một wave (giây)"""
        # Thời gian deploy cơ bản cho mỗi service
        base_time = 60  # 1 phút
        
        # Services phức tạp hơn mất nhiều thời gian hơn
        complex_services = ['order-service', 'payment-service']
        
        max_time = base_time
        for service in services:
            service_time = base_time * 2 if service in complex_services else base_time
            max_time = max(max_time, service_time)
        
        return max_time
    
    def _check_wave_dependencies(self, wave: List[str], wave_index: int, all_waves: List[List[str]]) -> bool:
        """Kiểm tra dependencies của wave đã được satisfy chưa"""
        # Tất cả services trong các waves trước đó
        previous_services = set()
        for i in range(wave_index):
            previous_services.update(all_waves[i])
        
        # Kiểm tra từng service trong wave hiện tại
        for service_name in wave:
            if service_name in self.services:
                service = self.services[service_name]
                for dep in service.dependencies:
                    if dep in self.services and dep not in previous_services:
                        return False
        
        return True
    
    def print_deployment_plan(self, plan: Dict):
        """In deployment plan một cách đẹp"""
        print(f"\n🚀 DEPLOYMENT PLAN - Strategy: {plan['strategy']}")
        print(f"📊 Total Waves: {plan['total_waves']}")
        print(f"⚡ Max Concurrent: {plan['max_concurrent']}")
        print(f"🔄 Parallel Allowed: {plan['allow_parallel']}")
        print("="*60)
        
        for wave in plan['waves']:
            print(f"\n📦 Wave {wave['wave_number']}:")
            print(f"   Services: {', '.join(wave['services'])}")
            print(f"   Estimated Time: {wave['estimated_time']}s")
            print(f"   Dependencies OK: {'✅' if wave['dependencies_satisfied'] else '❌'}")
        
        total_estimated = sum(wave['estimated_time'] for wave in plan['waves'])
        print(f"\n⏱️  Total Estimated Time: {total_estimated}s ({total_estimated//60}m {total_estimated%60}s)")


if __name__ == "__main__":
    # Test dependency manager
    try:
        dm = DependencyManager()
        
        # Validate dependencies
        is_valid, errors = dm.validate_dependencies()
        print(f"Dependencies valid: {is_valid}")
        if errors:
            print(f"Errors: {errors}")
        
        # Test different strategies
        strategies = ["sequential", "parallel_optimized", "priority_based"]
        
        for strategy in strategies:
            print(f"\n{'='*60}")
            print(f"STRATEGY: {strategy.upper()}")
            
            plan = dm.get_deployment_plan(strategy)
            dm.print_deployment_plan(plan)
            
    except Exception as e:
        print(f"Error: {str(e)}") 