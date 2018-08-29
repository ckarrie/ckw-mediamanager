from django.db.models import signals
from django.conf import settings
from django.conf.urls.static import static
import urls


def register_disk_urls():
    from models import StorageDisk

    for sd in StorageDisk.objects.all():
        urls.urlpatterns = urls.urlpatterns + static(str(sd.id), document_root=sd.path, show_indexes=True)

    print urls.urlpatterns


def register_signals(config):
    print "mediamanager.register_signals called for config", config
    register_disk_urls()
