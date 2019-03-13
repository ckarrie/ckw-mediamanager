import os

from django.views import generic

import models
import admin


class RecordingEndpointView(generic.TemplateView):
    template_name = 'mediamanager/rec_endpoint.html'

    def get_context_data(self, **kwargs):
        ctx = super(RecordingEndpointView, self).get_context_data(**kwargs)
        base_name = self.request.GET.get('fn', None)
        storage_disk_id = self.request.GET.get('sd', None)
        results = {}
        fileresources = []
        episode_resources = []
        show = None

        dest_storage_disk_dori = models.StorageDisk.objects.filter(id=1).first()

        if storage_disk_id:
            storage_disk = models.StorageDisk.objects.filter(id=storage_disk_id).first()
            print "[RecordingEndpointView] storage_disk", storage_disk
            if storage_disk:
                if os.path.exists(storage_disk.path):
                    show_storages = models.ShowStorage.objects.filter(storagefolder__disk=storage_disk)
                    for show_storage in show_storages:
                        fn = os.path.join(show_storage.path, base_name)

                        if os.path.exists(fn):
                            print "[RecordingEndpointView] FOUND in", show_storage.show
                            results = show_storage.scan_files(read_metadata=True, limit_filename=base_name)
                            fileresources = results.get('fileresources', [])
                            show = show_storage.show
                            break
                        else:
                            pass
                        #print "[RecordingEndpointView] Not found in", show_storage.path
                else:
                    print "[RecordingEndpointView] NOT MOUNTED", storage_disk.path

        if not show:
            print "[RecordingEndpointView] NOT PROCESSED", base_name

        for fr in fileresources:
            aa_results = fr.auto_assign()
            episode_resources = aa_results.get('episode_resources', [])
            for episode_resource in episode_resources:
                episode_resource.episode.delete_smaller_duplicates()
                episode_resource.rename_file_res()

                print "[RecordingEndpointView] finished as", episode_resource.file_res.get_basename()

                if dest_storage_disk_dori:
                    dest_storage_disk_dori.admin_show_episode_move_func(
                        admin.ShowEpisodeAdmin(models.ShowEpisode, None),
                        request=self.request,
                        queryset=[episode_resource.episode]
                    )

        ctx.update({
            'fn': base_name,
            'episode_resources': episode_resources
        })
        return ctx

    def get(self, request, *args, **kwargs):
        fn = request.GET.get('fn', None)
        print "[RecordingEndpointView]", fn

        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)
