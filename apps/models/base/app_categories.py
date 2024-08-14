from django.db import models


class AppCategories(models.Model):
    name = models.CharField(max_length=512)
    priority = models.IntegerField(default=100)
    slug = models.CharField(max_length=512, default="", primary_key=True)

    def __str__(self):
        return str(self.name)

    class Meta:
        verbose_name = "App Category"
        verbose_name_plural = "App Categories"
