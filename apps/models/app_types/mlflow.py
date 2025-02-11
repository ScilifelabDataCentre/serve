from apps.models import AppInstanceManager, BaseAppInstance


class MlflowAppManager(AppInstanceManager):
    model_type = "mlflow"


class MLFlowInstance(BaseAppInstance):
    objects = MlflowAppManager()

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["tracking"] = {
            "auth": {"enabled": True},
            "ingress": {
                "enabled": True,
                "ingressClassName": "nginx",
                "hostname": self.url.split("://")[1] if self.url is not None else self.url,
            },
        }
        return k8s_values

    class Meta:
        verbose_name = "MLFlow App Instance"
        verbose_name_plural = "MLFlow App Instances"
        permissions = [("can_access_app", "Can access app service")]
