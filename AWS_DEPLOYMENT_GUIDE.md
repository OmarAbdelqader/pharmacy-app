# AWS Deployment Guide for Pharmacy App

This guide will walk you through deploying your Django pharmacy app to AWS using Elastic Beanstalk.

## Prerequisites

1. **Create an AWS Account**: Visit https://aws.amazon.com/ and sign up
2. **Install AWS CLI**: Download from https://aws.amazon.com/cli/
3. **Configure AWS Credentials**: Run `aws configure` in your terminal (you'll need Access Key ID and Secret Access Key from AWS)

## Step 1: Create a PostgreSQL Database on AWS RDS

1. Go to AWS Console → RDS → Databases
2. Click "Create database"
3. Choose:
   - **Engine**: PostgreSQL
   - **Version**: 15.x
   - **DB instance class**: db.t3.micro (free tier eligible)
   - **Storage**: 20 GB (free tier)
   - **DB instance identifier**: pharmacy-db
   - **Master username**: postgres
   - **Master password**: (create a strong password and save it)
4. Click "Create database" and wait 5-10 minutes

**Important**: After database is created, go to Security Groups and allow inbound traffic on port 5432 from your Elastic Beanstalk security group (you'll do this after creating EB).

## Step 2: Create an S3 Bucket for Static Files

1. Go to AWS Console → S3
2. Click "Create bucket"
3. Choose a unique name: `pharmacy-app-static-<your-name>`
4. Uncheck "Block all public access"
5. Click "Create bucket"

## Step 3: Create IAM User for Application

1. Go to AWS Console → IAM → Users
2. Click "Create user": `pharmacy-app-user`
3. Choose "Attach policies directly"
4. Select: `AmazonS3FullAccess` and `AmazonRDSDataFullAccess`
5. Click "Create user"
6. Go to "Security credentials" → "Create access key"
7. Choose "Application running outside AWS"
8. Copy the Access Key ID and Secret Access Key (save these!)

## Step 4: Deploy with Elastic Beanstalk

### Install EB CLI
```bash
pip install awsebcli
```

### Initialize Elastic Beanstalk
```bash
cd "c:\Users\mohab\Documents\Pharmacy app"
eb init -p python-3.12 pharmacy-app --region us-east-1
```

### Create and Deploy Environment
```bash
eb create pharmacy-prod \
  --instance-type t3.micro \
  --envvars SECRET_KEY=your-secret-key,DEBUG=False,ALLOWED_HOSTS=your-domain.com
```

### Configure Environment Variables
Create a `.ebextensions/django.config` file with database and S3 settings.

## Step 5: Configure Production Settings

Your production environment variables should include:
- `SECRET_KEY`: Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `DEBUG=False`
- `ALLOWED_HOSTS=your-domain.elasticbeanstalk.com`
- `DATABASE_URL=postgres://user:password@rds-endpoint:5432/pharmacy_db`
- `AWS_STORAGE_BUCKET_NAME=pharmacy-app-static-xxx`
- `AWS_ACCESS_KEY_ID=xxx`
- `AWS_SECRET_ACCESS_KEY=xxx`

## Step 6: Migrate Database and Create Superuser

```bash
eb ssh
python manage.py migrate
python manage.py createsuperuser
exit
```

## Step 7: Set Up Domain (Optional)

1. Buy a domain from Route 53 or external registrar
2. In Elastic Beanstalk environment, go to "Configuration" → "Domain"
3. Add your custom domain

## Troubleshooting

- **502 Bad Gateway**: Check application logs with `eb logs`
- **Static files not loading**: Verify S3 bucket permissions and AWS credentials
- **Database connection failed**: Check RDS security group allows EB security group
- **Secret key issues**: Regenerate and update in EB environment variables

## Cost Estimate (Monthly)

- Elastic Beanstalk: ~$15-30 (t3.micro)
- RDS PostgreSQL: ~$15 (db.t3.micro)
- S3 storage: ~$0.50-2 (static files)
- **Total**: ~$30-50/month

## Further Reading

- [AWS Elastic Beanstalk Documentation](https://docs.aws.amazon.com/elasticbeanstalk/)
- [Django on AWS](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/create-deploy-python-django.html)
