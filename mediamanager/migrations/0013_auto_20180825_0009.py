# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-08-25 00:09
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mediamanager', '0012_auto_20180825_0006'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='episoderesource',
            options={'ordering': ('episode', 'file_res')},
        ),
        migrations.AlterModelOptions(
            name='fileresource',
            options={'ordering': ('show_storage', 'file_path')},
        ),
        migrations.AlterModelOptions(
            name='movieresource',
            options={'ordering': ('movie', 'file_res')},
        ),
    ]