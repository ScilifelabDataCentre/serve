from django.contrib.auth import get_user_model
from django.db import models
from django.utils.text import slugify


class Collection(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    maintainer = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name="collection_maintainer",
        null=True,
    )
    name = models.CharField(max_length=200, unique=True, default="")
    description = models.TextField(blank=True, default="", max_length=1000)
    website = models.URLField(max_length=200, blank=True)
    logo = models.ImageField(upload_to="collections/logos/", null=True, blank=True)
    slug = models.SlugField(unique=True, blank=True)
    zenodo_community_id = models.CharField(max_length=200, null=True, blank=True)
    # repositories source would be another field

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super(Collection, self).save(*args, **kwargs)
