import os

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()


def run(*args):
    if not User.objects.filter(email=os.getenv("DJANGO_SUPERUSER_EMAIL")).exists():
        User.objects.create_superuser(
            "admin", os.getenv("DJANGO_SUPERUSER_EMAIL"), os.getenv("DJANGO_SUPERUSER_PASSWORD")
        )

    admin = User.objects.get(username=os.getenv("DJANGO_SUPERUSER_EMAIL"))
    admin.set_password(os.getenv("DJANGO_SUPERUSER_PASSWORD"))
    admin.save()

    if not User.objects.filter(email=os.getenv("EVENT_USER_EMAIL")).exists():
        User.objects.create_superuser("event_user", os.getenv("EVENT_USER_EMAIL"), os.getenv("EVENT_USER_PASSWORD"))

    event_user = User.objects.get(username=os.getenv("EVENT_USER_EMAIL"))
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
