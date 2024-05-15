from datetime import datetime, timedelta
from django.db.models import Q

from apps.models import AppInstanceManager, BaseAppInstance


class NetpolicyInstanceManager(AppInstanceManager):
    model_type = "netpolicyinstance"
    
    def get_app_instances_of_project_filter(self, user, project, include_deleted=False, deleted_time_delta=None):
        q = Q()

        if not include_deleted:
            if deleted_time_delta is None:
                q &= ~Q(app_status__status="Deleted")
            else:
                time_threshold = datetime.now() - timedelta(minutes=deleted_time_delta)
                q &= ~Q(app_status__status="Deleted") | Q(deleted_on__gte=time_threshold)

        q &= Q(owner=user)
        q &= Q(project=project)

        return q


class NetpolicyInstance(BaseAppInstance):
    objects = NetpolicyInstanceManager()

    def __str__(self):
        return str(self.name)

    class Meta:
        verbose_name = "Network Policy"
        verbose_name_plural = "Network Policies"
        permissions = [("can_access_app", "Can access app service")]