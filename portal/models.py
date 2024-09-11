import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils.text import slugify


class PublicModelObject(models.Model):
    model = models.OneToOneField(settings.MODELS_MODEL, on_delete=models.CASCADE)
    obj = models.FileField(upload_to="models/objects/")
    updated_on = models.DateTimeField(auto_now=True)
    created_on = models.DateTimeField(auto_now_add=True)


class PublishedModel(models.Model):
    name = models.CharField(max_length=512)
    project = models.ForeignKey(settings.PROJECTS_MODEL, on_delete=models.CASCADE)
    model_obj = models.ManyToManyField(PublicModelObject)
    pattern = models.CharField(max_length=255, default="")
    updated_on = models.DateTimeField(auto_now=True)
    created_on = models.DateTimeField(auto_now_add=True)
    collections = models.ManyToManyField("portal.Collection", related_name="published_models", blank=True)

    @property
    def model_description(self):
        desc = None
        for mo in self.model_obj.all():
            desc = mo.model.description
        return desc


@receiver(pre_save, sender=PublishedModel)
def on_project_save(sender, instance, **kwargs):
    if instance.pattern == "":
        published_models = PublishedModel.objects.filter(project=instance.project)

        patterns = published_models.values_list("pattern", flat=True)

        arr = []

        for i in range(1, 31):
            pattern = f"pattern-{i}"

            if pattern not in patterns:
                arr.append(pattern)

        pattern = ""

        if len(arr) > 0:
            rand_index = random.randint(0, len(arr) - 1)

            pattern = arr[rand_index]

        else:
            randint = random.randint(1, 30)
            pattern = f"pattern-{randint}"

        instance.pattern = pattern


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


class EventsObject(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=200, default="")
    description = models.TextField(blank=True, null=True, default="", max_length=2024)
    start_time = models.DateTimeField(auto_now=False, auto_now_add=False)
    end_time = models.DateTimeField(auto_now=False, auto_now_add=False)
    venue = models.CharField(max_length=100, default="")
    speaker = models.CharField(max_length=200, default="")
    registration_url = models.URLField(max_length=200)
    recording_url = models.URLField(blank=True, null=True, max_length=200)

    @property
    def event_title(self):
        return self.title

    @property
    def event_description(self):
        return self.description

    @property
    def event_start_time(self):
        return self.start_time

    @property
    def event_end_time(self):
        return self.end_time

    @property
    def event_venue(self):
        return self.venue

    @property
    def event_speaker(self):
        return self.speaker

    @property
    def event_registration_url(self):
        return self.registration_url

    @property
    def event_recording_url(self):
        return self.recording_url
