from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm

from apps.app_registry import APP_REGISTRY
from apps.models import AppStatus, BaseAppInstance, MLFlowInstance
from studio.utils import get_logger

from .tasks import helm_delete

logger = get_logger(__name__)


UID = "app_instance_update_permission"


@receiver(pre_delete, sender=BaseAppInstance)
def pre_delete_helm_uninstall(sender, instance, **kwargs):
    """
    If object is deleted from the database, then we run helm uninstall
    """
    logger.info("PRE DELETING RESOURCES")

    values = instance.k8s_values
    if values:
        helm_delete.delay(values["subdomain"], values["namespace"])
    else:
        logger.error(f"Could not find helm release for {instance}")


# After status of app changes to Deleted, remove subdomain from BaseAppInstance
@receiver(post_save, sender=AppStatus)
def post_delete_subdomain_remove(sender, instance, using, **kwargs):
    if instance.status == "Deleted":
        baseapp_instance = BaseAppInstance.objects.get(app_status=instance)
        baseapp_instance.subdomain = None
        baseapp_instance.save()


@receiver(post_save, sender=MLFlowInstance)
def set_mlflow_user_can_see_secrets(sender, instance, **kwargs):
    instance.app.user_can_see_secrets = True
    instance.app.save()


def update_permission(sender, instance, created, **kwargs):
    owner = instance.owner

    access = getattr(instance, "access", None)

    if access is None and instance.name not in ["project-vol", "project-netpolicy"]:
        logger.error(f"Access not found in {instance}")
        # We do not expect there to be access in case of project-vol and project-netpolicy
        # so we do not show a warning when these are deployed.
        return

    if access == "private":
        logger.info(f"Assigning permission to {owner} for {instance}")
        if created or not owner.has_perm("can_access_app", instance):
            assign_perm("can_access_app", owner, instance)

    else:
        if owner.has_perm("can_access_app", instance):
            logger.info(f"Removing permission from {owner} for {instance}")
            remove_perm("can_access_app", owner, instance)


for model in APP_REGISTRY.iter_orm_models():
    receiver(post_save, sender=model, dispatch_uid=UID)(update_permission)

    """
    What is going on here?
    Well, after a model is saved, we want to update the permission of the owner of the model.
    This signal is triggered after a model is saved, and we  update the permission of the owner of the model.
    But, since we have many types of models, we must add a reciever for all types of models.
    We can do this by iterating over the values of SLUG_MODEL_FORM_MAP,
    which is a dictionary that maps the slug of the model to the model itself.

    Equivalent to doing this:

    @receiver(post_save, sender=JupyterInstance, dispatch_uid=UID)
    @receiver(post_save, sender=DashInstance, dispatch_uid=UID)
    ...
    @receiver(post_save, sender=LastModelInstance, dispatch_uid=UID)
    def update_perrmission(sender, instance, created, **kwargs):
        pass

    """
