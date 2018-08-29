#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Christian Karrié <christian@karrie.info>'

from distutils.core import setup

# Dynamically calculate the version based on ccm.VERSION
version_tuple = __import__('mediamanager').VERSION
version = ".".join([str(v) for v in version_tuple])

setup(
    name='ckw_mediamanager',
    description='Django Media Manager',
    version=version,
    author='Christian Karrie',
    author_email='ckarrie@gmail.com',
    url='http://ccm.app/',
    packages=['mediamanager'],
    install_requires=[
        'django<=1.11.9',
        'requests',
        'tvdb_api',
        'enzyme',
        'psycopg2',
        'lxml',
        'django-background-tasks',
        'tmdb3'
    ]
)
