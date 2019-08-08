# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2019-08-01 09:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mediamanager', '0019_episoderesource_created'),
    ]

    operations = [
        migrations.AddField(
            model_name='fileresource',
            name='file_source',
            field=models.CharField(choices=[(b'tv', b'TV (recorded)'), (b'dl', b'Web (downloaded)')], default=b'tv', max_length=2),
        ),
    ]