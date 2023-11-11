# Generated by Django 3.2.11 on 2022-06-02 15:18

import tagulous.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('models', '0009_auto_20220201_1137'),
    ]

    operations = [
        migrations.AlterField(
            model_name='model',
            name='tags',
            field=tagulous.models.fields.TagField(_set_tag_meta=True, blank=True, help_text='Enter a comma-separated tag string', to='models.Tagulous_Model_tags'),
        ),
    ]