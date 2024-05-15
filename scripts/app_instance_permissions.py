from guardian.shortcuts import assign_perm, remove_perm

from apps.models import AbstractAppInstance


def run(*args):
    """Reads all AppInstance objects and sets correct permission
    based on owner (user) and the instance access property"""

    for subclass in AbstractAppInstance.__subclasses__():
        app_instances_all = subclass.objects.all()
        for app_instance in app_instances_all:
            owner = app_instance.owner

            if app_instance.access == "private":
                if not owner.has_perm("can_access_app", app_instance):
                    assign_perm("can_access_app", owner, app_instance)
            else:
                if owner.has_perm("can_access_app", app_instance):
                    remove_perm("can_access_app", owner, app_instance)
