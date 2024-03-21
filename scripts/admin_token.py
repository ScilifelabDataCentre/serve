import os

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()


def run(*args):
    if not User.objects.filter(email="admin@test.com").exists():
        User.objects.create_superuser("admin", "admin@test.com", os.getenv("DJANGO_SUPERUSER_PASSWORD"))

    admin = User.objects.get(username="admin@test.com")
    admin.set_password(os.getenv("DJANGO_SUPERUSER_PASSWORD"))
    admin.save()

    if not User.objects.filter(email="event_user@test.com").exists():
        User.objects.create_superuser("event_user", "event_user@test.com", os.getenv("EVENT_USER_PASSWORD"))

    event_user = User.objects.get(username="event_user@test.com")
    event_user.set_password(os.getenv("EVENT_USER_PASSWORD"))
    event_user.save()

    try:
        _ = Token.objects.get(user=admin)
    except Token.DoesNotExist:
        _ = Token.objects.create(user=admin)

    try:
        _ = Token.objects.get(user=event_user)
    except Token.DoesNotExist:
        _ = Token.objects.create(user=event_user)
