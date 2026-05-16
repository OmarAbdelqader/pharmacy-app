# AWS Deployment Checklist

Use this checklist to track your deployment progress.

## Pre-Deployment (Your Computer)

- [ ] Read `AWS_QUICK_START.md`
- [ ] Created an AWS account
- [ ] Installed AWS CLI: `pip install awscli awsebcli`
- [ ] Ran `aws configure` (have your Access Keys ready)
- [ ] Generated SECRET_KEY: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

## AWS Setup

### RDS Database
- [ ] Created PostgreSQL database on RDS named `pharmacy-db`
- [ ] Saved database endpoint (URL)
- [ ] Saved database username: `postgres`
- [ ] Saved database password
- [ ] Created a new database named `pharmacy` in the instance

### S3 Storage
- [ ] Created S3 bucket named `pharmacy-static-xxxxx`
- [ ] Made bucket public (unchecked "Block all public access")
- [ ] Created IAM user `pharmacy-app-user`
- [ ] Created access keys for IAM user
- [ ] Saved Access Key ID and Secret Access Key

### Elastic Beanstalk
- [ ] Created Elastic Beanstalk application
- [ ] Environment created and running (green checkmark)
- [ ] Saved environment URL

## Deployment

- [ ] Updated `.env` file with production values:
  ```
  SECRET_KEY=your-generated-key
  DEBUG=False
  ALLOWED_HOSTS=pharmacy-prod.elasticbeanstalk.com
  USE_POSTGRESQL=True
  DB_NAME=pharmacy
  DB_USER=postgres
  DB_PASSWORD=your-password
  DB_HOST=pharmacy-db.xxxxx.us-east-1.rds.amazonaws.com
  AWS_STORAGE_BUCKET_NAME=pharmacy-static-xxxxx
  AWS_ACCESS_KEY_ID=xxxxx
  AWS_SECRET_ACCESS_KEY=xxxxx
  AWS_S3_REGION_NAME=us-east-1
  ```

- [ ] Committed changes to git
- [ ] Deployed with: `eb deploy`
- [ ] Checked deployment status: `eb status`
- [ ] Connected via SSH: `eb ssh`
- [ ] Ran migrations: `python manage.py migrate`
- [ ] Created superuser: `python manage.py createsuperuser`
- [ ] Exited SSH: `exit`

## Post-Deployment

- [ ] Verified app is running at environment URL
- [ ] Logged in with superuser account
- [ ] Tested adding a medicine in the app
- [ ] Checked that static files load correctly
- [ ] Verified database is working (add test data)

## Monitoring

- [ ] Set up CloudWatch alarms (optional)
- [ ] Configure email notifications for errors
- [ ] Set up automatic backups for RDS

## Custom Domain (Optional)

- [ ] Purchased domain or have existing domain
- [ ] Updated Route 53 DNS records
- [ ] Set custom domain in Elastic Beanstalk
- [ ] Verified HTTPS/SSL working

## Troubleshooting

If deployment fails:

1. Check logs:
   ```powershell
   eb logs
   eb logs --stream  # Real-time logs
   ```

2. Common issues:
   - Database not connecting: Check RDS endpoint and credentials
   - Static files failing: Check S3 bucket name and AWS keys
   - 502 errors: Application crashed, check logs
   - Permission denied: Check IAM user permissions

3. Get help:
   - AWS Support: https://console.aws.amazon.com/support/
   - Django docs: https://docs.djangoproject.com/

## After Deployment

1. Monitor your app regularly
2. Set up backups for your database
3. Keep dependencies updated: `pip list --outdated`
4. Monitor AWS costs in the console
5. Enable billing alerts

---

**Estimated costs**:
- Elastic Beanstalk: $15-30/month
- RDS Database: $15/month
- S3 Storage: $0.50-2/month
- **Total**: ~$30-50/month (less during free tier)
