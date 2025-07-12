import json
import boto3
import os
from datetime import datetime, timezone

def lambda_handler(event, context):
    """
    Lambda function để gửi thông báo về kết quả deployment
    """
    try:
        # Lấy thông tin từ event
        status = event.get('status')  # SUCCESS hoặc FAILED
        deployment_context = event.get('deployment_context', {})
        error = event.get('error')
        services_deployed = event.get('services_deployed', [])
        
        deployment_id = deployment_context.get('deployment_id')
        environment = deployment_context.get('environment', 'unknown')
        version = deployment_context.get('version', 'unknown')
        
        print(f"Sending notification for deployment {deployment_id}: {status}")
        
        # Khởi tạo AWS clients
        sns_client = boto3.client('sns')
        ses_client = boto3.client('ses')
        
        # Tạo nội dung thông báo
        notification_content = create_notification_content(
            status, deployment_id, environment, version, services_deployed, error
        )
        
        # Gửi thông báo qua SNS
        sns_result = send_sns_notification(sns_client, notification_content)
        
        # Gửi email thông báo chi tiết
        email_result = send_email_notification(ses_client, notification_content)
        
        # Ghi log vào CloudWatch
        log_result = log_to_cloudwatch(notification_content)
        
        # Gửi thông báo tới Slack (nếu được cấu hình)
        slack_result = send_slack_notification(notification_content)
        
        result = {
            'statusCode': 200,
            'deployment_id': deployment_id,
            'notification_status': status,
            'notifications_sent': {
                'sns': sns_result,
                'email': email_result,
                'cloudwatch': log_result,
                'slack': slack_result
            },
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message': f'Notifications sent for deployment {status}'
        }
        
        print(f"Notification completed for deployment {deployment_id}")
        return result
        
    except Exception as e:
        error_message = f"Error sending notifications: {str(e)}"
        print(error_message)
        
        return {
            'statusCode': 500,
            'error': error_message,
            'deployment_id': deployment_context.get('deployment_id') if deployment_context else None,
            'message': 'Failed to send notifications'
        }

def create_notification_content(status, deployment_id, environment, version, services_deployed, error):
    """Tạo nội dung thông báo"""
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    if status == 'SUCCESS':
        subject = f"✅ Deployment Thành Công - {deployment_id}"
        
        message = f"""
🎉 DEPLOYMENT THÀNH CÔNG

📋 Thông tin Deployment:
• ID: {deployment_id}
• Environment: {environment}
• Version: {version}
• Thời gian: {timestamp}

✅ Services đã deploy thành công:
{chr(10).join([f'• {service}' for service in services_deployed])}

🔗 Liên kết hữu ích:
• AWS Console: https://console.aws.amazon.com/states/
• CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/
• ECS Console: https://console.aws.amazon.com/ecs/

Deployment đã hoàn thành thành công! Tất cả microservices đang hoạt động bình thường.
        """
        
        slack_color = "good"
        
    else:  # FAILED
        subject = f"❌ Deployment Thất Bại - {deployment_id}"
        
        error_details = ""
        if error:
            error_details = f"\n🔍 Chi tiết lỗi:\n{json.dumps(error, indent=2, ensure_ascii=False)}"
        
        message = f"""
🚨 DEPLOYMENT THẤT BẠI

📋 Thông tin Deployment:
• ID: {deployment_id}
• Environment: {environment}
• Version: {version}
• Thời gian: {timestamp}

❌ Deployment không thành công{error_details}

🔧 Hành động cần thực hiện:
• Kiểm tra CloudWatch Logs để xem chi tiết lỗi
• Xem lại cấu hình services
• Kiểm tra health endpoints
• Rollback nếu cần thiết

🔗 Liên kết troubleshooting:
• AWS Console: https://console.aws.amazon.com/states/
• CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/
• ECS Console: https://console.aws.amazon.com/ecs/

Vui lòng kiểm tra và khắc phục sự cố.
        """
        
        slack_color = "danger"
    
    return {
        'subject': subject,
        'message': message,
        'status': status,
        'deployment_id': deployment_id,
        'environment': environment,
        'version': version,
        'timestamp': timestamp,
        'slack_color': slack_color,
        'services_deployed': services_deployed,
        'error': error
    }

def send_sns_notification(sns_client, content):
    """Gửi thông báo qua SNS"""
    try:
        topic_arn = os.environ.get('SNS_TOPIC_ARN')
        if not topic_arn:
            return {'sent': False, 'reason': 'SNS_TOPIC_ARN not configured'}
        
        response = sns_client.publish(
            TopicArn=topic_arn,
            Subject=content['subject'],
            Message=content['message']
        )
        
        print(f"SNS notification sent: {response['MessageId']}")
        return {
            'sent': True,
            'message_id': response['MessageId'],
            'topic_arn': topic_arn
        }
        
    except Exception as e:
        print(f"Error sending SNS notification: {str(e)}")
        return {'sent': False, 'error': str(e)}

def send_email_notification(ses_client, content):
    """Gửi email thông báo chi tiết"""
    try:
        sender_email = os.environ.get('SENDER_EMAIL')
        recipient_emails = os.environ.get('RECIPIENT_EMAILS', '').split(',')
        
        if not sender_email or not recipient_emails[0]:
            return {'sent': False, 'reason': 'Email configuration not found'}
        
        # Tạo HTML email
        html_body = create_html_email(content)
        
        response = ses_client.send_email(
            Source=sender_email,
            Destination={
                'ToAddresses': [email.strip() for email in recipient_emails if email.strip()]
            },
            Message={
                'Subject': {
                    'Data': content['subject'],
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': content['message'],
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': html_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        
        print(f"Email notification sent: {response['MessageId']}")
        return {
            'sent': True,
            'message_id': response['MessageId'],
            'recipients': recipient_emails
        }
        
    except Exception as e:
        print(f"Error sending email notification: {str(e)}")
        return {'sent': False, 'error': str(e)}

def create_html_email(content):
    """Tạo HTML email đẹp"""
    status_color = "#28a745" if content['status'] == 'SUCCESS' else "#dc3545"
    status_icon = "✅" if content['status'] == 'SUCCESS' else "❌"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{content['subject']}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background-color: {status_color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
            .content {{ padding: 20px; }}
            .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 20px 0; }}
            .info-item {{ padding: 10px; background-color: #f8f9fa; border-radius: 4px; }}
            .services-list {{ background-color: #e8f5e8; padding: 15px; border-radius: 4px; margin: 15px 0; }}
            .error-details {{ background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 4px; margin: 15px 0; }}
            .footer {{ background-color: #f8f9fa; padding: 15px; border-radius: 0 0 8px 8px; text-align: center; font-size: 12px; color: #666; }}
            .btn {{ display: inline-block; padding: 10px 20px; background-color: {status_color}; color: white; text-decoration: none; border-radius: 4px; margin: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{status_icon} Deployment {content['status']}</h1>
                <p>ID: {content['deployment_id']}</p>
            </div>
            <div class="content">
                <div class="info-grid">
                    <div class="info-item">
                        <strong>Environment:</strong><br>
                        {content['environment']}
                    </div>
                    <div class="info-item">
                        <strong>Version:</strong><br>
                        {content['version']}
                    </div>
                    <div class="info-item">
                        <strong>Timestamp:</strong><br>
                        {content['timestamp']}
                    </div>
                    <div class="info-item">
                        <strong>Status:</strong><br>
                        {content['status']}
                    </div>
                </div>
    """
    
    if content['status'] == 'SUCCESS' and content['services_deployed']:
        html += f"""
                <div class="services-list">
                    <h3>✅ Services deployed successfully:</h3>
                    <ul>
                        {''.join([f'<li>{service}</li>' for service in content['services_deployed']])}
                    </ul>
                </div>
        """
    
    if content['status'] == 'FAILED' and content['error']:
        error_str = json.dumps(content['error'], indent=2) if isinstance(content['error'], dict) else str(content['error'])
        html += f"""
                <div class="error-details">
                    <h3>❌ Error Details:</h3>
                    <pre>{error_str}</pre>
                </div>
        """
    
    html += f"""
                <div style="text-align: center; margin: 20px 0;">
                    <a href="https://console.aws.amazon.com/states/" class="btn">AWS Console</a>
                    <a href="https://console.aws.amazon.com/cloudwatch/" class="btn">CloudWatch</a>
                    <a href="https://console.aws.amazon.com/ecs/" class="btn">ECS Console</a>
                </div>
            </div>
            <div class="footer">
                <p>Automated notification from Restaurant Microservices Deployment System</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def log_to_cloudwatch(content):
    """Ghi log chi tiết vào CloudWatch"""
    try:
        cloudwatch_logs = boto3.client('logs')
        log_group = '/aws/stepfunctions/restaurant-deployment'
        log_stream = f'notifications-{content["deployment_id"]}'
        
        log_event = {
            'timestamp': int(datetime.now().timestamp() * 1000),
            'message': json.dumps({
                'event': 'deployment_notification_sent',
                'deployment_id': content['deployment_id'],
                'status': content['status'],
                'environment': content['environment'],
                'version': content['version'],
                'services_deployed': content['services_deployed'],
                'error': content['error'] if content['error'] else None,
                'notification_timestamp': content['timestamp']
            }, ensure_ascii=False, indent=2)
        }
        
        try:
            cloudwatch_logs.create_log_stream(
                logGroupName=log_group,
                logStreamName=log_stream
            )
        except cloudwatch_logs.exceptions.ResourceAlreadyExistsException:
            pass  # Log stream already exists
        
        cloudwatch_logs.put_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            logEvents=[log_event]
        )
        
        print(f"CloudWatch log written to {log_group}/{log_stream}")
        return {'logged': True, 'log_group': log_group, 'log_stream': log_stream}
        
    except Exception as e:
        print(f"Error logging to CloudWatch: {str(e)}")
        return {'logged': False, 'error': str(e)}

def send_slack_notification(content):
    """Gửi thông báo tới Slack"""
    try:
        webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
        if not webhook_url:
            return {'sent': False, 'reason': 'SLACK_WEBHOOK_URL not configured'}
        
        import requests
        
        # Tạo Slack message format
        slack_message = {
            "text": f"Deployment {content['status']}: {content['deployment_id']}",
            "attachments": [
                {
                    "color": content['slack_color'],
                    "title": content['subject'],
                    "fields": [
                        {
                            "title": "Deployment ID",
                            "value": content['deployment_id'],
                            "short": True
                        },
                        {
                            "title": "Environment",
                            "value": content['environment'],
                            "short": True
                        },
                        {
                            "title": "Version",
                            "value": content['version'],
                            "short": True
                        },
                        {
                            "title": "Status",
                            "value": content['status'],
                            "short": True
                        }
                    ],
                    "footer": "Restaurant Deployment System",
                    "ts": int(datetime.now().timestamp())
                }
            ]
        }
        
        if content['status'] == 'SUCCESS' and content['services_deployed']:
            slack_message["attachments"][0]["fields"].append({
                "title": "Services Deployed",
                "value": "\n".join([f"• {service}" for service in content['services_deployed']]),
                "short": False
            })
        
        if content['status'] == 'FAILED' and content['error']:
            error_str = str(content['error'])[:500]  # Limit error message length
            slack_message["attachments"][0]["fields"].append({
                "title": "Error",
                "value": f"```{error_str}```",
                "short": False
            })
        
        response = requests.post(webhook_url, json=slack_message, timeout=10)
        
        if response.status_code == 200:
            print("Slack notification sent successfully")
            return {'sent': True, 'webhook_url': webhook_url[:50] + '...'}
        else:
            return {'sent': False, 'error': f'HTTP {response.status_code}'}
            
    except Exception as e:
        print(f"Error sending Slack notification: {str(e)}")
        return {'sent': False, 'error': str(e)} 