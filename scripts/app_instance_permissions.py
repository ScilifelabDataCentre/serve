from guardian.shortcuts import assign_perm, remove_perm

from apps.app_registry import APP_REGISTRY
from apps.models import BaseAppInstance


def run(*args):
    """Reads all AppInstance objects and sets correct permission
    based on owner (user) and the instance access property"""

    for orm_model in APP_REGISTRY.iter_orm_models():
        app_instances_all = orm_model.objects.all()
        for app_instance in app_instances_all:
            owner = app_instance.owner

            if getattr(app_instance, "access", False) == "private":
                if not owner.has_perm("can_access_app", app_instance):
                    assign_perm("can_access_app", owner, app_instance)
            else:
                if owner.has_perm("can_access_app", app_instance):
                    remove_perm("can_access_app", owner, app_instance)
