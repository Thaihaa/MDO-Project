#!/usr/bin/env python3
"""
Restaurant Microservices Deployment Dashboard

Dashboard để monitor deployments và hiển thị thông tin real-time về các services.
"""

import json
import boto3
import time
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import yaml
import click
from tabulate import tabulate
from colorama import Fore, Back, Style, init
import threading
import subprocess

# Khởi tạo colorama
init(autoreset=True)

class DeploymentDashboard:
    """Dashboard để monitor deployments"""
    
    def __init__(self, config_file: str = "config/aws_config.yaml"):
        """Khởi tạo dashboard"""
        self.config = self.load_config(config_file)
        self.setup_aws_clients()
        self.running = False
        
    def load_config(self, config_file: str) -> Dict:
        """Load cấu hình từ YAML file"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Lỗi load config: {str(e)}")
            sys.exit(1)
    
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
            self.sns_client = session.client('sns')
            
        except Exception as e:
            print(f"Lỗi khởi tạo AWS clients: {str(e)}")
            sys.exit(1)
    
    def get_account_id(self) -> str:
        """Lấy AWS Account ID"""
        try:
            sts_client = boto3.client('sts')
            response = sts_client.get_caller_identity()
            return response['Account']
        except Exception:
            return "123456789012"  # Default fallback
    
    def get_state_machine_arn(self) -> str:
        """Lấy ARN của state machine"""
        state_machine_name = self.config['step_functions']['state_machine_name']
        account_id = self.get_account_id()
        region = self.config['aws']['region']
        
        return f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"
    
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self):
        """In header của dashboard"""
        print(f"{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}🚀 RESTAURANT MICROSERVICES DEPLOYMENT DASHBOARD 🚀")
        print(f"{Fore.CYAN}{'='*80}")
        print(f"{Fore.WHITE}Region: {self.config['aws']['region']} | "
              f"Account: {self.get_account_id()} | "
              f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Fore.CYAN}{'='*80}")
    
    def get_active_executions(self) -> List[Dict]:
        """Lấy danh sách executions đang active"""
        try:
            response = self.stepfunctions_client.list_executions(
                stateMachineArn=self.get_state_machine_arn(),
                statusFilter='RUNNING',
                maxResults=10
            )
            
            executions = []
            for execution in response['executions']:
                executions.append({
                    'name': execution['name'],
                    'status': execution['status'],
                    'start_date': execution['startDate'],
                    'execution_arn': execution['executionArn']
                })
            
            return executions
            
        except Exception as e:
            print(f"Lỗi lấy active executions: {str(e)}")
            return []
    
    def get_recent_executions(self, limit: int = 5) -> List[Dict]:
        """Lấy recent executions (cả thành công và thất bại)"""
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
            return []
    
    def get_services_status(self, environment: str = "staging") -> Dict:
        """Lấy trạng thái của tất cả services"""
        services_status = {}
        
        for service_name, config in self.config['microservices'].items():
            try:
                cluster_name = f"restaurant-{environment}"
                service_name_full = f"{service_name}-{environment}"
                
                response = self.ecs_client.describe_services(
                    cluster=cluster_name,
                    services=[service_name_full]
                )
                
                if response['services']:
                    service = response['services'][0]
                    primary_deployment = next(
                        (d for d in service['deployments'] if d['status'] == 'PRIMARY'),
                        None
                    )
                    
                    if primary_deployment:
                        running_count = primary_deployment['runningCount']
                        desired_count = primary_deployment['desiredCount']
                        
                        # Determine health status
                        if running_count == desired_count and service['status'] == 'ACTIVE':
                            status = 'HEALTHY'
                        elif running_count > 0:
                            status = 'DEGRADED'
                        else:
                            status = 'UNHEALTHY'
                        
                        services_status[service_name] = {
                            'status': status,
                            'running_count': running_count,
                            'desired_count': desired_count,
                            'service_status': service['status'],
                            'last_updated': primary_deployment.get('updatedAt', datetime.now())
                        }
                    else:
                        services_status[service_name] = {
                            'status': 'NO_DEPLOYMENT',
                            'running_count': 0,
                            'desired_count': 0,
                            'service_status': 'INACTIVE'
                        }
                else:
                    services_status[service_name] = {
                        'status': 'NOT_FOUND',
                        'running_count': 0,
                        'desired_count': 0,
                        'service_status': 'NOT_FOUND'
                    }
                    
            except Exception as e:
                services_status[service_name] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'running_count': 0,
                    'desired_count': 0
                }
        
        return services_status
    
    def get_cloudwatch_metrics(self) -> Dict:
        """Lấy CloudWatch metrics"""
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=1)
            
            # Lấy metrics cho Step Functions
            sf_metrics = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/States',
                MetricName='ExecutionsSucceeded',
                Dimensions=[
                    {
                        'Name': 'StateMachineArn',
                        'Value': self.get_state_machine_arn()
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=['Sum']
            )
            
            # Lấy metrics cho ECS
            ecs_metrics = {}
            for service_name in self.config['microservices'].keys():
                try:
                    cluster_name = f"restaurant-staging"
                    service_name_full = f"{service_name}-staging"
                    
                    cpu_metrics = self.cloudwatch_client.get_metric_statistics(
                        Namespace='AWS/ECS',
                        MetricName='CPUUtilization',
                        Dimensions=[
                            {'Name': 'ClusterName', 'Value': cluster_name},
                            {'Name': 'ServiceName', 'Value': service_name_full}
                        ],
                        StartTime=end_time - timedelta(minutes=10),
                        EndTime=end_time,
                        Period=300,
                        Statistics=['Average']
                    )
                    
                    avg_cpu = 0
                    if cpu_metrics['Datapoints']:
                        avg_cpu = sum(dp['Average'] for dp in cpu_metrics['Datapoints']) / len(cpu_metrics['Datapoints'])
                    
                    ecs_metrics[service_name] = {
                        'cpu_utilization': avg_cpu
                    }
                    
                except Exception:
                    ecs_metrics[service_name] = {'cpu_utilization': 0}
            
            return {
                'step_functions': {
                    'executions_succeeded': sum(dp['Sum'] for dp in sf_metrics['Datapoints']) if sf_metrics['Datapoints'] else 0
                },
                'ecs': ecs_metrics
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def display_active_executions(self, executions: List[Dict]):
        """Hiển thị active executions"""
        print(f"\n{Fore.YELLOW}🔄 ACTIVE DEPLOYMENTS")
        print(f"{Fore.YELLOW}{'-'*50}")
        
        if not executions:
            print(f"{Fore.GREEN}✅ Không có deployment nào đang chạy")
            return
        
        table_data = []
        for execution in executions:
            start_time = execution['start_date'].strftime('%H:%M:%S')
            duration = (datetime.now(timezone.utc) - execution['start_date'].replace(tzinfo=timezone.utc)).total_seconds()
            duration_str = f"{int(duration//60)}m {int(duration%60)}s"
            
            table_data.append([
                execution['name'],
                f"{Fore.CYAN}RUNNING{Style.RESET_ALL}",
                start_time,
                duration_str
            ])
        
        headers = ['Name', 'Status', 'Start', 'Duration']
        print(tabulate(table_data, headers=headers, tablefmt='simple'))
    
    def display_recent_executions(self, executions: List[Dict]):
        """Hiển thị recent executions"""
        print(f"\n{Fore.MAGENTA}📊 RECENT DEPLOYMENTS")
        print(f"{Fore.MAGENTA}{'-'*50}")
        
        if not executions:
            print("Không có executions nào")
            return
        
        table_data = []
        for execution in executions:
            start_time = execution['start_date'].strftime('%H:%M:%S')
            
            # Tính duration
            if execution.get('stop_date'):
                duration = (execution['stop_date'] - execution['start_date']).total_seconds()
                duration_str = f"{int(duration//60)}m {int(duration%60)}s"
            else:
                duration = (datetime.now(timezone.utc) - execution['start_date'].replace(tzinfo=timezone.utc)).total_seconds()
                duration_str = f"{int(duration//60)}m {int(duration%60)}s"
            
            # Tô màu status
            status = execution['status']
            if status == 'SUCCEEDED':
                colored_status = f"{Fore.GREEN}✅ SUCCESS{Style.RESET_ALL}"
            elif status == 'FAILED':
                colored_status = f"{Fore.RED}❌ FAILED{Style.RESET_ALL}"
            elif status == 'RUNNING':
                colored_status = f"{Fore.CYAN}🔄 RUNNING{Style.RESET_ALL}"
            else:
                colored_status = f"{Fore.YELLOW}{status}{Style.RESET_ALL}"
            
            table_data.append([
                execution['name'][:30],
                colored_status,
                start_time,
                duration_str
            ])
        
        headers = ['Name', 'Status', 'Start', 'Duration']
        print(tabulate(table_data, headers=headers, tablefmt='simple'))
    
    def display_services_status(self, services_status: Dict):
        """Hiển thị trạng thái services"""
        print(f"\n{Fore.GREEN}🏥 SERVICES HEALTH STATUS")
        print(f"{Fore.GREEN}{'-'*50}")
        
        table_data = []
        for service_name, status_info in services_status.items():
            status = status_info.get('status', 'UNKNOWN')
            
            # Icon và màu cho status
            if status == 'HEALTHY':
                status_display = f"{Fore.GREEN}🟢 HEALTHY{Style.RESET_ALL}"
            elif status == 'DEGRADED':
                status_display = f"{Fore.YELLOW}🟡 DEGRADED{Style.RESET_ALL}"
            elif status == 'UNHEALTHY':
                status_display = f"{Fore.RED}🔴 UNHEALTHY{Style.RESET_ALL}"
            elif status == 'NOT_FOUND':
                status_display = f"{Fore.GRAY}⚫ NOT_FOUND{Style.RESET_ALL}"
            else:
                status_display = f"{Fore.MAGENTA}🟣 {status}{Style.RESET_ALL}"
            
            running = status_info.get('running_count', 0)
            desired = status_info.get('desired_count', 0)
            tasks = f"{running}/{desired}"
            
            # CPU info nếu có
            cpu_info = ""
            
            table_data.append([
                service_name,
                status_display,
                tasks,
                cpu_info
            ])
        
        headers = ['Service', 'Health', 'Tasks', 'CPU']
        print(tabulate(table_data, headers=headers, tablefmt='simple'))
    
    def display_metrics(self, metrics: Dict):
        """Hiển thị metrics"""
        print(f"\n{Fore.BLUE}📈 METRICS (Last Hour)")
        print(f"{Fore.BLUE}{'-'*50}")
        
        if 'error' in metrics:
            print(f"{Fore.RED}Lỗi lấy metrics: {metrics['error']}")
            return
        
        # Step Functions metrics
        sf_metrics = metrics.get('step_functions', {})
        executions_succeeded = sf_metrics.get('executions_succeeded', 0)
        print(f"Step Functions Executions Succeeded: {Fore.GREEN}{executions_succeeded}{Style.RESET_ALL}")
        
        # ECS metrics
        ecs_metrics = metrics.get('ecs', {})
        print(f"\nECS CPU Utilization:")
        for service, data in ecs_metrics.items():
            cpu = data.get('cpu_utilization', 0)
            cpu_color = Fore.GREEN if cpu < 70 else Fore.YELLOW if cpu < 90 else Fore.RED
            print(f"  {service}: {cpu_color}{cpu:.1f}%{Style.RESET_ALL}")
    
    def display_alerts(self):
        """Hiển thị alerts"""
        print(f"\n{Fore.RED}🚨 ALERTS & WARNINGS")
        print(f"{Fore.RED}{'-'*50}")
        
        # Placeholder for alerts logic
        alerts = []
        
        # Check for failed executions in last hour
        try:
            response = self.stepfunctions_client.list_executions(
                stateMachineArn=self.get_state_machine_arn(),
                statusFilter='FAILED',
                maxResults=5
            )
            
            recent_failures = 0
            now = datetime.now(timezone.utc)
            for execution in response['executions']:
                if execution['startDate'].replace(tzinfo=timezone.utc) > now - timedelta(hours=1):
                    recent_failures += 1
            
            if recent_failures > 0:
                alerts.append(f"🔥 {recent_failures} deployment failures in last hour")
                
        except Exception:
            pass
        
        if not alerts:
            print(f"{Fore.GREEN}✅ No alerts - All systems normal")
        else:
            for alert in alerts:
                print(f"{Fore.RED}{alert}")
    
    def run_dashboard(self, refresh_interval: int = 30, environment: str = "staging"):
        """Chạy dashboard với auto-refresh"""
        self.running = True
        
        try:
            while self.running:
                # Clear screen và hiển thị header
                self.clear_screen()
                self.print_header()
                
                # Lấy data
                active_executions = self.get_active_executions()
                recent_executions = self.get_recent_executions()
                services_status = self.get_services_status(environment)
                metrics = self.get_cloudwatch_metrics()
                
                # Hiển thị data
                self.display_active_executions(active_executions)
                self.display_recent_executions(recent_executions)
                self.display_services_status(services_status)
                self.display_metrics(metrics)
                self.display_alerts()
                
                # Footer
                print(f"\n{Fore.CYAN}{'='*80}")
                print(f"{Fore.WHITE}Press Ctrl+C to exit | Refresh every {refresh_interval}s | Environment: {environment}")
                print(f"{Fore.CYAN}{'='*80}")
                
                # Wait for next refresh
                time.sleep(refresh_interval)
                
        except KeyboardInterrupt:
            self.running = False
            print(f"\n{Fore.YELLOW}Dashboard stopped")
        except Exception as e:
            print(f"\n{Fore.RED}Dashboard error: {str(e)}")
    
    def run_simple_monitor(self, execution_arn: str):
        """Monitor một execution cụ thể"""
        try:
            while True:
                # Lấy status
                response = self.stepfunctions_client.describe_execution(
                    executionArn=execution_arn
                )
                
                status = response['status']
                
                self.clear_screen()
                print(f"{Fore.CYAN}🔍 MONITORING EXECUTION")
                print(f"{Fore.CYAN}{'='*60}")
                print(f"Execution: {response['name']}")
                print(f"Status: {self.format_status(status)}")
                print(f"Start Time: {response['startDate']}")
                
                if status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                    print(f"Stop Time: {response.get('stopDate', 'N/A')}")
                    
                    if status == 'SUCCEEDED':
                        print(f"\n{Fore.GREEN}🎉 Execution completed successfully!")
                    else:
                        print(f"\n{Fore.RED}💥 Execution failed: {status}")
                    
                    break
                
                # Hiển thị recent events
                try:
                    events_response = self.stepfunctions_client.get_execution_history(
                        executionArn=execution_arn,
                        maxResults=5,
                        reverseOrder=True
                    )
                    
                    print(f"\n{Fore.YELLOW}Recent Events:")
                    for event in reversed(events_response['events'][-3:]):
                        timestamp = event['timestamp'].strftime('%H:%M:%S')
                        event_type = event['type']
                        print(f"  {timestamp} - {event_type}")
                        
                except Exception:
                    pass
                
                print(f"\n{Fore.WHITE}Press Ctrl+C to stop monitoring")
                time.sleep(10)
                
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Monitoring stopped")
        except Exception as e:
            print(f"\n{Fore.RED}Monitoring error: {str(e)}")
    
    def format_status(self, status: str) -> str:
        """Format status với màu sắc"""
        if status == 'RUNNING':
            return f"{Fore.CYAN}🔄 RUNNING{Style.RESET_ALL}"
        elif status == 'SUCCEEDED':
            return f"{Fore.GREEN}✅ SUCCEEDED{Style.RESET_ALL}"
        elif status == 'FAILED':
            return f"{Fore.RED}❌ FAILED{Style.RESET_ALL}"
        elif status == 'TIMED_OUT':
            return f"{Fore.YELLOW}⏰ TIMED_OUT{Style.RESET_ALL}"
        else:
            return f"{Fore.MAGENTA}{status}{Style.RESET_ALL}"

# CLI Interface
@click.group()
@click.pass_context
def cli(ctx):
    """Restaurant Microservices Deployment Dashboard"""
    ctx.ensure_object(dict)
    ctx.obj['dashboard'] = DeploymentDashboard()

@cli.command()
@click.option('--refresh', '-r', default=30, help='Refresh interval in seconds')
@click.option('--environment', '-e', default='staging', help='Environment to monitor')
@click.pass_context
def dashboard(ctx, refresh, environment):
    """Chạy dashboard với auto-refresh"""
    dashboard = ctx.obj['dashboard']
    print(f"{Fore.CYAN}🚀 Starting deployment dashboard...")
    print(f"{Fore.CYAN}Environment: {environment} | Refresh: {refresh}s")
    dashboard.run_dashboard(refresh, environment)

@cli.command()
@click.argument('execution_arn')
@click.pass_context
def monitor(ctx, execution_arn):
    """Monitor một execution cụ thể"""
    dashboard = ctx.obj['dashboard']
    dashboard.run_simple_monitor(execution_arn)

@cli.command()
@click.option('--environment', '-e', default='staging', help='Environment')
@click.pass_context
def status(ctx, environment):
    """Hiển thị status một lần (không auto-refresh)"""
    dashboard = ctx.obj['dashboard']
    
    # Lấy data
    active_executions = dashboard.get_active_executions()
    recent_executions = dashboard.get_recent_executions()
    services_status = dashboard.get_services_status(environment)
    
    # Hiển thị
    dashboard.print_header()
    dashboard.display_active_executions(active_executions)
    dashboard.display_recent_executions(recent_executions)
    dashboard.display_services_status(services_status)

if __name__ == '__main__':
    cli() 