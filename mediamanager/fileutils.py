import shutil
import subprocess
import os
import datetime
import thread
from background_task import background

import models


@background
def move_file(src, dst, file_res_id, show_storage_id, so1_id):
    file_res = models.FileResource.objects.get(id=file_res_id)
    dest_show_storage = models.ShowStorage.objects.get(id=show_storage_id)
    so1 = models.StorageDiskOperation.objects.get(id=so1_id)

    try:
        start = datetime.datetime.now()
        # use copy instead of copy2 to avoid copystat()
        # shutil.copyfile(src, dst)
        subprocess.call(["cp", "%s" % src, "%s" % dst])

        took_seconds = int((datetime.datetime.now() - start).total_seconds())


        #start = datetime.datetime.now()
        os.remove(src)

        #took_seconds = int((datetime.datetime.now() - start).total_seconds())
        #if src_disk:
        #    dos.append(models.StorageDiskOperation(disk=src_disk, op_type='rm', file_size=file_size, took_seconds=took_seconds))

    except IOError, e:
        raise e

    file_res.file_path = dst
    file_res.show_storage = dest_show_storage
    file_res.save()

    so1.took_seconds = took_seconds
    so1.save()

    print "* finished moving to", dst


def filesize(path):
    return int(os.stat(path).st_size)


def move_file_thread(src, dst):
    t = thread.start_new_thread(move_file, (src, dst))
    return t
