# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-08-29 17:47
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mediamanager', '0016_auto_20180827_1534'),
    ]

    operations = [
        migrations.AddField(
            model_name='showepisode',
            name='orig_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='scraper',
            name='scraper_source',
            field=models.CharField(choices=[(b'imdb', b'ImDB'), (b'thetvdb', b'The TV DB'), (b'themoviedb', b'The Movie DB.org'), (b'fernsehserien.de', b'fernsehserien.de')], max_length=255),
        ),
    ]
