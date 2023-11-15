import random

from django.conf import settings
from django.db import models


class NewsObject(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=60, default="", primary_key=True)
    body = models.TextField(blank=True, null=True, default="", max_length=2024)

    @property
    def news_body(self):
        return self.body

    @property
    def news_title(self):
        return self.title
