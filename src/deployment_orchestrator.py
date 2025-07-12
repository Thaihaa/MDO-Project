#!/usr/bin/env python3
"""
Restaurant Microservices Deployment Orchestrator

Script này cho phép tương tác với AWS Step Functions để quản lý deployment
của các microservices trong hệ thống restaurant.
"""

import json
import boto3
import time
import yaml
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional
import click
from tabulate import tabulate
from colorama import Fore, Back, Style, init
from dependency_manager import DependencyManager

# Khởi tạo colorama
init(autoreset=True)

class DeploymentOrchestrator:
    """Class chính để quản lý deployment orchestration"""
    
    def __init__(self, config_file: str = "config/aws_config.yaml"):
        """Khởi tạo orchestrator với config file"""
        self.config = self.load_config(config_file)
        self.setup_aws_clients()
        # Khởi tạo dependency manager
        self.dependency_manager = DependencyManager()
        
    def load_config(self, config_file: str) -> Dict:
        """Load cấu hình từ YAML file"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Thay thế placeholders với values thực tế
            account_id = self.get_account_id()
            region = config['aws']['region']
            
            # Update ARNs với account ID và region thực tế
            if 'step_functions' in config:
                execution_role = config['step_functions']['execution_role_arn']
                config['step_functions']['execution_role_arn'] = execution_role.format(
                    account_id=account_id
                )
            
            if 'monitoring' in config:
                notification_topic = config['monitoring']['notification_topic_arn']
                config['monitoring']['notification_topic_arn'] = notification_topic.format(
                    region=region, account_id=account_id
                )
                
            return config
            
        except Exception as e:
            self.print_error(f"Lỗi load config: {str(e)}")
            sys.exit(1)
    
    def get_account_id(self) -> str:
        """Lấy AWS Account ID"""
        try:
            sts_client = boto3.client('sts')
            response = sts_client.get_caller_identity()
            return response['Account']
        except Exception as e:
            self.print_error(f"Không thể lấy Account ID: {str(e)}")
            return "123456789012"  # Default fallback
    
    def setup_aws_clients(self):
        """Khởi tạo AWS clients"""
        try:
            session = boto3.Session(
                profile_name=self.config['aws'].get('profile', 'default'),
                region_name=self.config['aws']['region']
            )
            
            self.stepfunctions_client = session.client('stepfunctions')
            self.ecs_client = session.client('ecs')
            self.cloudwatch_client = session.client('cloudwatch')
            self.logs_client = session.client('logs')
            
            self.print_success("AWS clients đã được khởi tạo thành công")
            
        except Exception as e:
            self.print_error(f"Lỗi khởi tạo AWS clients: {str(e)}")
            sys.exit(1)
    
    def create_state_machine(self) -> str:
        """Tạo hoặc cập nhật Step Functions state machine"""
        try:
            # Load state machine definition
            definition_file = "step_functions/restaurant_deployment_orchestrator.json"
            with open(definition_file, 'r') as f:
                definition = f.read()
            
            state_machine_name = self.config['step_functions']['state_machine_name']
            execution_role_arn = self.config['step_functions']['execution_role_arn']
            
            try:
                # Thử cập nhật state machine nếu đã tồn tại
                response = self.stepfunctions_client.update_state_machine(
                    stateMachineArn=self.get_state_machine_arn(),
                    definition=definition,
                    roleArn=execution_role_arn
                )
                
                self.print_success(f"Đã cập nhật state machine: {state_machine_name}")
                return response['stateMachineArn']
                
            except self.stepfunctions_client.exceptions.StateMachineDoesNotExist:
                # Tạo mới nếu chưa tồn tại
                response = self.stepfunctions_client.create_state_machine(
                    name=state_machine_name,
                    definition=definition,
                    roleArn=execution_role_arn,
                    type='STANDARD',
                    loggingConfiguration={
                        'level': 'ALL',
                        'includeExecutionData': True,
                        'destinations': [
                            {
                                'cloudWatchLogsLogGroup': {
                                    'logGroupArn': f"arn:aws:logs:{self.config['aws']['region']}:{self.get_account_id()}:log-group:{self.config['monitoring']['cloudwatch_log_group']}:*"
                                }
                            }
                        ]
                    }
                )
                
                self.print_success(f"Đã tạo state machine mới: {state_machine_name}")
                return response['stateMachineArn']
                
        except Exception as e:
            self.print_error(f"Lỗi tạo/cập nhật state machine: {str(e)}")
            raise
    
    def get_state_machine_arn(self) -> str:
        """Lấy ARN của state machine"""
        state_machine_name = self.config['step_functions']['state_machine_name']
        account_id = self.get_account_id()
        region = self.config['aws']['region']
        
        return f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"
    
    def start_deployment(self, environment: str = "staging", version: str = "latest", 
                        services: Optional[List[str]] = None) -> Dict:
        """Bắt đầu deployment mới"""
        try:
            self.print_info(f"Bắt đầu deployment - Environment: {environment}, Version: {version}")
            
            # Tạo input cho Step Functions
            execution_input = {
                "environment": environment,
                "version": version,
                "region": self.config['aws']['region'],
                "services": services or ["auth-service", "menu-service", "order-service", "payment-service"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Bắt đầu execution
            response = self.stepfunctions_client.start_execution(
                stateMachineArn=self.get_state_machine_arn(),
                name=f"deployment-{int(time.time())}",
                input=json.dumps(execution_input)
            )
            
            execution_arn = response['executionArn']
            
            self.print_success(f"Deployment đã được bắt đầu!")
            self.print_info(f"Execution ARN: {execution_arn}")
            
            return {
                'execution_arn': execution_arn,
                'input': execution_input,
                'start_time': response['startDate']
            }
            
        except Exception as e:
            self.print_error(f"Lỗi bắt đầu deployment: {str(e)}")
            raise
    
    def start_smart_deployment(self, environment: str = "staging", version: str = "latest", 
                              services: Optional[List[str]] = None, 
                              strategy: str = "parallel_optimized") -> Dict:
        """Bắt đầu deployment với dynamic dependency management"""
        try:
            self.print_info(f"🚀 Bắt đầu Smart Deployment - Strategy: {strategy}")
            self.print_info(f"Environment: {environment}, Version: {version}")
            
            # Validate dependencies
            is_valid, errors = self.dependency_manager.validate_dependencies()
            if not is_valid:
                raise ValueError(f"Invalid dependencies: {', '.join(errors)}")
            
            # Tạo deployment plan
            deployment_plan = self.dependency_manager.get_deployment_plan(
                strategy=strategy,
                services_to_deploy=services
            )
            
            # In deployment plan
            self.dependency_manager.print_deployment_plan(deployment_plan)
            
            # Bắt đầu deployment theo waves
            all_execution_arns = []
            wave_results = []
            
            for wave_info in deployment_plan["waves"]:
                wave_number = wave_info["wave_number"]
                wave_services = wave_info["services"]
                
                self.print_info(f"🌊 Deploying Wave {wave_number}: {', '.join(wave_services)}")
                
                if deployment_plan["allow_parallel"] and len(wave_services) > 1:
                    # Deploy song song các services trong wave
                    wave_executions = self._deploy_wave_parallel(
                        wave_services, environment, version, wave_number
                    )
                else:
                    # Deploy tuần tự
                    wave_executions = self._deploy_wave_sequential(
                        wave_services, environment, version, wave_number
                    )
                
                wave_results.append({
                    "wave": wave_number,
                    "services": wave_services,
                    "executions": wave_executions
                })
                all_execution_arns.extend(wave_executions)
            
            self.print_success(f"✅ Smart Deployment initiated với {len(wave_results)} waves!")
            
            return {
                "deployment_plan": deployment_plan,
                "wave_results": wave_results,
                "all_executions": all_execution_arns,
                "strategy": strategy
            }
            
        except Exception as e:
            self.print_error(f"Lỗi Smart Deployment: {str(e)}")
            raise
    
    def _deploy_wave_parallel(self, services: List[str], environment: str, 
                             version: str, wave_number: int) -> List[str]:
        """Deploy các services trong wave song song"""
        self.print_info(f"⚡ Parallel deployment Wave {wave_number}")
        
        # Tạo các executions song song
        executions = []
        for service in services:
            execution_input = {
                "environment": environment,
                "version": version,
                "services": [service],  # Deploy từng service riêng
                "wave_number": wave_number,
                "deployment_mode": "parallel",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            response = self.stepfunctions_client.start_execution(
                stateMachineArn=self.get_state_machine_arn(),
                name=f"wave-{wave_number}-{service}-{int(time.time())}",
                input=json.dumps(execution_input)
            )
            
            executions.append(response['executionArn'])
            self.print_success(f"  ✅ Started {service}: {response['executionArn']}")
        
        return executions
    
    def _deploy_wave_sequential(self, services: List[str], environment: str, 
                               version: str, wave_number: int) -> List[str]:
        """Deploy các services trong wave tuần tự"""
        self.print_info(f"🔄 Sequential deployment Wave {wave_number}")
        
        executions = []
        for service in services:
            execution_input = {
                "environment": environment,
                "version": version,
                "services": [service],
                "wave_number": wave_number,
                "deployment_mode": "sequential",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            response = self.stepfunctions_client.start_execution(
                stateMachineArn=self.get_state_machine_arn(),
                name=f"wave-{wave_number}-{service}-{int(time.time())}",
                input=json.dumps(execution_input)
            )
            
            execution_arn = response['executionArn']
            executions.append(execution_arn)
            
            self.print_success(f"  ✅ Started {service}: {execution_arn}")
            
            # Đợi service này hoàn thành trước khi deploy service tiếp theo
            if len(services) > 1:  # Chỉ wait nếu có nhiều hơn 1 service
                self.print_info(f"  ⏳ Waiting for {service} to complete...")
                final_status = self.wait_for_execution_completion(execution_arn, timeout=600)
                
                if final_status['status'] != 'SUCCEEDED':
                    raise Exception(f"Service {service} deployment failed: {final_status['status']}")
                
                self.print_success(f"  ✅ {service} completed successfully")
        
        return executions
    
    def get_execution_status(self, execution_arn: str) -> Dict:
        """Lấy trạng thái của execution"""
        try:
            response = self.stepfunctions_client.describe_execution(
                executionArn=execution_arn
            )
            
            return {
                'status': response['status'],
                'start_date': response['startDate'],
                'stop_date': response.get('stopDate'),
                'input': json.loads(response['input']) if response['input'] else {},
                'output': json.loads(response['output']) if response.get('output') else {},
                'execution_arn': response['executionArn']
            }
            
        except Exception as e:
            self.print_error(f"Lỗi lấy execution status: {str(e)}")
            raise
    
    def wait_for_execution_completion(self, execution_arn: str, timeout: int = 1800) -> Dict:
        """Chờ execution hoàn thành với progress tracking"""
        start_time = time.time()
        last_status = None
        
        self.print_info("Đang theo dõi tiến trình deployment...")
        
        while time.time() - start_time < timeout:
            try:
                status_info = self.get_execution_status(execution_arn)
                current_status = status_info['status']
                
                # In ra thay đổi status
                if current_status != last_status:
                    self.print_status_update(current_status)
                    last_status = current_status
                
                # Kiểm tra nếu đã hoàn thành
                if current_status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                    return status_info
                
                # Lấy và hiển thị events mới nhất
                self.show_recent_events(execution_arn)
                
                time.sleep(30)  # Check mỗi 30 giây
                
            except Exception as e:
                self.print_error(f"Lỗi theo dõi execution: {str(e)}")
                time.sleep(10)
        
        self.print_warning(f"Timeout sau {timeout} giây")
        return self.get_execution_status(execution_arn)
    
    def show_recent_events(self, execution_arn: str, max_events: int = 5):
        """Hiển thị events gần nhất của execution"""
        try:
            response = self.stepfunctions_client.get_execution_history(
                executionArn=execution_arn,
                maxResults=max_events,
                reverseOrder=True
            )
            
            events = response['events']
            if events:
                print(f"\n{Fore.CYAN}📊 Events gần nhất:")
                for event in reversed(events[-3:]):  # Hiển thị 3 events gần nhất
                    timestamp = event['timestamp'].strftime('%H:%M:%S')
                    event_type = event['type']
                    
                    if 'StateEntered' in event_type:
                        state_name = event['stateEnteredEventDetails']['name']
                        print(f"  {Fore.GREEN}✓ {timestamp} - Đang thực hiện: {state_name}")
                    elif 'StateExited' in event_type:
                        state_name = event['stateExitedEventDetails']['name']
                        print(f"  {Fore.BLUE}✓ {timestamp} - Hoàn thành: {state_name}")
                    elif 'Failed' in event_type:
                        print(f"  {Fore.RED}✗ {timestamp} - Lỗi: {event_type}")
                        
        except Exception as e:
            pass  # Không hiển thị lỗi cho events
    
    def list_recent_executions(self, limit: int = 10) -> List[Dict]:
        """Liệt kê các executions gần nhất"""
        try:
            response = self.stepfunctions_client.list_executions(
                stateMachineArn=self.get_state_machine_arn(),
                maxResults=limit
            )
            
            executions = []
            for execution in response['executions']:
                executions.append({
                    'name': execution['name'],
                    'status': execution['status'],
                    'start_date': execution['startDate'],
                    'stop_date': execution.get('stopDate'),
                    'execution_arn': execution['executionArn']
                })
            
            return executions
            
        except Exception as e:
            self.print_error(f"Lỗi lấy danh sách executions: {str(e)}")
            return []
    
    def stop_execution(self, execution_arn: str, error: str = "Manual stop", 
                      cause: str = "Stopped by user") -> bool:
        """Dừng execution đang chạy"""
        try:
            self.stepfunctions_client.stop_execution(
                executionArn=execution_arn,
                error=error,
                cause=cause
            )
            
            self.print_success(f"Đã dừng execution: {execution_arn}")
            return True
            
        except Exception as e:
            self.print_error(f"Lỗi dừng execution: {str(e)}")
            return False
    
    def get_service_health_status(self, environment: str = "staging") -> Dict:
        """Lấy trạng thái health của các services"""
        try:
            services_status = {}
            
            for service_name, config in self.config['microservices'].items():
                service_status = self.check_individual_service_health(
                    service_name, 
                    environment,
                    config
                )
                services_status[service_name] = service_status
            
            return services_status
            
        except Exception as e:
            self.print_error(f"Lỗi lấy service health status: {str(e)}")
            return {}
    
    def check_individual_service_health(self, service_name: str, environment: str, 
                                       config: Dict) -> Dict:
        """Kiểm tra health của một service"""
        try:
            cluster_name = f"restaurant-{environment}"
            service_name_full = f"{service_name}-{environment}"
            
            # Lấy thông tin service từ ECS
            response = self.ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name_full]
            )
            
            if not response['services']:
                return {'status': 'NOT_FOUND', 'message': 'Service not found in ECS'}
            
            service = response['services'][0]
            
            # Phân tích deployment status
            primary_deployment = next(
                (d for d in service['deployments'] if d['status'] == 'PRIMARY'),
                None
            )
            
            if not primary_deployment:
                return {'status': 'NO_PRIMARY_DEPLOYMENT'}
            
            running_count = primary_deployment['runningCount']
            desired_count = primary_deployment['desiredCount']
            
            if running_count == desired_count and service['status'] == 'ACTIVE':
                status = 'HEALTHY'
            elif running_count > 0:
                status = 'DEGRADED'
            else:
                status = 'UNHEALTHY'
            
            return {
                'status': status,
                'running_count': running_count,
                'desired_count': desired_count,
                'service_status': service['status'],
                'task_definition': service['taskDefinition']
            }
            
        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}
    
    # Utility methods for colored output
    def print_success(self, message: str):
        """In thông báo thành công"""
        print(f"{Fore.GREEN}✅ {message}{Style.RESET_ALL}")
    
    def print_error(self, message: str):
        """In thông báo lỗi"""
        print(f"{Fore.RED}❌ {message}{Style.RESET_ALL}")
    
    def print_warning(self, message: str):
        """In thông báo cảnh báo"""
        print(f"{Fore.YELLOW}⚠️  {message}{Style.RESET_ALL}")
    
    def print_info(self, message: str):
        """In thông tin"""
        print(f"{Fore.BLUE}ℹ️  {message}{Style.RESET_ALL}")
    
    def print_status_update(self, status: str):
        """In cập nhật trạng thái"""
        if status == 'RUNNING':
            print(f"{Fore.CYAN}🔄 Status: ĐANG CHẠY")
        elif status == 'SUCCEEDED':
            print(f"{Fore.GREEN}✅ Status: THÀNH CÔNG")
        elif status == 'FAILED':
            print(f"{Fore.RED}❌ Status: THẤT BẠI")
        elif status == 'TIMED_OUT':
            print(f"{Fore.YELLOW}⏰ Status: TIMEOUT")
        else:
            print(f"{Fore.MAGENTA}📊 Status: {status}")

# CLI Interface sử dụng Click
@click.group()
@click.pass_context
def cli(ctx):
    """Restaurant Microservices Deployment Orchestrator
    
    Tool để quản lý deployment của microservices qua AWS Step Functions
    """
    ctx.ensure_object(dict)
    ctx.obj['orchestrator'] = DeploymentOrchestrator()

@cli.command()
@click.option('--environment', '-e', default='staging', 
              help='Environment để deploy (staging/production)')
@click.option('--version', '-v', default='latest', 
              help='Version của services để deploy')
@click.option('--services', '-s', multiple=True, 
              help='Specific services để deploy (có thể dùng nhiều lần)')
@click.option('--wait', '-w', is_flag=True, 
              help='Chờ deployment hoàn thành')
@click.pass_context
def deploy(ctx, environment, version, services, wait):
    """Bắt đầu deployment mới"""
    orchestrator = ctx.obj['orchestrator']
    
    try:
        # Convert services tuple to list
        services_list = list(services) if services else None
        
        # Bắt đầu deployment
        result = orchestrator.start_deployment(environment, version, services_list)
        
        if wait:
            # Chờ hoàn thành
            final_status = orchestrator.wait_for_execution_completion(
                result['execution_arn']
            )
            
            if final_status['status'] == 'SUCCEEDED':
                orchestrator.print_success("🎉 Deployment hoàn thành thành công!")
            else:
                orchestrator.print_error(f"💥 Deployment thất bại: {final_status['status']}")
                if 'output' in final_status and final_status['output']:
                    print(json.dumps(final_status['output'], indent=2, ensure_ascii=False))
        
    except Exception as e:
        orchestrator.print_error(f"Deployment thất bại: {str(e)}")
        sys.exit(1)

@cli.command()
@click.option('--environment', '-e', default='staging', 
              help='Environment để deploy (staging/production)')
@click.option('--version', '-v', default='latest', 
              help='Version của services để deploy')
@click.option('--services', '-s', multiple=True, 
              help='Specific services để deploy (có thể dùng nhiều lần)')
@click.option('--strategy', default='parallel_optimized',
              type=click.Choice(['sequential', 'parallel_optimized', 'priority_based']),
              help='Deployment strategy')
@click.option('--wait', '-w', is_flag=True, 
              help='Chờ deployment hoàn thành')
@click.pass_context
def smart_deploy(ctx, environment, version, services, strategy, wait):
    """Smart deployment với dynamic dependency management"""
    orchestrator = ctx.obj['orchestrator']
    
    try:
        # Convert services tuple to list
        services_list = list(services) if services else None
        
        # Bắt đầu smart deployment
        result = orchestrator.start_smart_deployment(environment, version, services_list, strategy)
        
        if wait:
            orchestrator.print_info("⏳ Waiting for all waves to complete...")
            
            failed_executions = []
            successful_executions = []
            
            # Monitor tất cả executions
            for execution_arn in result["all_executions"]:
                try:
                    final_status = orchestrator.wait_for_execution_completion(execution_arn, timeout=1800)
                    
                    if final_status['status'] == 'SUCCEEDED':
                        successful_executions.append(execution_arn)
                        orchestrator.print_success(f"✅ Execution completed: {execution_arn}")
                    else:
                        failed_executions.append(execution_arn)
                        orchestrator.print_error(f"❌ Execution failed: {execution_arn}")
                        
                except Exception as e:
                    failed_executions.append(execution_arn)
                    orchestrator.print_error(f"❌ Error monitoring {execution_arn}: {str(e)}")
            
            # Summary
            total = len(result["all_executions"])
            success_count = len(successful_executions)
            failed_count = len(failed_executions)
            
            orchestrator.print_info(f"\n📊 DEPLOYMENT SUMMARY:")
            orchestrator.print_info(f"  Total Executions: {total}")
            orchestrator.print_success(f"  Successful: {success_count}")
            if failed_count > 0:
                orchestrator.print_error(f"  Failed: {failed_count}")
            
            if failed_count == 0:
                orchestrator.print_success("🎉 Smart Deployment hoàn thành thành công!")
            else:
                orchestrator.print_error("💥 Smart Deployment có lỗi xảy ra!")
                sys.exit(1)
        
    except Exception as e:
        orchestrator.print_error(f"Smart Deployment thất bại: {str(e)}")
        sys.exit(1)

@cli.command()
@click.option('--limit', '-l', default=10, help='Số lượng executions hiển thị')
@click.pass_context
def list_executions(ctx, limit):
    """Liệt kê các executions gần nhất"""
    orchestrator = ctx.obj['orchestrator']
    
    try:
        executions = orchestrator.list_recent_executions(limit)
        
        if not executions:
            orchestrator.print_info("Không có executions nào")
            return
        
        # Tạo bảng hiển thị
        table_data = []
        for execution in executions:
            start_time = execution['start_date'].strftime('%Y-%m-%d %H:%M:%S')
            duration = ""
            
            if execution.get('stop_date'):
                duration_seconds = (execution['stop_date'] - execution['start_date']).total_seconds()
                duration = f"{duration_seconds:.0f}s"
            
            # Tô màu status
            status = execution['status']
            if status == 'SUCCEEDED':
                status = f"{Fore.GREEN}{status}{Style.RESET_ALL}"
            elif status == 'FAILED':
                status = f"{Fore.RED}{status}{Style.RESET_ALL}"
            elif status == 'RUNNING':
                status = f"{Fore.CYAN}{status}{Style.RESET_ALL}"
            
            table_data.append([
                execution['name'],
                status,
                start_time,
                duration
            ])
        
        headers = ['Name', 'Status', 'Start Time', 'Duration']
        print(f"\n{Fore.CYAN}📋 Recent Executions:")
        print(tabulate(table_data, headers=headers, tablefmt='grid'))
        
    except Exception as e:
        orchestrator.print_error(f"Lỗi lấy danh sách executions: {str(e)}")

@cli.command()
@click.option('--execution-arn', '-e', help='ARN của execution cụ thể để kiểm tra')
@click.pass_context  
def status(ctx, execution_arn):
    """Kiểm tra trạng thái deployment hoặc execution cụ thể"""
    orchestrator = ctx.obj['orchestrator']
    
    try:
        if execution_arn:
            # Kiểm tra execution cụ thể
            status_info = orchestrator.get_execution_status(execution_arn)
            
            print(f"\n{Fore.CYAN}📊 Execution Status:")
            print(f"Status: {status_info['status']}")
            print(f"Start Date: {status_info['start_date']}")
            
            if status_info.get('stop_date'):
                print(f"Stop Date: {status_info['stop_date']}")
                duration = (status_info['stop_date'] - status_info['start_date']).total_seconds()
                print(f"Duration: {duration:.0f} seconds")
            
            if status_info.get('input'):
                print(f"\n{Fore.BLUE}📥 Input:")
                print(json.dumps(status_info['input'], indent=2, ensure_ascii=False))
            
            if status_info.get('output'):
                print(f"\n{Fore.GREEN}📤 Output:")
                print(json.dumps(status_info['output'], indent=2, ensure_ascii=False))
        else:
            # Hiển thị status tổng quát
            orchestrator.print_info("📊 Deployment System Status")
            
            # Hiển thị recent executions
            executions = orchestrator.list_recent_executions(5)
            
            if executions:
                print(f"\n{Fore.CYAN}📋 Recent Executions:")
                table_data = []
                for execution in executions:
                    start_time = execution['start_date'].strftime('%Y-%m-%d %H:%M:%S')
                    duration = ""
                    
                    if execution.get('stop_date'):
                        duration_seconds = (execution['stop_date'] - execution['start_date']).total_seconds()
                        duration = f"{duration_seconds:.0f}s"
                    
                    # Tô màu status
                    status = execution['status']
                    if status == 'SUCCEEDED':
                        status = f"{Fore.GREEN}{status}{Style.RESET_ALL}"
                    elif status == 'FAILED':
                        status = f"{Fore.RED}{status}{Style.RESET_ALL}"
                    elif status == 'RUNNING':
                        status = f"{Fore.CYAN}{status}{Style.RESET_ALL}"
                    
                    table_data.append([
                        execution['name'],
                        status,
                        start_time,
                        duration
                    ])
                
                headers = ['Name', 'Status', 'Start Time', 'Duration']
                print(tabulate(table_data, headers=headers, tablefmt='grid'))
            else:
                orchestrator.print_info("Không có executions nào")
        
    except Exception as e:
        orchestrator.print_error(f"Lỗi lấy status: {str(e)}")

@cli.command()
@click.option('--environment', '-e', default='staging', 
              help='Environment để kiểm tra')
@click.pass_context
def health(ctx, environment):
    """Kiểm tra health của các services"""
    orchestrator = ctx.obj['orchestrator']
    
    try:
        services_status = orchestrator.get_service_health_status(environment)
        
        if not services_status:
            orchestrator.print_warning("Không thể lấy service health status")
            return
        
        print(f"\n{Fore.CYAN}🏥 Service Health Status - Environment: {environment}")
        
        table_data = []
        for service_name, status_info in services_status.items():
            status = status_info.get('status', 'UNKNOWN')
            
            # Tô màu status
            if status == 'HEALTHY':
                colored_status = f"{Fore.GREEN}{status}{Style.RESET_ALL}"
            elif status == 'DEGRADED':
                colored_status = f"{Fore.YELLOW}{status}{Style.RESET_ALL}"
            elif status == 'UNHEALTHY':
                colored_status = f"{Fore.RED}{status}{Style.RESET_ALL}"
            else:
                colored_status = f"{Fore.WHITE}{status}{Style.RESET_ALL}"
            
            running = status_info.get('running_count', 'N/A')
            desired = status_info.get('desired_count', 'N/A')
            tasks = f"{running}/{desired}" if running != 'N/A' else 'N/A'
            
            table_data.append([
                service_name,
                colored_status,
                tasks,
                status_info.get('service_status', 'N/A')
            ])
        
        headers = ['Service', 'Health', 'Tasks', 'ECS Status']
        print(tabulate(table_data, headers=headers, tablefmt='grid'))
        
    except Exception as e:
        orchestrator.print_error(f"Lỗi kiểm tra health: {str(e)}")

@cli.command()
@click.argument('execution_arn')
@click.pass_context
def stop(ctx, execution_arn):
    """Dừng execution đang chạy"""
    orchestrator = ctx.obj['orchestrator']
    
    try:
        success = orchestrator.stop_execution(execution_arn)
        if success:
            orchestrator.print_success("Execution đã được dừng")
        else:
            orchestrator.print_error("Không thể dừng execution")
    
    except Exception as e:
        orchestrator.print_error(f"Lỗi dừng execution: {str(e)}")

@cli.command()
@click.pass_context
def setup(ctx):
    """Setup Step Functions state machine"""
    orchestrator = ctx.obj['orchestrator']
    
    try:
        orchestrator.print_info("Đang setup Step Functions state machine...")
        state_machine_arn = orchestrator.create_state_machine()
        orchestrator.print_success(f"Setup hoàn thành: {state_machine_arn}")
        
    except Exception as e:
        orchestrator.print_error(f"Setup thất bại: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    cli() 