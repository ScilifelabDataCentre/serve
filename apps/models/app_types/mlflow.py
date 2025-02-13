from apps.models import AppInstanceManager, BaseAppInstance


class MlflowAppManager(AppInstanceManager):
    model_type = "mlflow"


class MLFlowInstance(BaseAppInstance):
    objects = MlflowAppManager()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app.user_can_see_secrets = True

    def get_k8s_values(self):
        k8s_values = super().get_k8s_values()
        k8s_values["tracking"] = {
            "auth": {
                "enabled": True,
                # "username": self.basic_auth.username,
                # "password": self.basic_auth.password,
            },
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
