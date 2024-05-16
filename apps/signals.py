from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm
from django.db.models.signals import post_save
from apps.models import (JupyterInstance, RStudioInstance, VSCodeInstance, DashInstance, ShinyInstance, TissuumapsInstance, FilemanagerInstance, CustomAppInstance)

from studio.utils import get_logger
logger = get_logger(__name__)


UID="app_instance_update_permission"

#TODO: Can we make this generic? Using BaseAppInstance as sender does not work in tests
@receiver(post_save, sender=JupyterInstance, dispatch_uid=UID)
@receiver(post_save, sender=RStudioInstance, dispatch_uid=UID)
@receiver(post_save, sender=VSCodeInstance, dispatch_uid=UID)
@receiver(post_save, sender=DashInstance, dispatch_uid=UID)
@receiver(post_save, sender=ShinyInstance, dispatch_uid=UID)
@receiver(post_save, sender=TissuumapsInstance, dispatch_uid=UID)
@receiver(post_save, sender=FilemanagerInstance, dispatch_uid=UID)
@receiver(post_save, sender=CustomAppInstance, dispatch_uid=UID)
def update_permission(sender, instance, created, **kwargs):
    owner = instance.owner

    access = getattr(instance, "access", None)
    
    if access is None:
        logger.error(f"Access not found in {instance}")
        return
    
    if access == "private":
        logger.info(f"Assigning permission to {owner} for {instance}")
        if created or not owner.has_perm("can_access_app", instance):
            assign_perm("can_access_app", owner, instance)

    else:
        if owner.has_perm("can_access_app", instance):
            logger.info(f"Removing permission from {owner} for {instance}")
            remove_perm("can_access_app", owner, instance)
