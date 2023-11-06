from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
import os
User = get_user_model()

def run(*args):
    if not User.objects.filter(email='admin@test.com').exists():
        User.objects.create_superuser('admin', 'admin@test.com', os.getenv("DJANGO_SUPERUSER_PASSWORD"))
        
    admin = User.objects.get(username="admin@test.com")
    try:
        _ = Token.objects.get(user=admin)
    except Token.DoesNotExist:
        _ = Token.objects.create(user=admin)
