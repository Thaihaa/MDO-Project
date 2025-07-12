# Restaurant Microservices Deployment Orchestrator

🚀 **Hệ thống quản lý deployment microservices sử dụng AWS Step Functions**

Đây là project hoàn chỉnh để quản lý deployment các microservices của hệ thống nhà hàng sử dụng AWS Step Functions. System này giúp tự động hóa việc deploy, health check, và rollback các services một cách an toàn và có thể theo dõi được.

## 📋 Mục lục

- [Tính năng](#-tính-năng)
- [Kiến trúc](#-kiến-trúc)
- [Yêu cầu](#-yêu-cầu)
- [Cài đặt](#-cài-đặt)
- [Cấu hình](#-cấu-hình)
- [Sử dụng](#-sử-dụng)
- [Dashboard](#-dashboard)
- [Lambda Functions](#-lambda-functions)
- [Troubleshooting](#-troubleshooting)
- [Đóng góp](#-đóng-góp)

## 🎯 Tính năng

### ✅ Deployment Orchestration
- **Sequential Deployment**: Deploy các microservices theo thứ tự dependency
- **Health Checking**: Kiểm tra health của từng service sau khi deploy
- **Automatic Rollback**: Tự động rollback khi deployment thất bại
- **Parallel Processing**: Hỗ trợ deploy song song các services độc lập

### 📊 Monitoring & Alerting
- **Real-time Dashboard**: Dashboard theo dõi trạng thái deployments
- **CloudWatch Integration**: Ghi log chi tiết và metrics
- **Multi-channel Notifications**: Thông báo qua Email, SNS, Slack
- **Health Status Tracking**: Theo dõi health của các services

### 🔄 Workflow Management
- **Step Functions**: Orchestration bằng AWS Step Functions
- **Error Handling**: Xử lý lỗi và retry mechanisms
- **State Management**: Quản lý trạng thái deployment
- **Execution History**: Lịch sử và audit trail

## 🏗️ Kiến trúc

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CLI/Dashboard │    │  Step Functions │    │   Lambda Funcs  │
│                 │───▶│                 │───▶│                 │
│  - Deploy Cmd   │    │  - Orchestrator │    │  - Deployer     │
│  - Monitor      │    │  - State Mgmt   │    │  - Health Check │
│  - Dashboard    │    │  - Error Handle │    │  - Rollback     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   ECS Services  │    │   CloudWatch    │    │  Notifications  │
│                 │    │                 │    │                 │
│  - Auth Service │    │  - Logs         │    │  - SNS          │
│  - Menu Service │    │  - Metrics      │    │  - Email        │
│  - Order Service│    │  - Dashboards   │    │  - Slack        │
│  - Payment Svc  │    │  - Alarms       │    │  - Dashboard    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Components chính:

1. **Step Functions State Machine**: Orchestrates toàn bộ deployment workflow
2. **Lambda Functions**: Thực hiện các tasks cụ thể (deploy, health check, rollback)
3. **ECS Services**: Host các microservices
4. **CloudWatch**: Logging và monitoring
5. **SNS/Email/Slack**: Notification system

## 📋 Yêu cầu

### AWS Services
- AWS Step Functions
- AWS Lambda
- Amazon ECS/Fargate
- Amazon ECR
- AWS CloudWatch
- AWS SNS
- AWS IAM

### Local Environment
- Python 3.8+
- AWS CLI configured
- Docker (để build images)
- Git

### AWS Permissions
User cần có quyền:
- `stepfunctions:*`
- `lambda:*`
- `ecs:*`
- `ecr:*`
- `cloudwatch:*`
- `sns:*`
- `iam:PassRole`

## 🚀 Cài đặt

### 1. Clone Repository
```bash
git clone <repository-url>
cd restaurant-microservices-orchestrator
```

### 2. Setup Python Environment
```bash
# Tạo virtual environment
python -m venv venv

# Activate virtual environment
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure AWS CLI
```bash
aws configure
# Nhập AWS Access Key ID, Secret Access Key, Region, Output format
```

## ⚙️ Cấu hình

### 1. Cập nhật Config File
Sửa file `config/aws_config.yaml`:

```yaml
aws:
  region: "us-east-1"  # Thay đổi region của bạn
  profile: "default"   # AWS profile

step_functions:
  state_machine_name: "restaurant-deployment-orchestrator"
  execution_role_arn: "arn:aws:iam::{account_id}:role/StepFunctionsExecutionRole"

microservices:
  auth_service:
    name: "auth-service"
    repository: "your-account.dkr.ecr.region.amazonaws.com/auth-service"
    health_check_endpoint: "/health"
    port: 8080
  # ... cấu hình các services khác
```

### 2. Tạo IAM Roles

#### Step Functions Execution Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction",
        "logs:*",
        "sns:Publish"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Lambda Execution Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecs:*",
        "ecr:*",
        "ec2:DescribeNetworkInterfaces",
        "logs:*",
        "sns:Publish",
        "ses:SendEmail"
      ],
      "Resource": "*"
    }
  ]
}
```

### 3. Setup Environment Variables

Tạo file `.env`:
```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# Lambda Environment Variables
TASK_EXECUTION_ROLE_ARN=arn:aws:iam::123456789012:role/ecsTaskExecutionRole
TASK_ROLE_ARN=arn:aws:iam::123456789012:role/ecsTaskRole
SUBNET_IDS=subnet-12345,subnet-67890
SECURITY_GROUP_ID=sg-12345

# Notification Configuration
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:deployment-notifications
SENDER_EMAIL=deploy@yourcompany.com
RECIPIENT_EMAILS=team@yourcompany.com,ops@yourcompany.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## 🎮 Sử dụng

### 1. Setup Step Functions State Machine

```bash
# Setup state machine lần đầu
python src/deployment_orchestrator.py setup
```

### 2. Deploy Lambda Functions

```bash
# Deploy tất cả Lambda functions
aws lambda create-function \
  --function-name deployment-initializer \
  --runtime python3.9 \
  --role arn:aws:iam::ACCOUNT:role/lambda-execution-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_functions/deployment_initializer.zip

# Tương tự cho các functions khác...
```

### 3. Bắt đầu Deployment

#### Basic Deployment
```bash
# Deploy với default settings (staging environment, latest version)
python src/deployment_orchestrator.py deploy

# Deploy với specific parameters
python src/deployment_orchestrator.py deploy \
  --environment production \
  --version v1.2.3 \
  --wait
```

#### Deploy Specific Services
```bash
# Deploy chỉ auth và menu services
python src/deployment_orchestrator.py deploy \
  --services auth-service \
  --services menu-service \
  --environment staging \
  --wait
```

### 4. Monitor Deployments

#### List Recent Executions
```bash
# Xem 10 executions gần nhất
python src/deployment_orchestrator.py list-executions --limit 10
```

#### Check Execution Status
```bash
# Check status của một execution cụ thể
python src/deployment_orchestrator.py status arn:aws:states:region:account:execution:name:id
```

#### Stop Running Execution
```bash
# Dừng execution đang chạy
python src/deployment_orchestrator.py stop arn:aws:states:region:account:execution:name:id
```

### 5. Health Checking

```bash
# Check health của tất cả services
python src/deployment_orchestrator.py health

# Check health của environment cụ thể
python src/deployment_orchestrator.py health --environment production
```

## 📊 Dashboard

### 1. Chạy Real-time Dashboard

```bash
# Dashboard với auto-refresh mỗi 30 giây
python src/deployment_dashboard.py dashboard

# Custom refresh interval
python src/deployment_dashboard.py dashboard --refresh 10

# Monitor specific environment
python src/deployment_dashboard.py dashboard --environment production
```

### 2. Monitor Specific Execution

```bash
# Monitor một execution cụ thể
python src/deployment_dashboard.py monitor arn:aws:states:region:account:execution:name:id
```

### 3. One-time Status Check

```bash
# Xem status một lần (không auto-refresh)
python src/deployment_dashboard.py status
```

### Dashboard Features

- **🔄 Active Deployments**: Hiển thị deployments đang chạy
- **📊 Recent Deployments**: Lịch sử deployments gần đây
- **🏥 Service Health**: Trạng thái health của tất cả services
- **📈 Metrics**: CPU utilization và metrics khác
- **🚨 Alerts**: Cảnh báo và notifications

## 🔧 Lambda Functions

### 1. Deployment Initializer
**File**: `lambda_functions/deployment_initializer.py`
- Khởi tạo deployment context
- Tạo deployment ID unique
- Setup logging

### 2. Microservice Deployer
**File**: `lambda_functions/microservice_deployer.py`
- Deploy individual microservice
- Update ECS task definition
- Deploy to ECS cluster
- Wait for deployment completion

### 3. Health Checker
**File**: `lambda_functions/health_checker.py`
- Check ECS service status
- Test health endpoints
- Validate service availability

### 4. Final Health Checker
**File**: `lambda_functions/final_health_checker.py`
- Overall system health check
- Inter-service connectivity testing
- Generate health report

### 5. Deployment Notifier
**File**: `lambda_functions/deployment_notifier.py`
- Send notifications via multiple channels
- Generate HTML emails
- Post to Slack
- Log to CloudWatch

### 6. Deployment Rollback
**File**: `lambda_functions/deployment_rollback.py`
- Rollback failed deployments
- Restore previous task definitions
- Cleanup failed resources

## 🔍 Troubleshooting

### Common Issues

#### 1. State Machine Creation Failed
```bash
# Check IAM permissions
aws iam get-role --role-name StepFunctionsExecutionRole

# Verify role trust policy
aws iam get-role-policy --role-name StepFunctionsExecutionRole --policy-name StepFunctionsPolicy
```

#### 2. Lambda Function Timeout
- Increase timeout in Lambda configuration
- Check network connectivity to ECS
- Verify security group rules

#### 3. ECS Service Not Found
```bash
# List ECS clusters
aws ecs list-clusters

# Check services in cluster
aws ecs list-services --cluster restaurant-staging
```

#### 4. Health Check Failed
- Verify service endpoints
- Check security group rules
- Ensure load balancer configuration

### Debug Commands

#### View Execution History
```bash
aws stepfunctions get-execution-history \
  --execution-arn "arn:aws:states:region:account:execution:name:id" \
  --max-items 50
```

#### Check Lambda Logs
```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/"

aws logs tail /aws/lambda/deployment-initializer
```

#### ECS Service Events
```bash
aws ecs describe-services \
  --cluster restaurant-staging \
  --services auth-service-staging
```

### Performance Tuning

#### 1. Optimize Lambda Cold Starts
- Increase memory allocation
- Use provisioned concurrency
- Minimize package size

#### 2. ECS Task Optimization
- Right-size CPU and memory
- Use appropriate instance types
- Optimize health check intervals

#### 3. Step Functions Optimization
- Reduce state transitions
- Use parallel processing where possible
- Implement efficient retry strategies

## 📚 Examples

### Example 1: Simple Deployment

```bash
# Deploy tất cả services lên staging
python src/deployment_orchestrator.py deploy \
  --environment staging \
  --version latest \
  --wait

# Expected output:
# ✅ AWS clients đã được khởi tạo thành công
# ℹ️  Bắt đầu deployment - Environment: staging, Version: latest
# ✅ Deployment đã được bắt đầu!
# ℹ️  Execution ARN: arn:aws:states:...
# 🔄 Status: ĐANG CHẠY
# ✅ Status: THÀNH CÔNG
# 🎉 Deployment hoàn thành thành công!
```

### Example 2: Production Deployment với Monitoring

```bash
# Terminal 1: Start deployment
python src/deployment_orchestrator.py deploy \
  --environment production \
  --version v2.1.0 \
  --services auth-service \
  --services menu-service

# Terminal 2: Monitor dashboard
python src/deployment_dashboard.py dashboard \
  --environment production \
  --refresh 15
```

### Example 3: Rollback Scenario

```python
# Nếu deployment thất bại, system sẽ tự động rollback
# Bạn có thể theo dõi quá trình qua dashboard

# Check health after rollback
python src/deployment_orchestrator.py health --environment production
```

## 🤝 Đóng góp

### Development Setup

1. Fork repository
2. Create feature branch
3. Setup development environment
4. Make changes
5. Test thoroughly
6. Submit pull request

### Code Style

- Follow PEP 8
- Use type hints
- Write comprehensive docstrings
- Add unit tests for new features

### Testing

```bash
# Run unit tests
python -m pytest tests/

# Run integration tests
python -m pytest tests/integration/

# Run with coverage
python -m pytest --cov=src tests/
```

## 📄 License

MIT License - xem file [LICENSE](LICENSE) để biết thêm chi tiết.

## 📞 Support

- **Issues**: [GitHub Issues](link-to-issues)
- **Documentation**: [Wiki](link-to-wiki)
- **Email**: support@yourcompany.com

---

## 🚀 Quick Start Guide

### Bước 1: Cài đặt
```bash
git clone <repo>
cd restaurant-microservices-orchestrator
pip install -r requirements.txt
```

### Bước 2: Cấu hình
```bash
# Sửa config/aws_config.yaml
# Tạo IAM roles
# Setup environment variables
```

### Bước 3: Deploy
```bash
python src/deployment_orchestrator.py setup
python src/deployment_orchestrator.py deploy --wait
```

### Bước 4: Monitor
```bash
python src/deployment_dashboard.py dashboard
```

**🎉 Chúc bạn deployment thành công!** 