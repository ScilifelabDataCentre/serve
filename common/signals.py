from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from common.models import UserProfile


@receiver(pre_save, sender=User)
def custom_save(sender, instance, **kwargs):
    """
    This function is used to set the username of the user to the email address.

    We decided to do that in SS-507, because we want to use the email address as the username,
    but we are in the middle of the project live, so django documention points out that 
    it is a `complicated process to change user model now <https://docs.djangoproject.com/en/4.2/topics/auth/customizing/#changing-to-a-custom-user-model-mid-project>`_
    . So we decided to use this signal to set the username to the email address.

    This call back is registered by ``common.apps.CommonConfig.ready()``
    """
    instance.username = instance.email

