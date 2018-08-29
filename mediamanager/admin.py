from django.contrib import admin, messages
from django.template.defaultfilters import truncatechars, filesizeformat
from django.urls import reverse
from django.utils.safestring import mark_safe

import time
import os

import models
import forms


class FileServerAdmin(admin.ModelAdmin):
    list_display = ['name', 'webui']


class StorageDiskAdmin(admin.ModelAdmin):
    list_display = ['server', 'name', 'path', 'get_free_size_display', 'get_reserved_disk_space_display', 'get_copy_speed_display']
    actions = ['apply_path_change', 'create_show_folders']

    def apply_path_change(self, request, queryset):
        for sd in queryset:
            for storagefolder in sd.storagefolder_set.all():
                storagefolder_last_folder = os.path.basename(os.path.normpath(storagefolder.path))
                storagefolder.path = os.path.join(sd.path, storagefolder_last_folder) + '/'
                storagefolder.save()

                for showstorage in storagefolder.showstorage_set.all():
                    showstorage_last_folder = os.path.basename(os.path.normpath(showstorage.path))
                    showstorage.path = os.path.join(storagefolder.path, showstorage_last_folder) + '/'
                    showstorage.save()

                    for fileresource in showstorage.fileresource_set.all():
                        fileresource_fn = fileresource.get_basename()
                        fileresource.file_path = os.path.join(showstorage.path, fileresource_fn)

                        if models.FileResource.objects.filter(file_path=fileresource.file_path).exists():
                            pass
                        else:
                            fileresource.save()

    def create_show_folders(self, request, queryset):
        for disk in queryset:
            existing_showstorages = models.ShowStorage.objects.filter(storagefolder__disk=disk, storagefolder__contains='shows')
            existing_shows_ids = []
            for ss in existing_showstorages:
                existing_shows_ids.append(ss.show.id)

            storagefolder = disk.storagefolder_set.filter(contains='shows').first()

            if storagefolder:
                missing_shows = models.Show.objects.all().exclude(id__in=existing_shows_ids)
                for show in missing_shows:
                    disk_show_path = os.path.join(storagefolder.path, show.name)
                    if not os.path.exists(disk_show_path):
                        os.mkdir(disk_show_path)
                        ss_path = disk_show_path + '/'
                        showstorage = models.ShowStorage(show=show, storagefolder=storagefolder, path=ss_path)
                        showstorage.save()
                    else:
                        ss_path = disk_show_path + '/'
                        showstorage = models.ShowStorage(show=show, storagefolder=storagefolder, path=ss_path)
                        showstorage.save()



class StorageFolderAdmin(admin.ModelAdmin):
    list_display = ['disk', 'contains', 'path']


class ShowStorageAdmin(admin.ModelAdmin):
    list_display = ['show', 'storagefolder', 'path']
    actions = ['scan_files', 'scan_files_and_read_metadata', 'cleanup_nonexisting_filesres']
    list_filter = ['storagefolder__disk']

    def scan_files(self, request, queryset, read_metadata=False):
        for ss in queryset:
            results = ss.scan_files(read_metadata=read_metadata)
            self.message_user(request, u'%(ss)s: %(updated)d updated, %(added)d added of %(files)d files' % {
                'ss': ss,
                'updated': results['updated'],
                'added': results['added'],
                'files': results['files'],
            })

    def scan_files_and_read_metadata(self, request, queryset):
        return self.scan_files(request, queryset, read_metadata=True)

    def cleanup_nonexisting_filesres(self, request, queryset):
        for obj in queryset:
            cnt_deleted = obj.cleanup_nonexisting_filesres()
            if cnt_deleted:
                self.message_user(request, u'%(ss)s: cleanup %(fr)d FileResources' % {'ss': obj, 'fr': cnt_deleted})


class FileResourceAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'get_basename', 'get_disk', 'get_size_display', 'file_size',
        'md_title', 'md_duration', 'md_summary', 'md_summary_raw_icon', 'has_episoderesource', 'md_duration_text', 'running_tasks', 'er_list'
    ]

    list_editable = ['md_summary']

    search_fields = ['md_summary', 'md_description', 'file_path']
    readonly_fields = ['get_current_file_size_display', 'get_size_display', 'get_file_process', 'get_file_process_text', 'get_running_tasks']
    actions = ['read_metadata', 'auto_assign', 'delete_from_disk', 'assign_show_storage']
    list_filter = ['show_storage__show', 'show_storage__storagefolder__disk']

    def get_changelist_form(self, request, **kwargs):
        kwargs.setdefault('form', forms.FileResourceAdminForm)
        return super(FileResourceAdmin, self).get_changelist_form(request, **kwargs)

    def read_metadata(self, request, queryset):
        for obj in queryset:
            obj.read_metadata()

    def get_disk(self, obj):
        if obj.show_storage:
            return obj.show_storage.storagefolder.disk
        else:
            return obj.get_folder()

    def auto_assign(self, request, queryset):
        for obj in queryset:
            results = obj.auto_assign()
            created_ers = results['episode_resources']
            if created_ers:
                self.message_user(request, u"Got/Created %(er_cnt)d ER for %(fr)s" % {
                    'fr': obj.get_basename(),
                    'er_cnt': len(created_ers)
                })
            else:
                self.message_user(request, u"No match for %(fr)s" % {
                    'fr': obj.get_basename()
                }, messages.ERROR)

    def running_tasks(self, obj):
        return obj.get_running_tasks().count()

    def has_episoderesource(self, obj):
        return obj.episoderesource_set.exists()

    has_episoderesource.boolean = True

    def er_list(self, obj):
        ers = []
        for er in obj.episoderesource_set.all():
            ers.append(u'<a class="related-widget-wrapper-link change-related" href="%(url)s">%(ep_title)s</a>' % {
                'ep_title': er.episode.name,
                'url': reverse('admin:mediamanager_episoderesource_change', args=(er.id,)) + '?_popup=1',
            })
        return mark_safe(u' | '.join(ers))

    def md_summary_raw_icon(self, obj):
        return mark_safe(u'<img src="/static/admin/img/icon-unknown.svg" title="%(title)s" />' % {
            'title': obj.md_summary_raw
        })

    def md_duration_text(self, obj):
        return time.strftime('%H:%M:%S', time.gmtime(obj.md_duration))

    def delete_from_disk(self, request, queryset):
        for obj in queryset:
            obj.delete_from_disk()
            obj.delete()

    def assign_show_storage(self, request, queryset):
        storages = models.ShowStorage.objects.all()
        for obj in queryset:
            storage = storages.filter(path__icontains=obj.get_folder()).first()
            obj.show_storage = storage
            obj.save()


class ScraperAdmin(admin.ModelAdmin):
    list_display = ['name', 'scraper_source', 'scraper_id']


class ShowAdmin(admin.ModelAdmin):
    list_display = ['name', 'assigned_ers', 'er_by_discs']
    actions = ['fetch_show_data', 'auto_assign']

    def fetch_show_data(self, request, queryset):
        for show in queryset:
            show.fetch_show_data()

            self.message_user(request, u"%(show)s: fetched %(seasons)d seasons with %(episodes)d episodes" % {
                'show': show.name,
                'episodes': models.ShowEpisode.objects.filter(season__show=show).count(),
                'seasons': models.ShowSeason.objects.filter(show=show).count(),
            })

    def assigned_ers(self, obj):
        return mark_safe(u'<a href="%(ers_url)s" title="Episode Resources">%(assigned_ers_cnt)s</a> / <a href="%(files_url)s" title="File Resource">%(files_cnt)s</a> / <a href="%(episodes_url)s" title="Total Episode">%(episodes_cnt)d</a>' % {
            'assigned_ers_cnt': models.EpisodeResource.objects.filter(episode__season__show=obj).count(),
            'files_cnt': models.FileResource.objects.filter(show_storage__show=obj).count(),
            'ers_url': reverse('admin:mediamanager_episoderesource_changelist') + '?episode__season__show__id__exact=' + str(obj.id),
            'files_url': reverse('admin:mediamanager_fileresource_changelist') + '?show_storage__show__id__exact=' + str(obj.id),
            'episodes_url': reverse('admin:mediamanager_showepisode_changelist') + '?season__show__id__exact=' + str(obj.id),
            'episodes_cnt': models.ShowEpisode.objects.filter(season__show=obj).count(),
        })

    assigned_ers.short_description = "ER / FR / Total"

    def auto_assign(self, request, queryset):
        for obj in queryset:
            results = obj.auto_assign()
            writings = results['writings']
            assigned_fileresource_ids = results['assigned_fileresource_ids']

            self.message_user(request, u"%(show)s: assigned %(assigned_fileresources_cnt)d FileResources, writings: %(writings)s" % {
                'show': obj.name,
                'assigned_fileresources_cnt': len(assigned_fileresource_ids),
                'writings': u", ".join([w for w in writings]),
            })

    def er_by_discs(self, obj):
        ers_text = []
        for disk in models.StorageDisk.objects.all():
            ers_qs = models.EpisodeResource.objects.filter(episode__season__show=obj, file_res__show_storage__storagefolder__disk=disk)
            frs_qs = models.FileResource.objects.filter(show_storage__show=obj, show_storage__storagefolder__disk=disk)
            d = {
                'disk': disk.name,
                'cnt_ers': ers_qs.count(),
                'cnt_frs': frs_qs.count(),
            }

            if ers_qs.exists():
                ers_text.append(u'<code>%(disk)s: <span title="found File Resources">%(cnt_frs)03d</span>/<strong title="assigned Episode Resources">%(cnt_ers)03d</strong></code>' % d)
            else:
                ers_text.append(u'<code>%(disk)s: <span title="found File Resources">%(cnt_frs)03d</span>/<span title="assigned Episode Resources">%(cnt_ers)03d</span></code>' % d)
        return mark_safe(u'&nbsp;&nbsp;|&nbsp;&nbsp;'.join(ers_text))


class ShowSeasonAdmin(admin.ModelAdmin):
    list_display = ['show', 'nr']
    list_filter = ['show']


class VideoResFilter(admin.SimpleListFilter):
    title = 'Video Resolution'
    parameter_name = 'vres'

    def lookups(self, request, model_admin):
        return (
            ('sSD', '< SD'),
            ('SD', 'SD'),
            ('HD', 'HD'),
            ('FHD', 'Full HD'),
            ('UHD', 'Ultra HD'),
        )

    def queryset(self, request, queryset):
        v = self.value()
        if v == 'sSD':
            return queryset.filter(episoderesource__file_res__md_video_height__lt=720)
        elif v == 'SD':
            return queryset.filter(episoderesource__file_res__md_video_height=720)
        elif v == 'HD':
            return queryset.filter(episoderesource__file_res__md_video_height__range=(720, 1079))
        elif v == 'FHD':
            return queryset.filter(episoderesource__file_res__md_video_height__range=(1080, 1200))
        elif v == 'UHD':
            return queryset.filter(episoderesource__file_res__md_video_height__range=(1200, 1201))


class ShowEpisodeAdmin(admin.ModelAdmin):
    list_display = ['season_show', 'season', 'nr', 'name', 'orig_name',
                    'episoderesource_cnt', 'get_show_storages_text', 'fr_links']
    list_filter = [
        'season__show',
        'episoderesource__file_res__show_storage__storagefolder__disk',
        'episoderesource__file_res__show_storage__storagefolder__disk__server',
        #'episoderesource__file_res__md_channel',
        'episoderesource__file_res__md_video_height',
        VideoResFilter,
        'season__show__auto_assign_multiep'
    ]
    search_fields = ['name', 'orig_name']
    actions = ['delete_smaller_duplicates', 'delete_greatest_duplicate', 'rename_file_res']

    def get_actions(self, request):
        actions = super(ShowEpisodeAdmin, self).get_actions(request=request)
        for disk in models.StorageDisk.objects.all():
            func = disk.admin_show_episode_move_func
            name = 'move_to_disk' + str(disk.id)
            desc = u"Move to Disk: %(disk)s" % {'disk': disk.name}
            actions[name] = (func, name, desc)

        return actions

    def season_show(self, obj):
        return obj.season.show.name

    def fr_links(self, obj):
        links = []
        for er in obj.episoderesource_set.all():
            links.append(u'<a class="related-widget-wrapper-link change-related" href="%(url)s" title="%(title_episode)s || %(title_file)s">%(id)s</a> (<a href="%(del_url)s">X</a>)' % {
                'url': reverse('admin:mediamanager_fileresource_change', args=(er.file_res.id,)) + '?_popup=1',
                'del_url': reverse('admin:mediamanager_fileresource_delete', args=(er.file_res.id,)),
                'id': er.file_res.id,
                'title_file': er.file_res.md_summary,
                'title_episode': obj.name,

            })
        if links and obj.name:
            links.append(u'<a href="%(search)s" target="_blank"><img src="/static/admin/img/search.svg" /></a>' % {
                'search': reverse('admin:mediamanager_fileresource_changelist') + '?show_storage__show__id__exact=' + str(obj.season.show.id) + '&q=' + obj.name,
            })
        return mark_safe(u"" + u" | ".join(links) + u"")

    def episoderesource_cnt(self, obj):
        return obj.episoderesource_set.count()

    def rename_file_res(self, request, queryset):
        renamed_cnt = 0
        not_completed_cnt = 0
        file_not_exists_cnt = 0

        for obj in queryset:
            for er in obj.episoderesource_set.all():
                results = er.rename_file_res()
                file_exists = results['file_exists']
                is_completed = results['is_completed']
                renamed = results['renamed']

                if renamed:
                    renamed_cnt += 1
                if not file_exists:
                    file_not_exists_cnt += 1
                if not is_completed:
                    not_completed_cnt += 1

        self.message_user(request, u"Renamed %(renamed_cnt)d Files, Not existing files: %(file_not_exists_cnt)d, Not completed files: %(not_completed_cnt)d" % {
            'renamed_cnt': renamed_cnt,
            'file_not_exists_cnt': file_not_exists_cnt,
            'not_completed_cnt': not_completed_cnt,
        })

    def get_show_storages_text(self, obj):
        storages = []
        for er in obj.episoderesource_set.filter(file_res__show_storage__isnull=False):
            storages.append(u'<a href="file://%(file_url)s">%(disk)s</a> (%(size)s, %(duration)s, <span title="%(channel)s">%(channel_short)s</span>, <code><strong>%(video_res)s</strong></code>)' % {
                'disk': er.file_res.show_storage.storagefolder.disk.name,
                'size': er.file_res.get_size_display(),
                'file_url': er.file_res.file_path,
                'duration': time.strftime('%H:%M:%S', time.gmtime(er.file_res.md_duration)),
                'channel_short': truncatechars(er.file_res.md_channel, 10),
                'channel': er.file_res.md_channel,
                'video_res': er.file_res.get_video_resolution_text(),
            })

        return mark_safe(u", ".join(storages))

    def delete_smaller_duplicates(self, request, queryset):
        freed_by_disk = {}
        freed_by_disk_text = []

        for obj in queryset:
            print "Processing deletion for", obj.id
            data_by_disks = obj.delete_smaller_duplicates()
            for k, v in data_by_disks.items():
                if k in freed_by_disk.keys():
                    freed_by_disk[k] += v
                else:
                    freed_by_disk[k] = v

        for k, v in freed_by_disk.items():
            freed_by_disk_text.append(u"%(freed)s on %(disk)s" % {
                'freed': filesizeformat(v),
                'disk': k.name if k else u"unknown"
            })

        self.message_user(request, u"Freed %(text)s" % {
            'text': u", ".join(freed_by_disk_text)
        })

    def delete_greatest_duplicate(self, request, queryset):
        for obj in queryset:
            data_by_disks = obj.delete_greatest_duplicate()


class EpisodeResourceAdmin(admin.ModelAdmin):
    list_display = [
        'episode', 'episode_name',
        'file_base', 'file_md_title', 'file_md_summary',
        'file_md_size', 'get_rename_filename', 'is_renamed',
        'match_similarity', 'match_method'
    ]
    actions = ['delete_from_disk', 'rename_file_res']
    list_filter = ['episode__season__show', 'match_method', 'episode__season__show__auto_assign_multiep']
    raw_id_fields = ['episode', 'file_res']

    def episode_name(self, obj):
        return obj.episode.name

    def file_base(self, obj):
        return obj.file_res.get_basename()

    def file_md_title(self, obj):
        return obj.file_res.md_title

    def file_md_summary(self, obj):
        return truncatechars(obj.file_res.md_summary, 50)

    def file_md_size(self, obj):
        return obj.file_res.get_size_display()

    def delete_from_disk(self, request, queryset):
        for obj in queryset:
            obj.delete_from_disk()

    def rename_file_res(self, request, queryset):
        renamed_cnt = 0
        not_completed_cnt = 0
        file_not_exists_cnt = 0
        for obj in queryset:
            results = obj.rename_file_res()
            file_exists = results['file_exists']
            is_completed = results['is_completed']
            renamed = results['renamed']

            if renamed:
                renamed_cnt += 1
            if not file_exists:
                file_not_exists_cnt += 1
            if not is_completed:
                not_completed_cnt += 1

        self.message_user(request, u"Renamed %(renamed_cnt)d Files, Not existing files: %(file_not_exists_cnt)d, Not completed files: %(not_completed_cnt)d" % {
            'renamed_cnt': renamed_cnt,
            'file_not_exists_cnt': file_not_exists_cnt,
            'not_completed_cnt': not_completed_cnt,
        })


class StorageDiskOperationAdmin(admin.ModelAdmin):
    list_display = ['id', 'disk', 'op_type', 'file_size', 'took_seconds', 'speed', 'created_at']
    list_filter = ['disk']


admin.site.register(models.FileServer, FileServerAdmin)
admin.site.register(models.StorageDisk, StorageDiskAdmin)
admin.site.register(models.StorageFolder, StorageFolderAdmin)
admin.site.register(models.Show, ShowAdmin)
admin.site.register(models.Movie, )
admin.site.register(models.ShowStorage, ShowStorageAdmin)
admin.site.register(models.Scraper, ScraperAdmin)
admin.site.register(models.ShowSeason, ShowSeasonAdmin)
admin.site.register(models.ShowEpisode, ShowEpisodeAdmin)
admin.site.register(models.FileResource, FileResourceAdmin)
admin.site.register(models.EpisodeResource, EpisodeResourceAdmin)
admin.site.register(models.MovieResource, )
admin.site.register(models.StorageDiskOperation, StorageDiskOperationAdmin)
