"""
Create superuser automatically on EB deployment
"""
from django.contrib.auth import get_user_model

User = get_user_model()

if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@pharmacy.local', 'admin123')
    print("Superuser created")
else:
    print("Superuser already exists")
