#!/usr/bin/env python3
"""
Scalability Testing Framework cho Microservices Deployment Orchestrator

Framework này test hiệu năng, tải và khả năng scale của hệ thống deployment.
"""

import asyncio
import time
import json
import statistics
import boto3
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import click
import yaml
from tabulate import tabulate
import threading


@dataclass
class TestResult:
    """Kết quả của một test case"""
    test_name: str
    start_time: datetime
    end_time: datetime
    duration: float
    success: bool
    error_message: Optional[str] = None
    metrics: Dict = None


@dataclass
class LoadTestConfig:
    """Cấu hình cho load testing"""
    concurrent_deployments: int
    total_deployments: int
    deployment_interval: float  # seconds
    timeout_per_deployment: int  # seconds
    services_per_deployment: List[str]
    environment: str = "load-test"


class ScalabilityTester:
    """Class chính cho scalability testing"""
    
    def __init__(self, config_file: str = "config/aws_config.yaml"):
        """Khởi tạo scalability tester"""
        self.config = self.load_config(config_file)
        self.setup_aws_clients()
        self.test_results: List[TestResult] = []
        
    def load_config(self, config_file: str) -> Dict:
        """Load AWS config"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"Error loading config: {str(e)}")
    
    def setup_aws_clients(self):
        """Setup AWS clients"""
        try:
            session = boto3.Session(
                profile_name=self.config['aws'].get('profile', 'default'),
                region_name=self.config['aws']['region']
            )
            
            self.stepfunctions_client = session.client('stepfunctions')
            self.cloudwatch_client = session.client('cloudwatch')
            self.lambda_client = session.client('lambda')
            
            print("✅ AWS clients initialized for scalability testing")
            
        except Exception as e:
            raise Exception(f"Error setting up AWS clients: {str(e)}")
    
    def get_state_machine_arn(self) -> str:
        """Lấy ARN của state machine"""
        state_machine_name = self.config['step_functions']['state_machine_name']
        account_id = self.get_account_id()
        region = self.config['aws']['region']
        
        return f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"
    
    def get_account_id(self) -> str:
        """Lấy AWS Account ID"""
        try:
            sts_client = boto3.client('sts')
            response = sts_client.get_caller_identity()
            return response['Account']
        except Exception:
            return "123456789012"  # Fallback
    
    def run_performance_baseline_test(self) -> TestResult:
        """Test hiệu năng cơ bản với 1 deployment"""
        test_name = "Performance Baseline"
        start_time = datetime.now(timezone.utc)
        
        try:
            print(f"🏃 Running {test_name}...")
            
            # Single deployment
            execution_input = {
                "environment": "performance-test",
                "version": "baseline-test",
                "services": ["auth-service"],
                "timestamp": start_time.isoformat(),
                "test_mode": True
            }
            
            response = self.stepfunctions_client.start_execution(
                stateMachineArn=self.get_state_machine_arn(),
                name=f"perf-baseline-{int(time.time())}",
                input=json.dumps(execution_input)
            )
            
            execution_arn = response['executionArn']
            
            # Đợi hoàn thành
            result = self._wait_for_execution(execution_arn, timeout=300)
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            success = result['status'] == 'SUCCEEDED'
            
            metrics = {
                "execution_arn": execution_arn,
                "execution_time": duration,
                "status": result['status']
            }
            
            return TestResult(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=success,
                metrics=metrics
            )
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            return TestResult(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=False,
                error_message=str(e)
            )
    
    def run_concurrent_deployment_test(self, concurrent_count: int = 5) -> TestResult:
        """Test concurrent deployments"""
        test_name = f"Concurrent Deployments (x{concurrent_count})"
        start_time = datetime.now(timezone.utc)
        
        try:
            print(f"⚡ Running {test_name}...")
            
            # Tạo concurrent executions
            execution_futures = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_count) as executor:
                for i in range(concurrent_count):
                    future = executor.submit(self._single_deployment_test, i)
                    execution_futures.append(future)
                
                # Đợi tất cả hoàn thành
                results = []
                for future in concurrent.futures.as_completed(execution_futures, timeout=600):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        results.append({"success": False, "error": str(e)})
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            # Phân tích kết quả
            successful = sum(1 for r in results if r.get("success", False))
            failed = len(results) - successful
            
            execution_times = [r.get("duration", 0) for r in results if r.get("success", False)]
            avg_execution_time = statistics.mean(execution_times) if execution_times else 0
            
            metrics = {
                "concurrent_count": concurrent_count,
                "total_executions": len(results),
                "successful": successful,
                "failed": failed,
                "success_rate": successful / len(results) * 100,
                "avg_execution_time": avg_execution_time,
                "max_execution_time": max(execution_times) if execution_times else 0,
                "min_execution_time": min(execution_times) if execution_times else 0
            }
            
            return TestResult(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=successful > 0,
                metrics=metrics
            )
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            return TestResult(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=False,
                error_message=str(e)
            )
    
    def _single_deployment_test(self, test_id: int) -> Dict:
        """Single deployment test cho concurrent testing"""
        try:
            start_time = datetime.now(timezone.utc)
            
            execution_input = {
                "environment": f"concurrent-test-{test_id}",
                "version": "concurrent-test",
                "services": ["auth-service"],
                "timestamp": start_time.isoformat(),
                "test_mode": True,
                "test_id": test_id
            }
            
            response = self.stepfunctions_client.start_execution(
                stateMachineArn=self.get_state_machine_arn(),
                name=f"concurrent-test-{test_id}-{int(time.time())}",
                input=json.dumps(execution_input)
            )
            
            execution_arn = response['executionArn']
            
            # Đợi hoàn thành
            result = self._wait_for_execution(execution_arn, timeout=300)
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            return {
                "success": result['status'] == 'SUCCEEDED',
                "duration": duration,
                "execution_arn": execution_arn,
                "test_id": test_id,
                "status": result['status']
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "test_id": test_id
            }
    
    def run_load_test(self, config: LoadTestConfig) -> TestResult:
        """Chạy load test với cấu hình cho trước"""
        test_name = f"Load Test ({config.concurrent_deployments} concurrent, {config.total_deployments} total)"
        start_time = datetime.now(timezone.utc)
        
        try:
            print(f"🔥 Running {test_name}...")
            
            # Phân chia deployments thành batches
            batches = []
            remaining = config.total_deployments
            
            while remaining > 0:
                batch_size = min(config.concurrent_deployments, remaining)
                batches.append(batch_size)
                remaining -= batch_size
            
            all_results = []
            
            for batch_num, batch_size in enumerate(batches):
                print(f"  🚀 Batch {batch_num + 1}: {batch_size} deployments")
                
                # Concurrent deployments trong batch
                with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
                    batch_futures = []
                    
                    for i in range(batch_size):
                        deployment_id = batch_num * config.concurrent_deployments + i
                        future = executor.submit(self._load_test_deployment, deployment_id, config)
                        batch_futures.append(future)
                    
                    # Collect results
                    for future in concurrent.futures.as_completed(batch_futures, timeout=config.timeout_per_deployment):
                        try:
                            result = future.result()
                            all_results.append(result)
                        except Exception as e:
                            all_results.append({"success": False, "error": str(e)})
                
                # Interval between batches
                if batch_num < len(batches) - 1:  # Không sleep sau batch cuối
                    time.sleep(config.deployment_interval)
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            # Phân tích kết quả
            successful = sum(1 for r in all_results if r.get("success", False))
            failed = len(all_results) - successful
            
            execution_times = [r.get("duration", 0) for r in all_results if r.get("success", False)]
            
            metrics = {
                "total_deployments": config.total_deployments,
                "concurrent_deployments": config.concurrent_deployments,
                "successful": successful,
                "failed": failed,
                "success_rate": successful / len(all_results) * 100 if all_results else 0,
                "avg_execution_time": statistics.mean(execution_times) if execution_times else 0,
                "max_execution_time": max(execution_times) if execution_times else 0,
                "min_execution_time": min(execution_times) if execution_times else 0,
                "total_test_time": duration,
                "deployments_per_minute": len(all_results) / (duration / 60) if duration > 0 else 0
            }
            
            return TestResult(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=successful > 0,
                metrics=metrics
            )
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            return TestResult(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=False,
                error_message=str(e)
            )
    
    def _load_test_deployment(self, deployment_id: int, config: LoadTestConfig) -> Dict:
        """Single deployment cho load test"""
        try:
            start_time = datetime.now(timezone.utc)
            
            execution_input = {
                "environment": config.environment,
                "version": f"load-test-{deployment_id}",
                "services": config.services_per_deployment,
                "timestamp": start_time.isoformat(),
                "test_mode": True,
                "deployment_id": deployment_id
            }
            
            response = self.stepfunctions_client.start_execution(
                stateMachineArn=self.get_state_machine_arn(),
                name=f"load-test-{deployment_id}-{int(time.time())}",
                input=json.dumps(execution_input)
            )
            
            execution_arn = response['executionArn']
            
            # Đợi hoàn thành
            result = self._wait_for_execution(execution_arn, timeout=config.timeout_per_deployment)
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            return {
                "success": result['status'] == 'SUCCEEDED',
                "duration": duration,
                "execution_arn": execution_arn,
                "deployment_id": deployment_id,
                "status": result['status']
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "deployment_id": deployment_id
            }
    
    def _wait_for_execution(self, execution_arn: str, timeout: int = 600) -> Dict:
        """Đợi execution hoàn thành"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = self.stepfunctions_client.describe_execution(
                    executionArn=execution_arn
                )
                
                status = response['status']
                
                if status in ['SUCCEEDED', 'FAILED', 'ABORTED']:
                    return {
                        'status': status,
                        'start_date': response['startDate'],
                        'stop_date': response.get('stopDate'),
                        'execution_arn': execution_arn
                    }
                
                time.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                return {
                    'status': 'ERROR',
                    'error': str(e),
                    'execution_arn': execution_arn
                }
        
        return {
            'status': 'TIMEOUT',
            'execution_arn': execution_arn
        }
    
    def run_stress_test(self, max_concurrent: int = 20, step: int = 5) -> List[TestResult]:
        """Stress test - tăng dần concurrent deployments"""
        results = []
        
        print(f"💪 Running Stress Test (up to {max_concurrent} concurrent)")
        
        for concurrent in range(step, max_concurrent + 1, step):
            print(f"\n🔄 Testing {concurrent} concurrent deployments...")
            
            result = self.run_concurrent_deployment_test(concurrent)
            results.append(result)
            
            # Break nếu success rate quá thấp
            if result.metrics and result.metrics.get('success_rate', 0) < 50:
                print(f"⚠️  Success rate dropped below 50% at {concurrent} concurrent deployments")
                break
        
        return results
    
    def run_full_test_suite(self) -> List[TestResult]:
        """Chạy toàn bộ test suite"""
        print("🧪 Running Full Scalability Test Suite")
        print("="*60)
        
        all_results = []
        
        # 1. Performance Baseline
        result = self.run_performance_baseline_test()
        all_results.append(result)
        
        # 2. Concurrent Tests
        for concurrent in [3, 5, 10]:
            result = self.run_concurrent_deployment_test(concurrent)
            all_results.append(result)
        
        # 3. Load Test
        load_config = LoadTestConfig(
            concurrent_deployments=5,
            total_deployments=20,
            deployment_interval=2.0,
            timeout_per_deployment=300,
            services_per_deployment=["auth-service"]
        )
        
        result = self.run_load_test(load_config)
        all_results.append(result)
        
        # 4. Stress Test
        stress_results = self.run_stress_test(max_concurrent=15, step=3)
        all_results.extend(stress_results)
        
        self.test_results = all_results
        return all_results
    
    def generate_report(self, results: List[TestResult] = None) -> str:
        """Tạo báo cáo scalability testing"""
        if results is None:
            results = self.test_results
        
        report = []
        report.append("="*80)
        report.append("🚀 SCALABILITY TESTING REPORT")
        report.append("="*80)
        report.append(f"Test Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        report.append(f"Total Tests: {len(results)}")
        
        successful_tests = sum(1 for r in results if r.success)
        report.append(f"Successful Tests: {successful_tests}/{len(results)} ({successful_tests/len(results)*100:.1f}%)")
        report.append("")
        
        # Test Results Table
        table_data = []
        for result in results:
            row = [
                result.test_name,
                "✅" if result.success else "❌",
                f"{result.duration:.1f}s",
                result.error_message or "N/A"
            ]
            table_data.append(row)
        
        headers = ["Test Name", "Status", "Duration", "Error"]
        table = tabulate(table_data, headers=headers, tablefmt="grid")
        report.append(table)
        report.append("")
        
        # Detailed Metrics
        report.append("📊 DETAILED METRICS")
        report.append("-" * 40)
        
        for result in results:
            if result.metrics:
                report.append(f"\n🔍 {result.test_name}:")
                for key, value in result.metrics.items():
                    if isinstance(value, float):
                        report.append(f"  {key}: {value:.2f}")
                    else:
                        report.append(f"  {key}: {value}")
        
        # Performance Summary
        report.append("\n" + "="*40)
        report.append("📈 PERFORMANCE SUMMARY")
        report.append("="*40)
        
        # Tìm baseline performance
        baseline = next((r for r in results if "Baseline" in r.test_name), None)
        if baseline and baseline.success:
            report.append(f"Baseline Execution Time: {baseline.duration:.1f}s")
        
        # Tìm max concurrent đạt được
        concurrent_tests = [r for r in results if "Concurrent" in r.test_name and r.success]
        if concurrent_tests:
            max_concurrent = max(r.metrics.get('concurrent_count', 0) for r in concurrent_tests)
            report.append(f"Max Successful Concurrent: {max_concurrent}")
        
        # Load test performance
        load_tests = [r for r in results if "Load Test" in r.test_name and r.success]
        if load_tests:
            best_load = max(load_tests, key=lambda x: x.metrics.get('deployments_per_minute', 0))
            report.append(f"Best Throughput: {best_load.metrics.get('deployments_per_minute', 0):.1f} deployments/minute")
        
        return "\n".join(report)
    
    def save_report(self, filename: str = None, results: List[TestResult] = None):
        """Lưu báo cáo ra file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scalability_report_{timestamp}.txt"
        
        report = self.generate_report(results)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"📋 Report saved to: {filename}")


# CLI Interface
@click.group()
def cli():
    """Scalability Testing CLI cho Microservices Deployment Orchestrator"""
    pass

@cli.command()
@click.option('--concurrent', '-c', default=5, help='Số concurrent deployments')
def concurrent_test(concurrent):
    """Chạy concurrent deployment test"""
    tester = ScalabilityTester()
    result = tester.run_concurrent_deployment_test(concurrent)
    
    print(f"\n📊 Test Results:")
    print(f"Success: {result.success}")
    print(f"Duration: {result.duration:.1f}s")
    if result.metrics:
        for key, value in result.metrics.items():
            print(f"{key}: {value}")

@cli.command()
@click.option('--concurrent', '-c', default=5, help='Concurrent deployments per batch')
@click.option('--total', '-t', default=20, help='Total deployments')
@click.option('--interval', '-i', default=2.0, help='Interval between batches (seconds)')
def load_test(concurrent, total, interval):
    """Chạy load test"""
    tester = ScalabilityTester()
    
    config = LoadTestConfig(
        concurrent_deployments=concurrent,
        total_deployments=total,
        deployment_interval=interval,
        timeout_per_deployment=300,
        services_per_deployment=["auth-service"]
    )
    
    result = tester.run_load_test(config)
    
    print(f"\n📊 Load Test Results:")
    print(f"Success: {result.success}")
    print(f"Duration: {result.duration:.1f}s")
    if result.metrics:
        for key, value in result.metrics.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f}")
            else:
                print(f"{key}: {value}")

@cli.command()
@click.option('--max-concurrent', '-m', default=15, help='Max concurrent deployments')
@click.option('--step', '-s', default=3, help='Step size for increasing concurrent')
def stress_test(max_concurrent, step):
    """Chạy stress test"""
    tester = ScalabilityTester()
    results = tester.run_stress_test(max_concurrent, step)
    
    print(f"\n📊 Stress Test Results:")
    for result in results:
        status = "✅" if result.success else "❌"
        print(f"{result.test_name}: {status} ({result.duration:.1f}s)")

@cli.command()
@click.option('--save', '-s', is_flag=True, help='Lưu báo cáo ra file')
def full_suite(save):
    """Chạy toàn bộ test suite"""
    tester = ScalabilityTester()
    results = tester.run_full_test_suite()
    
    # In báo cáo
    report = tester.generate_report(results)
    print(report)
    
    # Lưu file nếu được yêu cầu
    if save:
        tester.save_report()

if __name__ == "__main__":
    cli() 