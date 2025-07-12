# Operational Procedures - Restaurant Microservices Deployment Orchestrator

## 📋 Mục lục

- [Disaster Recovery](#disaster-recovery)
- [Maintenance Procedures](#maintenance-procedures)
- [Monitoring & Alerting](#monitoring--alerting)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Emergency Procedures](#emergency-procedures)
- [Security Procedures](#security-procedures)
- [Performance Optimization](#performance-optimization)
- [Backup & Recovery](#backup--recovery)

---

## 🚨 Disaster Recovery

### 1. Disaster Recovery Plan

#### Critical Components
- **AWS Step Functions State Machine**: `restaurant-deployment-orchestrator2`
- **Lambda Functions**: 6 deployment functions
- **IAM Roles**: Step Functions execution role
- **Configuration Files**: AWS config, dependencies config

#### Recovery Time Objectives (RTO)
- **Critical**: 15 minutes
- **High**: 1 hour  
- **Medium**: 4 hours
- **Low**: 24 hours

#### Recovery Point Objectives (RPO)
- **Configuration Changes**: 0 (version controlled)
- **Deployment History**: 24 hours
- **Logs**: 1 hour

### 2. Disaster Scenarios & Response

#### Scenario 1: AWS Region Failure
**Impact**: Complete service unavailability
**Priority**: Critical
**RTO**: 15 minutes

**Response Steps:**
1. **Immediate (0-5 minutes)**
   ```bash
   # Switch to backup region
   export AWS_DEFAULT_REGION=us-west-2
   
   # Verify backup region resources
   aws stepfunctions list-state-machines --region us-west-2
   ```

2. **Short-term (5-15 minutes)**
   ```bash
   # Deploy state machine to backup region
   cd restaurant-microservices-orchestrator
   python scripts/deploy_to_backup_region.py --region us-west-2
   
   # Update DNS/Load Balancer to point to backup region
   python scripts/failover_dns.py --target-region us-west-2
   ```

3. **Recovery Verification**
   ```bash
   # Test deployment in backup region
   python src/deployment_orchestrator.py deploy --environment disaster-recovery --wait
   
   # Verify all functions working
   python tests/scalability_tester.py concurrent-test --concurrent 3
   ```

#### Scenario 2: State Machine Corruption
**Impact**: Deployment pipeline down
**Priority**: Critical
**RTO**: 15 minutes

**Response Steps:**
1. **Immediate Assessment**
   ```bash
   # Check state machine status
   aws stepfunctions describe-state-machine \
     --state-machine-arn arn:aws:states:us-east-1:424470772957:stateMachine:restaurant-deployment-orchestrator2
   
   # Check recent executions
   aws stepfunctions list-executions \
     --state-machine-arn arn:aws:states:us-east-1:424470772957:stateMachine:restaurant-deployment-orchestrator2 \
     --max-items 5
   ```

2. **Recovery Actions**
   ```bash
   # Backup current definition
   aws stepfunctions describe-state-machine \
     --state-machine-arn arn:aws:states:us-east-1:424470772957:stateMachine:restaurant-deployment-orchestrator2 \
     > backup/state-machine-$(date +%Y%m%d-%H%M%S).json
   
   # Redeploy from known good definition
   python src/deployment_orchestrator.py setup
   
   # Test recovery
   python src/deployment_orchestrator.py deploy --environment recovery-test --wait
   ```

#### Scenario 3: Lambda Functions Failure
**Impact**: Specific deployment steps failing
**Priority**: High
**RTO**: 30 minutes

**Response Steps:**
1. **Identify Failed Functions**
   ```bash
   # Check CloudWatch logs
   aws logs describe-log-groups --log-group-name-prefix /aws/lambda/
   
   # Check function status
   for func in deployment-initializer microservice-deployer health-checker; do
     aws lambda get-function --function-name $func
   done
   ```

2. **Recovery Actions**
   ```bash
   # Redeploy failed functions
   python scripts/deploy_lambda_functions.py --function deployment-initializer
   
   # Update function permissions
   python scripts/fix_lambda_permissions.py
   
   # Test function
   aws lambda invoke --function-name deployment-initializer \
     --payload '{"test": true}' response.json
   ```

### 3. Data Recovery Procedures

#### Configuration Recovery
```bash
# Restore from Git
git checkout HEAD~1 config/
git checkout HEAD~1 step_functions/

# Apply emergency patches
git apply emergency-patches/config-fix.patch

# Validate configuration
python src/dependency_manager.py validate
```

#### Execution History Recovery
```bash
# Export recent executions
python scripts/export_execution_history.py --days 7 --output backup/

# Import to backup system
python scripts/import_execution_history.py --input backup/executions.json
```

---

## 🔧 Maintenance Procedures

### 1. Scheduled Maintenance

#### Weekly Maintenance (Every Sunday 2:00 AM UTC)
1. **System Health Check**
   ```bash
   # Run health checks
   python src/deployment_orchestrator.py health --environment production
   
   # Check AWS service limits
   python scripts/check_aws_limits.py
   
   # Verify Lambda function health
   python scripts/check_lambda_health.py
   ```

2. **Log Rotation & Cleanup**
   ```bash
   # Rotate CloudWatch logs (keep 30 days)
   python scripts/rotate_cloudwatch_logs.py --retention-days 30
   
   # Clean up old executions (keep 100 recent)
   python scripts/cleanup_old_executions.py --keep 100
   
   # Archive old deployment artifacts
   python scripts/archive_old_deployments.py --days 90
   ```

3. **Performance Monitoring**
   ```bash
   # Run performance baseline test
   python tests/scalability_tester.py concurrent-test --concurrent 5
   
   # Generate weekly performance report
   python scripts/generate_performance_report.py --period weekly
   ```

#### Monthly Maintenance (First Sunday 1:00 AM UTC)
1. **Security Updates**
   ```bash
   # Update IAM policies
   python scripts/update_iam_policies.py --dry-run
   python scripts/update_iam_policies.py --apply
   
   # Rotate access keys (if applicable)
   python scripts/rotate_access_keys.py
   
   # Security audit
   python scripts/security_audit.py --full
   ```

2. **Capacity Planning**
   ```bash
   # Analyze usage patterns
   python scripts/analyze_usage_patterns.py --period 30-days
   
   # Forecast capacity needs
   python scripts/capacity_forecast.py --horizon 90-days
   
   # Optimize Lambda concurrency limits
   python scripts/optimize_lambda_limits.py
   ```

### 2. Maintenance Windows

#### Standard Maintenance Window
- **Time**: Sunday 2:00-4:00 AM UTC
- **Frequency**: Weekly
- **Impact**: Minimal (deployments paused)

#### Emergency Maintenance
- **Trigger Conditions**:
  - Security vulnerabilities
  - Critical AWS service updates
  - System performance degradation > 50%

**Emergency Maintenance Procedure:**
1. **Notification (T-15 minutes)**
   ```bash
   # Send emergency notification
   python scripts/send_emergency_notification.py \
     --message "Emergency maintenance starting in 15 minutes"
   ```

2. **Maintenance Execution**
   ```bash
   # Put system in maintenance mode
   python scripts/enable_maintenance_mode.py
   
   # Stop all running deployments gracefully
   python scripts/graceful_stop_deployments.py
   
   # Perform maintenance tasks
   # ... maintenance actions ...
   
   # Verify system health
   python tests/scalability_tester.py concurrent-test --concurrent 3
   
   # Disable maintenance mode
   python scripts/disable_maintenance_mode.py
   ```

### 3. Update Procedures

#### Lambda Function Updates
```bash
# Backup current functions
python scripts/backup_lambda_functions.py

# Deploy new versions with blue-green
python scripts/deploy_lambda_blue_green.py --function microservice-deployer

# Test new version
python tests/test_lambda_function.py --function microservice-deployer

# Switch traffic to new version
python scripts/switch_lambda_traffic.py --function microservice-deployer --version $LATEST

# Cleanup old versions (keep 3)
python scripts/cleanup_lambda_versions.py --keep 3
```

#### State Machine Updates
```bash
# Backup current definition
aws stepfunctions describe-state-machine \
  --state-machine-arn arn:aws:states:us-east-1:424470772957:stateMachine:restaurant-deployment-orchestrator2 \
  > backup/state-machine-$(date +%Y%m%d-%H%M%S).json

# Validate new definition
python scripts/validate_state_machine.py --definition step_functions/restaurant_deployment_orchestrator.json

# Update state machine
aws stepfunctions update-state-machine \
  --state-machine-arn arn:aws:states:us-east-1:424470772957:stateMachine:restaurant-deployment-orchestrator2 \
  --definition file://step_functions/restaurant_deployment_orchestrator.json

# Test updated state machine
python src/deployment_orchestrator.py deploy --environment test-update --wait
```

---

## 📊 Monitoring & Alerting

### 1. Key Metrics

#### System Health Metrics
- **Deployment Success Rate**: Target > 95%
- **Average Deployment Time**: Target < 300 seconds
- **Lambda Function Errors**: Target < 1%
- **Step Function Execution Errors**: Target < 2%

#### Performance Metrics
- **Concurrent Deployment Capacity**: Monitor peak usage
- **Lambda Cold Start Times**: Target < 5 seconds
- **State Machine Throttling**: Should be 0

#### Business Metrics
- **Deployments per Hour**: Track trends
- **Mean Time to Recovery (MTTR)**: Target < 15 minutes
- **Service Availability**: Target > 99.9%

### 2. Alerting Rules

#### Critical Alerts (PagerDuty/SMS)
```yaml
Critical_Deployment_Failure:
  condition: deployment_success_rate < 80% over 15 minutes
  action: immediate_page
  
Lambda_Function_Complete_Failure:
  condition: lambda_errors > 50% over 5 minutes
  action: immediate_page
  
State_Machine_Down:
  condition: step_function_executions = 0 over 10 minutes
  action: immediate_page
```

#### Warning Alerts (Email/Slack)
```yaml
Performance_Degradation:
  condition: avg_deployment_time > 600 seconds over 30 minutes
  action: email_team
  
High_Error_Rate:
  condition: deployment_errors > 10% over 20 minutes
  action: slack_notification
  
Capacity_Warning:
  condition: concurrent_deployments > 15 for 5 minutes
  action: email_ops_team
```

### 3. Dashboard Setup

#### CloudWatch Dashboard
```bash
# Create main monitoring dashboard
python scripts/create_monitoring_dashboard.py

# Custom dashboard for operations team
python scripts/create_ops_dashboard.py --team operations
```

#### Grafana Dashboard (if using)
```bash
# Import dashboard template
python scripts/import_grafana_dashboard.py --template templates/deployment-orchestrator.json
```

---

## 🛠️ Troubleshooting Guide

### 1. Common Issues

#### Issue: "State Machine Does Not Exist"
**Symptoms**: CLI commands fail with state machine not found
**Root Cause**: Wrong state machine name in config
**Solution**:
```bash
# Check existing state machines
aws stepfunctions list-state-machines

# Update config with correct name
# Edit config/aws_config.yaml
# Set state_machine_name to correct value

# Verify fix
python src/deployment_orchestrator.py deploy --environment test --wait
```

#### Issue: Lambda Function Timeouts
**Symptoms**: Deployments fail at specific steps, Lambda timeout errors in logs
**Root Cause**: Insufficient timeout or resource limits
**Solution**:
```bash
# Check function configuration
aws lambda get-function-configuration --function-name microservice-deployer

# Update timeout and memory
aws lambda update-function-configuration \
  --function-name microservice-deployer \
  --timeout 300 \
  --memory-size 512

# Test fix
python tests/test_lambda_function.py --function microservice-deployer
```

#### Issue: Permission Denied Errors
**Symptoms**: Lambda functions fail with permission errors
**Root Cause**: Missing IAM permissions
**Solution**:
```bash
# Check current permissions
python scripts/audit_iam_permissions.py

# Fix common permission issues
python scripts/fix_lambda_permissions.py

# Verify permissions
python scripts/test_lambda_permissions.py
```

#### Issue: High Deployment Failure Rate
**Symptoms**: Multiple deployments failing, success rate < 90%
**Root Cause**: Various (resource limits, dependency issues, service degradation)
**Investigation Steps**:
```bash
# 1. Check system health
python src/deployment_orchestrator.py health --environment production

# 2. Analyze recent failures
python scripts/analyze_deployment_failures.py --hours 24

# 3. Check AWS service health
python scripts/check_aws_service_health.py

# 4. Review logs
python scripts/analyze_cloudwatch_logs.py --pattern ERROR --hours 6

# 5. Test basic functionality
python tests/scalability_tester.py concurrent-test --concurrent 1
```

### 2. Performance Issues

#### Slow Deployments
**Investigation**:
```bash
# Analyze deployment times
python scripts/analyze_deployment_performance.py --days 7

# Check Lambda cold starts
python scripts/analyze_lambda_cold_starts.py

# Monitor resource utilization
python scripts/check_resource_utilization.py
```

**Optimization Actions**:
```bash
# Optimize Lambda functions
python scripts/optimize_lambda_performance.py

# Increase Lambda memory (reduces execution time)
python scripts/update_lambda_memory.py --memory 1024

# Enable provisioned concurrency for critical functions
python scripts/enable_provisioned_concurrency.py --function deployment-initializer
```

#### High Concurrency Issues
**Symptoms**: Throttling errors, deployment queue buildup
**Solution**:
```bash
# Check current concurrency limits
aws lambda get-account-settings

# Request limit increase
python scripts/request_lambda_limit_increase.py --target-concurrent 100

# Implement batching for high load
python scripts/enable_deployment_batching.py --batch-size 10
```

### 3. Data Issues

#### Configuration Corruption
**Symptoms**: Unexpected deployment behavior, validation errors
**Investigation**:
```bash
# Validate configuration files
python src/dependency_manager.py validate

# Check for syntax errors
python scripts/validate_all_configs.py

# Compare with known good version
git diff HEAD~1 config/
```

**Recovery**:
```bash
# Restore from backup
git checkout HEAD~1 config/

# Apply minimal required changes
python scripts/apply_config_patches.py

# Validate and test
python src/dependency_manager.py validate
python src/deployment_orchestrator.py deploy --environment test --wait
```

---

## 🚨 Emergency Procedures

### 1. Emergency Shutdown

#### Complete System Shutdown
**When to Use**: Critical security incident, data corruption, cascading failures

```bash
# 1. Stop all running deployments
python scripts/emergency_stop_all_deployments.py

# 2. Disable state machine
aws stepfunctions tag-resource \
  --resource-arn arn:aws:states:us-east-1:424470772957:stateMachine:restaurant-deployment-orchestrator2 \
  --tags Key=Status,Value=EmergencyShutdown

# 3. Scale down Lambda concurrency to 0
python scripts/emergency_scale_down_lambdas.py

# 4. Send emergency notification
python scripts/send_emergency_notification.py --level CRITICAL \
  --message "Deployment system emergency shutdown initiated"
```

#### Partial Shutdown (Specific Services)
```bash
# Stop deployments for specific services only
python scripts/stop_service_deployments.py --services auth-service,payment-service

# Block new deployments for these services
python scripts/block_service_deployments.py --services auth-service,payment-service
```

### 2. Emergency Recovery

#### Rapid Recovery Protocol
```bash
# 1. Assess damage
python scripts/emergency_assessment.py --full

# 2. Restore from known good state
python scripts/emergency_restore.py --timestamp "2024-01-15T10:00:00Z"

# 3. Minimal functionality test
python tests/scalability_tester.py concurrent-test --concurrent 1

# 4. Gradual restoration
python scripts/gradual_service_restore.py --start-with auth-service
```

### 3. Communication Procedures

#### Incident Communication
```bash
# Send incident notification
python scripts/send_incident_notification.py \
  --severity HIGH \
  --title "Deployment System Incident" \
  --description "Brief description of issue" \
  --estimated-resolution "2 hours"

# Update incident status
python scripts/update_incident_status.py \
  --incident-id INC-2024-001 \
  --status "Investigating"

# Send resolution notification
python scripts/send_resolution_notification.py \
  --incident-id INC-2024-001 \
  --resolution-summary "Issue resolved, service restored"
```

---

## 🔒 Security Procedures

### 1. Security Monitoring

#### Regular Security Audits
```bash
# Weekly security audit
python scripts/security_audit.py --weekly

# Check for suspicious activity
python scripts/check_suspicious_activity.py --days 7

# Validate IAM permissions
python scripts/audit_iam_permissions.py --detailed
```

#### Security Incident Response
```bash
# Immediate isolation
python scripts/isolate_compromised_functions.py --function-name suspicious-function

# Audit trail analysis
python scripts/analyze_audit_trail.py --incident-time "2024-01-15T14:30:00Z"

# Remediation
python scripts/security_remediation.py --incident-id SEC-2024-001
```

### 2. Access Control

#### User Access Management
```bash
# Review user permissions quarterly
python scripts/review_user_permissions.py --quarter Q1-2024

# Rotate service account keys
python scripts/rotate_service_keys.py --service deployment-orchestrator

# Audit access logs
python scripts/audit_access_logs.py --days 30
```

---

## ⚡ Performance Optimization

### 1. Continuous Optimization

#### Monthly Performance Review
```bash
# Generate performance report
python scripts/generate_performance_report.py --period monthly

# Identify optimization opportunities
python scripts/identify_optimization_opportunities.py

# Apply recommended optimizations
python scripts/apply_performance_optimizations.py --recommendations recommendations.json
```

#### Real-time Optimization
```bash
# Monitor performance metrics
python scripts/monitor_real_time_performance.py

# Auto-scale Lambda concurrency
python scripts/auto_scale_lambda_concurrency.py --enable

# Optimize deployment scheduling
python scripts/optimize_deployment_scheduling.py
```

---

## 💾 Backup & Recovery

### 1. Backup Procedures

#### Daily Backups
```bash
# Configuration backup
python scripts/backup_configurations.py --daily

# State machine definition backup
python scripts/backup_state_machine.py --daily

# Lambda function code backup
python scripts/backup_lambda_functions.py --daily
```

#### Weekly Full Backup
```bash
# Complete system backup
python scripts/full_system_backup.py --weekly

# Verify backup integrity
python scripts/verify_backup_integrity.py --backup-id BACKUP-2024-001

# Test restore procedure
python scripts/test_restore_procedure.py --backup-id BACKUP-2024-001 --dry-run
```

### 2. Recovery Testing

#### Monthly Recovery Drills
```bash
# Simulate disaster scenario
python scripts/simulate_disaster.py --scenario region-failure

# Execute recovery procedure
python scripts/execute_recovery_drill.py --scenario region-failure

# Validate recovery success
python scripts/validate_recovery.py --test-suite full
```

---

## 📞 Contact Information

### Escalation Matrix

| Level | Contact | Response Time | Availability |
|-------|---------|---------------|--------------|
| L1 - Operations | ops-team@company.com | 15 minutes | 24/7 |
| L2 - Engineering | engineering@company.com | 30 minutes | Business hours |
| L3 - Principal Engineer | principal@company.com | 1 hour | On-call |
| L4 - Architecture | architecture@company.com | 2 hours | Business hours |

### Emergency Contacts
- **Critical Issues**: +1-555-CRITICAL
- **Security Incidents**: security@company.com
- **AWS Support**: Case escalation via console

---

## 📚 Additional Resources

- **Runbooks**: `/docs/runbooks/`
- **Architecture Docs**: `/docs/architecture/`
- **Troubleshooting Logs**: `/logs/troubleshooting/`
- **Performance Baselines**: `/docs/performance/`
- **Security Policies**: `/docs/security/`

---

*Last Updated: 2024-01-15*  
*Version: 2.0*  
*Owner: Platform Engineering Team* 