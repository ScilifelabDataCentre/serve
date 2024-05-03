from django.db import models


class AppStatus(models.Model):
    info = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=15, default="Unknown")
    time = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "time"

    def __str__(self):
        return f"{str(self.status)} ({str(self.time)})"
