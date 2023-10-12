from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from common.models import UserProfile


@receiver(pre_save, sender=User)
def custom_save(sender, instance, **kwargs):
    instance.username = instance.email

