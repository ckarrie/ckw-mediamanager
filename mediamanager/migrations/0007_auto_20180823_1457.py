# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-08-23 14:57
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mediamanager', '0006_auto_20180823_1409'),
    ]

    operations = [
        migrations.AddField(
            model_name='show',
            name='language',
            field=models.CharField(choices=[(b'de', b'Deutsch (de)'), (b'en', b'English (en)')], default=b'de', max_length=3),
        ),
        migrations.AlterUniqueTogether(
            name='show',
            unique_together=set([('name', 'language')]),
        ),
    ]
