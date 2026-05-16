# AWS Deployment - Quick Start for Beginners

This guide walks you through deploying your pharmacy app to AWS step-by-step. Estimated time: 30-45 minutes.

## What is AWS?

AWS (Amazon Web Services) is a cloud platform where you can host your website. Think of it like renting a computer from Amazon instead of running one in your office.

## Cost

- **Free tier**: First 12 months include free resources
- **After free tier**: ~$30-50/month for a small app

## Step-by-Step Deployment

### Phase 1: AWS Account Setup (5 minutes)

1. Go to https://aws.amazon.com/
2. Click "Create an AWS Account"
3. Enter your email and create a password
4. Verify your email
5. Add a credit card (for billing, but you get 12 months free)

### Phase 2: Create Your Database (10 minutes)

1. Log in to AWS Console
2. Search for "RDS" and click it
3. Click "Create database"
4. Choose:
   - **Engine**: PostgreSQL
   - **Version**: 15.x (default)
   - **Free tier**: Check "Free tier eligible"
   - **DB instance**: `pharmacy-db`
   - **Username**: `postgres`
   - **Password**: Create a strong one and save it! (example: `Pharmacy@2025#Secure`)
5. Scroll down and click "Create database"
6. Wait 5-10 minutes for it to finish

**Save these details**:
```
Database: pharmacy_db
Username: postgres
Password: YOUR_PASSWORD_HERE
```

### Phase 3: Create Storage Bucket (5 minutes)

1. Search for "S3" in AWS Console
2. Click "Create bucket"
3. Bucket name: `pharmacy-static-yourname` (must be unique, use your initials)
4. Uncheck "Block all public access"
5. Click "Create bucket"

**Save this**:
```
Bucket name: pharmacy-static-yourname
```

### Phase 4: Set Up Web Server (15 minutes)

1. Search for "Elastic Beanstalk" in AWS Console
2. Click "Create application"
3. Choose:
   - **Application name**: `pharmacy-app`
   - **Platform**: Python 3.12
   - **Code**: "Sample application"
4. Click "Create application"
5. Wait for environment to be created (green checkmark appears)

**Save this**:
```
Environment URL: something.elasticbeanstalk.com
```

### Phase 5: Connect Everything

Open your terminal/PowerShell and run:

```powershell
# Install AWS tools
pip install awsebcli awscli

# Configure AWS (you'll need Access Key ID and Secret from AWS Console)
aws configure

# Go to your pharmacy app folder
cd "c:\Users\mohab\Documents\Pharmacy app"

# Generate a secure key for Django
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Copy the output - you'll need it below

# Set environment variables
$env:SECRET_KEY = "PASTE_THE_KEY_YOU_JUST_GENERATED"
$env:DEBUG = "False"
$env:ALLOWED_HOSTS = "pharmacy-app.elasticbeanstalk.com"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = "YOUR_DATABASE_PASSWORD"
$env:DB_HOST = "YOUR_RDS_ENDPOINT" # like: pharmacy-db.xxxxx.us-east-1.rds.amazonaws.com
$env:DB_NAME = "pharmacy"
$env:AWS_STORAGE_BUCKET_NAME = "pharmacy-static-yourname"

# Deploy to AWS
eb deploy
```

### Phase 6: Final Steps

After deployment completes:

```powershell
# Connect to your server and set up database
eb ssh

# Inside the server, run:
python manage.py migrate
python manage.py createsuperuser  # Create admin account

# Exit
exit
```

## How to Access Your App

1. Go to your Elastic Beanstalk environment URL (from step 4)
2. Log in with the superuser account you just created
3. Go to `/admin/` to access the admin panel

## If Something Goes Wrong

Check logs:
```powershell
eb logs  # Shows what happened
```

Common issues:
- **"Connection refused"**: Database not connected - check DB endpoint in settings
- **"Static files not loading"**: S3 bucket name or permissions issue
- **"502 Bad Gateway"**: Application crashed - check logs

## Next Steps

1. Set up a custom domain (optional)
2. Enable HTTPS/SSL (automatic with AWS)
3. Set up monitoring and backups
4. Configure email alerts

## Support

- AWS Documentation: https://docs.aws.amazon.com/
- Django Deployment Guide: https://docs.djangoproject.com/en/5.1/howto/deployment/

Good luck! 🚀
