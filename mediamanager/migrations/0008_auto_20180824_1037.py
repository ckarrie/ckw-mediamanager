# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-08-24 10:37
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mediamanager', '0007_auto_20180823_1457'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fileresource',
            name='md_summary',
            field=models.TextField(blank=True, null=True),
        ),
    ]
