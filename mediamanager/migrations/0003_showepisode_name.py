# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-08-23 13:29
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mediamanager', '0002_auto_20180823_1204'),
    ]

    operations = [
        migrations.AddField(
            model_name='showepisode',
            name='name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
