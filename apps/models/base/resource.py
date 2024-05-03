from django.db import models


class ResourceData(models.Model):
    appinstance = models.ForeignKey("AbstractAppInstance", on_delete=models.CASCADE, related_name="resourcedata")
    cpu = models.IntegerField()
    gpu = models.IntegerField()
    mem = models.IntegerField()
    time = models.IntegerField()
