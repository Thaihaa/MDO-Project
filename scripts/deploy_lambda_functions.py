#!/usr/bin/env python3
"""
Script để deploy tất cả Lambda functions lên AWS

Usage: python scripts/deploy_lambda_functions.py
"""

import os
import json
import zipfile
import boto3
import yaml
import sys
import time
from pathlib import Path
import tempfile
import shutil

def load_config():
    """Load cấu hình từ config file"""
    config_file = "config/aws_config.yaml"
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Lỗi load config: {str(e)}")
        sys.exit(1)

def get_account_id():
    """Lấy AWS Account ID"""
    try:
        sts_client = boto3.client('sts')
        response = sts_client.get_caller_identity()
        return response['Account']
    except Exception as e:
        print(f"❌ Không thể lấy Account ID: {str(e)}")
        return "123456789012"

def create_lambda_zip(function_name, source_dir="lambda_functions"):
    """Tạo zip file cho Lambda function"""
    source_file = f"{source_dir}/{function_name}.py"
    
    if not os.path.exists(source_file):
        print(f"❌ Không tìm thấy file: {source_file}")
        return None
    
    # Tạo temp directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy source file
        temp_source = os.path.join(temp_dir, "lambda_function.py")
        shutil.copy2(source_file, temp_source)
        
        # Create zip file
        zip_path = f"/tmp/{function_name}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(temp_source, "lambda_function.py")
        
        return zip_path

def create_or_update_lambda_function(lambda_client, function_name, zip_path, role_arn, 
                                   environment_vars=None, timeout=300, memory_size=512):
    """Tạo hoặc cập nhật Lambda function"""
    try:
        # Đọc zip file
        with open(zip_path, 'rb') as zip_file:
            zip_content = zip_file.read()
        
        # Kiểm tra function đã tồn tại chưa
        try:
            lambda_client.get_function(FunctionName=function_name)
            function_exists = True
        except lambda_client.exceptions.ResourceNotFoundException:
            function_exists = False
        
        if function_exists:
            # Cập nhật function code
            print(f"🔄 Updating function: {function_name}")
            
            lambda_client.update_function_code(
                FunctionName=function_name,
                ZipFile=zip_content
            )
            
            # Cập nhật configuration
            update_params = {
                'FunctionName': function_name,
                'Role': role_arn,
                'Timeout': timeout,
                'MemorySize': memory_size
            }
            
            if environment_vars:
                update_params['Environment'] = {'Variables': environment_vars}
            
            lambda_client.update_function_configuration(**update_params)
            
        else:
            # Tạo function mới
            print(f"🆕 Creating function: {function_name}")
            
            create_params = {
                'FunctionName': function_name,
                'Runtime': 'python3.9',
                'Role': role_arn,
                'Handler': 'lambda_function.lambda_handler',
                'Code': {'ZipFile': zip_content},
                'Timeout': timeout,
                'MemorySize': memory_size,
                'Publish': True
            }
            
            if environment_vars:
                create_params['Environment'] = {'Variables': environment_vars}
            
            lambda_client.create_function(**create_params)
        
        # Chờ function active
        print(f"⏳ Waiting for {function_name} to be active...")
        waiter = lambda_client.get_waiter('function_active')
        waiter.wait(FunctionName=function_name)
        
        print(f"✅ {function_name} deployed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error deploying {function_name}: {str(e)}")
        return False

def create_execution_role(iam_client, role_name):
    """Tạo IAM role cho Lambda execution"""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    # Policy cho Lambda functions
    lambda_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                "Resource": "arn:aws:logs:*:*:*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ecs:*",
                    "ecr:*",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:CreateNetworkInterface",
                    "ec2:DeleteNetworkInterface",
                    "ec2:DescribeInstances",
                    "ec2:AttachNetworkInterface"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "sns:Publish",
                    "ses:SendEmail",
                    "ses:SendRawEmail"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "lambda:InvokeFunction"
                ],
                "Resource": "*"
            }
        ]
    }
    
    try:
        # Kiểm tra role đã tồn tại chưa
        try:
            role_response = iam_client.get_role(RoleName=role_name)
            role_arn = role_response['Role']['Arn']
            print(f"✅ Using existing IAM role: {role_name}")
            
        except iam_client.exceptions.NoSuchEntityException:
            # Tạo role mới
            print(f"🆕 Creating IAM role: {role_name}")
            
            role_response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='Execution role for restaurant deployment Lambda functions'
            )
            
            role_arn = role_response['Role']['Arn']
            
            # Attach policy
            policy_name = f"{role_name}-policy"
            
            try:
                iam_client.put_role_policy(
                    RoleName=role_name,
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(lambda_policy)
                )
                print(f"✅ Created IAM role and policy: {role_name}")
                
                # Chờ role được propagate
                print("⏳ Waiting for IAM role to propagate...")
                time.sleep(10)
                
            except Exception as e:
                print(f"❌ Error creating role policy: {str(e)}")
                return None
        
        return role_arn
        
    except Exception as e:
        print(f"❌ Error creating IAM role: {str(e)}")
        return None

def deploy_all_functions():
    """Deploy tất cả Lambda functions"""
    print("🚀 Starting Lambda functions deployment...")
    
    # Load config
    config = load_config()
    account_id = get_account_id()
    region = config['aws']['region']
    
    # Khởi tạo AWS clients
    try:
        session = boto3.Session(
            profile_name=config['aws'].get('profile', 'default'),
            region_name=region
        )
        
        lambda_client = session.client('lambda')
        iam_client = session.client('iam')
        
    except Exception as e:
        print(f"❌ Error initializing AWS clients: {str(e)}")
        return False
    
    # Tạo IAM role
    role_name = "RestaurantDeploymentLambdaExecutionRole"
    role_arn = create_execution_role(iam_client, role_name)
    
    if not role_arn:
        print("❌ Failed to create IAM role")
        return False
    
    # Environment variables chung
    common_env_vars = {
        'AWS_REGION': region,
        'AWS_ACCOUNT_ID': account_id,
        'TASK_EXECUTION_ROLE_ARN': f"arn:aws:iam::{account_id}:role/ecsTaskExecutionRole",
        'TASK_ROLE_ARN': f"arn:aws:iam::{account_id}:role/ecsTaskRole",
        'SECURITY_GROUP_ID': 'sg-default',  # Update this
        'SUBNET_IDS': 'subnet-default1,subnet-default2'  # Update this
    }
    
    # Notification environment variables
    notification_env_vars = common_env_vars.copy()
    notification_env_vars.update({
        'SNS_TOPIC_ARN': f"arn:aws:sns:{region}:{account_id}:deployment-notifications",
        'SENDER_EMAIL': 'deploy@yourcompany.com',
        'RECIPIENT_EMAILS': 'team@yourcompany.com',
        'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
    })
    
    # Danh sách functions cần deploy
    functions_to_deploy = [
        {
            'name': 'deployment-initializer',
            'file': 'deployment_initializer',
            'timeout': 60,
            'memory': 256,
            'env_vars': common_env_vars
        },
        {
            'name': 'microservice-deployer',
            'file': 'microservice_deployer',
            'timeout': 900,  # 15 minutes
            'memory': 512,
            'env_vars': common_env_vars
        },
        {
            'name': 'health-checker',
            'file': 'health_checker',
            'timeout': 300,  # 5 minutes
            'memory': 256,
            'env_vars': common_env_vars
        },
        {
            'name': 'final-health-checker',
            'file': 'final_health_checker',
            'timeout': 600,  # 10 minutes
            'memory': 512,
            'env_vars': common_env_vars
        },
        {
            'name': 'deployment-notifier',
            'file': 'deployment_notifier',
            'timeout': 300,
            'memory': 256,
            'env_vars': notification_env_vars
        },
        {
            'name': 'deployment-rollback',
            'file': 'deployment_rollback',
            'timeout': 900,  # 15 minutes
            'memory': 512,
            'env_vars': common_env_vars
        }
    ]
    
    # Deploy từng function
    success_count = 0
    total_count = len(functions_to_deploy)
    
    for func_config in functions_to_deploy:
        print(f"\n📦 Processing: {func_config['name']}")
        
        # Tạo zip file
        zip_path = create_lambda_zip(func_config['file'])
        if not zip_path:
            continue
        
        try:
            # Deploy function
            success = create_or_update_lambda_function(
                lambda_client=lambda_client,
                function_name=func_config['name'],
                zip_path=zip_path,
                role_arn=role_arn,
                environment_vars=func_config['env_vars'],
                timeout=func_config['timeout'],
                memory_size=func_config['memory']
            )
            
            if success:
                success_count += 1
            
        finally:
            # Cleanup zip file
            if os.path.exists(zip_path):
                os.remove(zip_path)
    
    # Kết quả
    print(f"\n{'='*60}")
    print(f"📊 Deployment Summary:")
    print(f"✅ Successful: {success_count}/{total_count}")
    print(f"❌ Failed: {total_count - success_count}/{total_count}")
    
    if success_count == total_count:
        print(f"🎉 All Lambda functions deployed successfully!")
        
        # Hiển thị next steps
        print(f"\n📋 Next Steps:")
        print(f"1. Update Step Functions state machine definition với đúng function ARNs")
        print(f"2. Configure environment variables với đúng values:")
        print(f"   - SUBNET_IDS: subnet IDs thật")
        print(f"   - SECURITY_GROUP_ID: security group ID thật") 
        print(f"   - SNS_TOPIC_ARN: SNS topic ARN thật")
        print(f"   - Email/Slack configurations")
        print(f"3. Deploy Step Functions state machine:")
        print(f"   python src/deployment_orchestrator.py setup")
        print(f"4. Test deployment:")
        print(f"   python src/deployment_orchestrator.py deploy --wait")
        
        return True
    else:
        print(f"💥 Some functions failed to deploy. Check the errors above.")
        return False

def update_step_functions_definition():
    """Cập nhật Step Functions definition với Lambda ARNs"""
    print("\n🔄 Updating Step Functions definition...")
    
    config = load_config()
    account_id = get_account_id()
    region = config['aws']['region']
    
    # Đọc template
    template_file = "step_functions/restaurant_deployment_orchestrator.json"
    with open(template_file, 'r') as f:
        definition = f.read()
    
    # Function name mappings
    function_mappings = {
        'deployment-initializer': f"arn:aws:lambda:{region}:{account_id}:function:deployment-initializer",
        'microservice-deployer': f"arn:aws:lambda:{region}:{account_id}:function:microservice-deployer",
        'health-checker': f"arn:aws:lambda:{region}:{account_id}:function:health-checker",
        'final-health-checker': f"arn:aws:lambda:{region}:{account_id}:function:final-health-checker",
        'deployment-notifier': f"arn:aws:lambda:{region}:{account_id}:function:deployment-notifier",
        'deployment-rollback': f"arn:aws:lambda:{region}:{account_id}:function:deployment-rollback"
    }
    
    # Replace function names với ARNs
    for func_name, func_arn in function_mappings.items():
        definition = definition.replace(f'"FunctionName": "{func_name}"', f'"FunctionName": "{func_arn}"')
    
    # Lưu updated definition
    updated_file = template_file.replace('.json', '_updated.json')
    with open(updated_file, 'w') as f:
        f.write(definition)
    
    print(f"✅ Updated Step Functions definition saved to: {updated_file}")
    print(f"💡 Tip: Copy this file over the original template to use updated ARNs")

def cleanup_old_versions():
    """Dọn dẹp các versions cũ của Lambda functions"""
    print("\n🧹 Cleaning up old Lambda function versions...")
    
    config = load_config()
    session = boto3.Session(
        profile_name=config['aws'].get('profile', 'default'),
        region_name=config['aws']['region']
    )
    
    lambda_client = session.client('lambda')
    
    function_names = [
        'deployment-initializer',
        'microservice-deployer', 
        'health-checker',
        'final-health-checker',
        'deployment-notifier',
        'deployment-rollback'
    ]
    
    for func_name in function_names:
        try:
            # Lấy danh sách versions
            response = lambda_client.list_versions_by_function(FunctionName=func_name)
            versions = response['Versions']
            
            # Xóa versions cũ (giữ lại $LATEST và 2 versions gần nhất)
            versions_to_delete = [v for v in versions if v['Version'] not in ['$LATEST']]
            
            if len(versions_to_delete) > 2:
                for version in versions_to_delete[:-2]:  # Keep last 2 versions
                    try:
                        lambda_client.delete_function(
                            FunctionName=func_name,
                            Qualifier=version['Version']
                        )
                        print(f"🗑️ Deleted {func_name} version {version['Version']}")
                    except Exception as e:
                        print(f"⚠️ Could not delete {func_name} version {version['Version']}: {str(e)}")
                        
        except Exception as e:
            print(f"⚠️ Could not cleanup {func_name}: {str(e)}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Deploy Lambda functions for Restaurant Deployment Orchestrator')
    parser.add_argument('--cleanup', action='store_true', help='Cleanup old function versions after deployment')
    parser.add_argument('--update-stepfunctions', action='store_true', help='Update Step Functions definition with Lambda ARNs')
    
    args = parser.parse_args()
    
    # Deploy functions
    success = deploy_all_functions()
    
    if success:
        if args.update_stepfunctions:
            update_step_functions_definition()
        
        if args.cleanup:
            cleanup_old_versions()
    
    sys.exit(0 if success else 1) 