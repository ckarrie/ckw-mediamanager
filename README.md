Media Manager
=============

1. create python 2 venv and install ckw-mediamanager
2. `(mediamanager)christian@nzxt:~/workspace/venvs/mediamanager$ pip install -e ~/src/ckw-mediamanager`
3. `(mediamanager) christian@nzxt:~/workspace/venvs/mediamanager$ pip install django==1.11.9`


Screenshots:

![Shows](showepisodes.png)

List your DVR recorded TV shows

![Episodes](showepisodes.png)

List your Episodes


Start:

    screen -S mm
    
Screen 1:

    cd ~/workspace/venvs/mediamanager
    source bin/activate
    python mm/manage.py process_tasks --queue disk-move-<Name of Storage Device>

Screen 2:

    cd ~/workspace/venvs/mediamanager
    source bin/activate
    python mm/manage.py runserver 0.0.0.0:9003

Resume:

    screen -r mm

Tabs:

    1.: Shows               http://0.0.0.0:9003/admin/mediamanager/show/
    2.: Show storages       http://0.0.0.0:9003/admin/mediamanager/showstorage/
    3.: Episode resources   http://0.0.0.0:9003/admin/mediamanager/episoderesource/
    4.: Show episodes       http://0.0.0.0:9003/admin/mediamanager/showepisode
    5.: File resources      http://0.0.0.0:9003/admin/mediamanager/fileresource/

    x.: Tasks               http://0.0.0.0:9003/admin/background_task/task/
