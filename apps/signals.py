from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from django.db.models.signals import post_save
from apps.models import BaseAppInstance


@receiver(
    post_save,
    sender=BaseAppInstance,
    dispatch_uid="app_instance_update_permission",
)
def update_permission(sender, instance, created, **kwargs):
    """Should work with BaseAppInstance or any subclass of it."""
    owner = instance.owner

    if instance.access == "private":
        if created or not owner.has_perm("can_access_app", instance):
            assign_perm("can_access_app", owner, instance)

    else:
        if owner.has_perm("can_access_app", instance):
            remove_perm("can_access_app", owner, instance)
