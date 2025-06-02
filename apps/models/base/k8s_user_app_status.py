from django.db import models

K8S_USER_APP_STATUS_CHOICES = [
    ("CrashLoopBackOff", "CrashLoopBackOff"),
    ("ContainerCreating", "ContainerCreating"),
    ("PodInitializing", "PodInitializing"),
    ("ErrImagePull", "ErrImagePull"),
    ("ImagePullBackOff", "ImagePullBackOff"),
    ("PostStartHookError", "PostStartHookError"),
    ("Unknown", "Unknown"),
    ("Running", "Running"),
    ("Deleted", "Deleted"),
]


class K8sUserAppStatus(models.Model):
    info = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=20, null=True, choices=K8S_USER_APP_STATUS_CHOICES)
    time = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "time"
        verbose_name = "k8s User App Status"
        verbose_name_plural = "k8s User App Statuses"

    def __str__(self):
        return f"{str(self.status)} ({str(self.time)})"
