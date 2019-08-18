import glob
import os
import re
import shutil
from collections import OrderedDict

from django.apps import apps
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres import search
from django.db import models
from django.template.defaultfilters import filesizeformat, slugify
from django.utils import timezone

from mediamanager import fileutils


class FileServer(models.Model):
    name = models.CharField(max_length=255)
    webui = models.CharField(max_length=255, null=True, blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ('name',)


class StorageDisk(models.Model):
    server = models.ForeignKey(FileServer)
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=255)

    def get_free_size(self):
        import subprocess
        df = subprocess.Popen(["df", self.path], stdout=subprocess.PIPE)
        output = df.communicate()[0]
        try:
            device, size, used, available, percent, mountpoint = \
                output.split("\n")[1].split()

            if available:
                return int(available) * 1024
        except IndexError:
            pass
        return 0

    def get_reserved_disk_space(self):
        reserved_filesizes_by_disk_ops = self.storagediskoperation_set.filter(
            took_seconds=-1
        ).aggregate(sum_file_size=models.Sum('file_size')).get('sum_file_size')
        if not reserved_filesizes_by_disk_ops:
            reserved_filesizes_by_disk_ops = 0
        return reserved_filesizes_by_disk_ops

    def get_reserved_disk_space_display(self):
        return filesizeformat(self.get_reserved_disk_space())

    def get_copy_speed_display(self):
        ops = self.storagediskoperation_set.filter(op_type='cp', took_seconds__gt=1, speed__gt=1).aggregate(
            min=models.Min('speed'),
            max=models.Max('speed'),
            avg=models.Avg('speed'),
        )
        ops_text = []
        for k, v in ops.items():
            ops_text.append(u'%(k)s %(v_filesize)s/s' % {
                'k': k,
                'v_filesize': filesizeformat(v or 0),
            })
        return u', '.join(ops_text)

    def get_free_size_display(self):
        return filesizeformat(self.get_free_size())

    def admin_show_episode_move_func(self, modeladmin, request, queryset):
        for show_episode in queryset:
            other_ers = show_episode.episoderesource_set.filter(
                file_res__show_storage__isnull=False
            ).exclude(
                file_res__show_storage__storagefolder__disk=self
            )
            destination_disk = self

            size_to_move = 0
            for er in other_ers:
                size_to_move += er.file_res.file_size

            reserved_filesizes_by_disk_ops = destination_disk.get_reserved_disk_space()
            available_destination_disk_size = destination_disk.get_free_size() - reserved_filesizes_by_disk_ops

            if available_destination_disk_size <= size_to_move:
                modeladmin.message_user(request, u"No Space left on %(disk)s %(disk_space)s, need %(need_space)s (Reserved: %(reserved_space)s)" % {
                    'disk': unicode(destination_disk),
                    'disk_space': filesizeformat(available_destination_disk_size),
                    'need_space': filesizeformat(size_to_move),
                    'reserved_space': filesizeformat(reserved_filesizes_by_disk_ops),
                }, level=messages.ERROR)

            else:

                if other_ers.count() > 1:
                    modeladmin.message_user(request, u"Multiple Episode Resources for %(show_episode)s" % {
                        'show_episode': show_episode,
                    }, level=messages.ERROR)

                else:
                    for er in other_ers:
                        if not er.is_renamed():
                            modeladmin.message_user(request, u"Skipped, %(show_episode)s is not renamed" % {
                                'show_episode': unicode(er.episode),
                            }, level=messages.INFO)

                        else:

                            running_tasks = er.file_res.get_running_tasks()
                            has_running_tasks = running_tasks.exists()

                            if has_running_tasks:
                                modeladmin.message_user(request, u"Skipped, has %(tasks)d running task(s)" % {
                                    'tasks': running_tasks.count(),
                                }, level=messages.INFO)

                            else:

                                source_path = er.file_res.get_folder()
                                source_file_path = er.file_res.file_path
                                source_show_storage = er.file_res.show_storage
                                dest_show_storage = er.episode.season.show.showstorage_set.filter(storagefolder__disk=destination_disk).first()
                                if dest_show_storage:
                                    dest_path = dest_show_storage.path
                                    dest_file_path = os.path.join(dest_path, er.file_res.get_basename())

                                    if os.path.exists(dest_file_path):

                                        if os.path.exists(source_file_path):
                                            source_file_size = fileutils.filesize(source_file_path)
                                        else:
                                            source_file_size = fileutils.filesize(dest_file_path)

                                        if source_file_size == fileutils.filesize(dest_file_path):
                                            if os.path.exists(source_file_path):
                                                os.remove(source_file_path)
                                            er.file_res.file_path = dest_file_path
                                            er.file_res.show_storage = dest_show_storage
                                            er.file_res.save()

                                            modeladmin.message_user(request, u"Same file already exists on %(disk)s, removed source file, freed %(freed)s" % {
                                                'disk': unicode(destination_disk),
                                                'freed': filesizeformat(source_file_size)
                                            }, level=messages.INFO)

                                        else:
                                            os.remove(dest_file_path)
                                            modeladmin.message_user(request, u"Deleted %(dest)s, retrying..." % {
                                                'dest': dest_file_path,
                                            }, level=messages.INFO)
                                            self.admin_show_episode_move_func(modeladmin, request, queryset)

                                    else:
                                        if os.path.exists(source_file_path):
                                            file_size = fileutils.filesize(source_file_path)
                                            dest_disk = dest_show_storage.storagefolder.disk
                                            so1 = StorageDiskOperation(disk=dest_disk, op_type='cp', file_size=file_size, took_seconds=-1)
                                            so1.save()
                                            queue_name = u'disk-move-%(disk)s' % {'disk': dest_disk.name}
                                            task = fileutils.move_file(
                                                source_file_path,
                                                dest_file_path,
                                                er.file_res.id,
                                                dest_show_storage.id,
                                                so1.id,
                                                queue=queue_name
                                            )
                                            task.creator_content_type = ContentType.objects.get_for_model(er.file_res)
                                            task.creator_object_id = er.file_res.id
                                            task.save()

                                            modeladmin.message_user(request, u"Moving %(uc)s from %(source_path)s to %(dest_path)s" % {
                                                'uc': er.file_res.get_basename(),
                                                'source_path': source_path,
                                                'dest_path': dest_path,
                                            })
                                        else:
                                            pass
                                else:
                                    modeladmin.message_user(request, u"No ShowStorage found for Show %(show)s at Disk %(disk)s" % {
                                        'show': unicode(er.episode.season.show),
                                        'disk': unicode(destination_disk),
                                    }, level=messages.WARNING)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ('server', 'name')


class StorageDiskOperation(models.Model):
    disk = models.ForeignKey(StorageDisk)
    op_type = models.CharField(max_length=255, choices=(
        ('cp', 'Copy'),
        ('rm', 'Remove'),
    ))
    file_size = models.BigIntegerField(default=-1)
    took_seconds = models.BigIntegerField(default=-1)
    speed = models.BigIntegerField(default=-1)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.took_seconds > 0:
            self.speed = self.file_size / self.took_seconds
        super(StorageDiskOperation, self).save(*args, **kwargs)


class StorageFolder(models.Model):
    disk = models.ForeignKey(StorageDisk)
    contains = models.CharField(max_length=255, choices=(
        ('movies', 'Movies'),
        ('shows', 'Shows'),
    ))
    path = models.CharField(max_length=255)

    def __unicode__(self):
        return self.path

    def is_online(self):
        return os.path.exists(self.path)

    def get_usage_size(self):
        return fileutils.get_path_size(start_path=self.path)

    def get_free_size(self):
        return 0

    class Meta:
        ordering = ('disk', 'contains')


class Show(models.Model):
    name = models.CharField(max_length=255)
    scrapers = models.ManyToManyField('mediamanager.Scraper', blank=True)
    language = models.CharField(max_length=3, choices=(
        ('de', 'Deutsch (de)'),
        ('en', 'English (en)'),
    ), default='de')
    auto_assign_multiep = models.BooleanField(default=False)
    auto_assign_multiep_sep = models.CharField(default=u' / ', max_length=100)

    def __unicode__(self):
        return self.name

    def fetch_show_data(self):
        for scraper in self.scrapers.all():
            scraper.process_show(show=self)

    def read_showstorages(self):
        results = OrderedDict()
        for showstorage in self.showstorage_set.all():
            print " - Looking up Files in", showstorage
            ss_results = showstorage.scan_files(read_metadata=True)
            results[showstorage] = ss_results
        return results

    def auto_assign(self):
        matched_show_fileresources = FileResource.objects.annotate(
            md_title_similarity=search.TrigramSimilarity(
                'md_title', self.name
            )
        ).filter(md_title_similarity__gt=0.4).order_by('-md_title_similarity')
        show_writings = list(set([fr.md_title for fr in matched_show_fileresources]))
        assigned_fileresource_ids = []

        print "Writings"
        for msf in matched_show_fileresources:
            print "  - ", msf.md_title, msf.md_title_similarity * 100., "%"

        fileresources = FileResource.objects.filter(show_storage__show=self)
        for fr in fileresources:
            results = fr.auto_assign()
            if results['episode_resources']:
                assigned_fileresource_ids.append(fr.id)

        return {
            'writings': show_writings,
            'assigned_fileresource_ids': assigned_fileresource_ids,
        }

    class Meta:
        unique_together = ('name', 'language')
        ordering = ('name', 'language')


class Movie(models.Model):
    name = models.CharField(max_length=255)
    scrapers = models.ManyToManyField('mediamanager.Scraper', blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ('name',)


class ShowStorage(models.Model):
    show = models.ForeignKey(Show)
    storagefolder = models.ForeignKey(StorageFolder)
    path = models.CharField(max_length=255)

    def __unicode__(self):
        return self.path

    def scan_files(self, read_metadata=False, limit_filename=None):
        results = {
            'added': 0,
            'updated': 0,
            'files': 0,
            'fileresources': []
        }

        dl_keywords = [
            '.WEBDL.',
            '.WEB-DL.',
            '.x264-',
            '.x264.',
            '.h264-',
            '.h264.',
            '.DUBBED.',
            '.SUBBED.',
            '.GERMAN.',
            '.1080p.',
            '.720p.',
            '.DVD.',
            '.BLURAY.',
            '.AmazonHD.',
            '.NetflixHD.',
            '.WEBRIP.',
        ]
        dl_keywords = [kw.lower() for kw in dl_keywords]

        videofiles = []
        if limit_filename:
            videofile = os.path.join(self.path, limit_filename)
            if os.path.exists(videofile):
                videofiles = [videofile]

        else:
            video_file_types = ['*.mkv', '*.flv', '*.avi', '*.m4v', '*.mp4']
            for file_type in video_file_types:
                for videofile in glob.glob(self.path + file_type):
                    videofiles.append(videofile)

        for videofile in videofiles:
            videofile_filename = os.path.basename(videofile).lower()
            fr_source = 'tv'
            for kw in dl_keywords:
                if kw in videofile_filename:
                    fr_source = 'dl'

            fr, fr_created = FileResource.objects.get_or_create(
                file_path=videofile,
                defaults={
                    'show_storage': self,
                    'file_source': fr_source
                }
            )
            results['fileresources'].append(fr)
            try:
                size = int(os.stat(videofile).st_size)
            except OSError:
                size = -1
            if fr_created:
                results['added'] += 1
            if fr.file_size == -1:
                fr.file_size = size
                fr.save()
                results['updated'] += 1

            if read_metadata:
                fr.read_metadata()

            results['files'] += 1

        return results

    def get_folder_size(self):
        size = self.fileresource_set.filter(file_size__gt=0).aggregate(size_sum=models.Sum('file_size')).get('size_sum') or 0
        return size

    def cleanup_nonexisting_filesres(self):
        cnt_deleted = 0
        for fr in self.fileresource_set.all():
            exists = fr.file_exists()
            is_completed = fr.is_completed()
            if not exists or not is_completed:
                fr.delete_from_disk()
                fr.delete()
                cnt_deleted += 1
        return cnt_deleted

    class Meta:
        ordering = ('show', 'storagefolder')


class Scraper(models.Model):
    name = models.CharField(max_length=255)
    scraper_source = models.CharField(max_length=255, choices=(
        ('imdb', 'ImDB'),
        ('thetvdb', 'The TV DB'),
        ('themoviedb', 'The Movie DB.org'),
        ('fernsehserien.de', 'fernsehserien.de'),
    ))
    scraper_id = models.IntegerField(null=True, blank=True)
    scraper_url = models.CharField(max_length=255, null=True, blank=True, help_text="With tailing /")
    scraper_priority = models.IntegerField(default=0)
    orig_language = models.CharField(max_length=3, choices=(
        ('de', 'Deutsch (de)'),
        ('en', 'English (en)'),
    ), default='en')

    def __unicode__(self):
        return self.name

    def scrape_thetvdb(self, show, language='de'):
        import tvdb_api

        print "Fetching data from tvdb_api", show, language

        t = tvdb_api.Tvdb(language=language)
        t._getShowData(self.scraper_id, language)
        t_show = t.shows.get(self.scraper_id)

        is_orig_lang = language == self.orig_language

        print " - is_orig_lang", is_orig_lang, language, "==", self.orig_language

        for season_nr, episodes in t_show.items():
            show_season, show_season_created = ShowSeason.objects.get_or_create(
                show=show,
                nr=season_nr
            )
            for episode_nr, episode_data in episodes.items():
                field = 'name'
                if is_orig_lang:
                    field = 'orig_name'
                episode_name = episode_data.get(u'episodeName', None)
                show_episode, show_episode_created = ShowEpisode.objects.get_or_create(
                    season=show_season,
                    nr=episode_nr,
                    defaults={
                        field: episode_name
                    }
                )
                current_name = getattr(show_episode, field)
                if episode_name != current_name:
                    setattr(show_episode, field, episode_name)
                    show_episode.save()

    def scrape_themovie_db(self, show, language='de'):
        from mediamanager.scrapers import themoviedb
        is_orig_lang = language == self.orig_language
        results = themoviedb.scrape_show(self.scraper_id, language=language)

        for season_nr, episodes in results.items():
            show_season, show_season_created = ShowSeason.objects.get_or_create(
                show=show,
                nr=season_nr
            )
            for episode_nr, episode_name in episodes.items():
                field = 'name'
                if is_orig_lang:
                    field = 'orig_name'
                show_episode, show_episode_created = ShowEpisode.objects.get_or_create(
                    season=show_season,
                    nr=episode_nr,
                    defaults={
                        field: episode_name
                    }
                )

                current_name = getattr(show_episode, field)
                if episode_name != current_name:
                    setattr(show_episode, field, episode_name)
                    show_episode.save()

    def scrape_fernsehserien_de(self, show):
        from mediamanager.scrapers import fernsehserien
        row_data = fernsehserien.scrape(self.scraper_url)
        data_cnt = len(row_data)
        matched_cnt = 0
        match_similarity = 0.6
        assign_similarity = 0.7
        for episode_dict in row_data:
            orig_name = episode_dict['orig_title']
            assign_name = episode_dict['title']
            if assign_name:
                orig_name_matched_episodes = ShowEpisode.objects.annotate(
                    similarity=search.TrigramSimilarity(
                        'orig_name', orig_name
                    )
                ).filter(
                    similarity__gt=match_similarity,
                    orig_name__isnull=False,
                    name__isnull=True,
                    season__show=show
                ).order_by('-similarity')

                first_match = orig_name_matched_episodes.filter(similarity__gt=assign_similarity).first()
                # print "Matched FS.de orig_title", orig_name, "with ShowEpisode", orig_name_matched_episodes, first_match
                if first_match:
                    matched_cnt += 1
                    first_match.name = episode_dict['title']
                    first_match.save()

                else:
                    lower_matched = orig_name_matched_episodes.filter(similarity__lte=assign_similarity)
                    if lower_matched.exists():
                        print " - Lower for", orig_name
                        for low_ep in lower_matched:
                            print "   - ", low_ep, low_ep.orig_name

        print "Matched %d of %d (sim=%f)" % (matched_cnt, data_cnt, match_similarity)

    def process_show(self, show):
        if self.scraper_source == 'thetvdb' and self.scraper_id:
            if show.language != self.orig_language:
                # get orig language first
                self.scrape_thetvdb(show, language=self.orig_language)
            self.scrape_thetvdb(show)
        elif self.scraper_source == 'themoviedb' and self.scraper_id:
            if show.language != self.orig_language:
                self.scrape_themovie_db(show, language=self.orig_language)
            self.scrape_themovie_db(show)
        elif self.scraper_source == 'fernsehserien.de' and self.scraper_url:
            return self.scrape_fernsehserien_de(show)

    class Meta:
        ordering = ('name', 'scraper_priority', 'scraper_source')


class ShowSeason(models.Model):
    show = models.ForeignKey(Show)
    nr = models.IntegerField()

    def __unicode__(self):
        return u'%(show)s EP %(nr)s' % {
            'show': self.show.name,
            'nr': self.nr,
        }

    class Meta:
        ordering = ('show', 'nr')


class ShowEpisode(models.Model):
    season = models.ForeignKey(ShowSeason)
    nr = models.IntegerField()
    name = models.CharField(max_length=255, null=True, blank=True)
    orig_name = models.CharField(max_length=255, null=True, blank=True)

    def __unicode__(self):
        return u'%(show)s %(ep_nr)sx%(nr)s' % {
            'show': self.season.show.name,
            'ep_nr': self.season.nr,
            'nr': self.nr,
        }

    def delete_smaller_duplicates(self):
        episoderesources = self.episoderesource_set.all()
        freed_disk_space_by_discs = {}
        failed_deleted_files = []
        if episoderesources.count() > 1:
            all_by_size = episoderesources.order_by('-file_res__file_size')
            if self.season.show.auto_assign_multiep:
                duplicate_fr_ids = []
                matched_fileresources = []
                for er in episoderesources:
                    matched_fileresources.append(er.file_res)

                fr_episodes = OrderedDict()
                for fr in matched_fileresources:
                    fr_episodes_qs = ShowEpisode.objects.filter(episoderesource__file_res=fr).order_by('pk')
                    episodes_list = list(set([ep.id for ep in fr_episodes_qs]))
                    key = fr.id
                    if key in fr_episodes.keys():
                        fr_episodes[key] = list(set(fr_episodes[key] + episodes_list))
                    else:
                        fr_episodes[key] = episodes_list

                for fr_id, episodes_ids in fr_episodes.items():
                    other_frs = FileResource.objects.filter(episoderesource__episode__id__in=episodes_ids).exclude(id=fr_id).distinct()
                    other_frs_ids = list(other_frs.values_list('id', flat=True))
                    duplicate_fr_ids.extend(other_frs_ids)
                    print self, "other_frs", other_frs.count(), other_frs_ids

                all_by_size = FileResource.objects.filter(id__in=duplicate_fr_ids).order_by('-file_size')
                print self, "to delete (except first)", all_by_size.values_list('id', flat=True)
                for fr in all_by_size[1:]:
                    show_storage = fr.show_storage
                    if show_storage:
                        disk = show_storage.storagefolder.disk
                    else:
                        disk = None
                    if disk in freed_disk_space_by_discs.keys():
                        freed_disk_space_by_discs[disk] += fr.file_size
                    else:
                        freed_disk_space_by_discs[disk] = fr.file_size
                    file_deleted = fr.delete_from_disk()
                    if file_deleted:
                        fr.delete()
                    else:
                        failed_deleted_files.append(fr)

            else:
                smaller = all_by_size[1:]
                for small in smaller:
                    show_storage = small.file_res.show_storage
                    if show_storage:
                        disk = show_storage.storagefolder.disk
                    else:
                        disk = None

                    if disk in freed_disk_space_by_discs.keys():
                        freed_disk_space_by_discs[disk] += small.file_res.file_size
                    else:
                        freed_disk_space_by_discs[disk] = small.file_res.file_size

                    file_deleted = small.delete_from_disk()
                    if not file_deleted:
                        failed_deleted_files.append(small)

        # print "small_frs", small_frs
        return freed_disk_space_by_discs, failed_deleted_files

    def delete_greatest_duplicate(self):
        episoderesources = self.episoderesource_set.all()
        freed_disk_space_by_discs = {}
        if episoderesources.count() > 1:
            all_by_size = episoderesources.order_by('-file_res__file_size')
            greatest = all_by_size.first()
            greatest.delete_from_disk()

    class Meta:
        ordering = ('season', 'nr')


class FileResource(models.Model):
    file_path = models.CharField(max_length=500, unique=True)
    file_size = models.BigIntegerField(default=-1)
    file_source = models.CharField(default='tv', max_length=2, choices=(
        ('tv', 'TV (recorded)'),
        ('dl', 'Web (downloaded)'),
    ))
    md_title = models.CharField(max_length=255, null=True, blank=True)
    md_duration = models.BigIntegerField(default=-1)
    md_video_width = models.IntegerField(default=-1)
    md_video_height = models.IntegerField(default=-1)
    md_summary = models.TextField(null=True, blank=True)
    md_summary_raw = models.TextField(null=True, blank=True)
    md_channel = models.CharField(max_length=500, null=True, blank=True)
    md_description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True, auto_now_add=True)

    show_storage = models.ForeignKey(ShowStorage, null=True, blank=True)
    """
    status = models.IntegerField(default=0, choices=(
        (0, 'New'),
        (10, 'Reading Metadata'),
        (11, 'Failed reading Metadata'),
        (12, 'Metadata read'),
        (20, 'Moving file'),
        (21, 'Moving file failed'),
        (22, 'File moved'),
    ))
    """

    def __unicode__(self):
        return self.file_path

    def get_basename(self):
        return os.path.basename(self.file_path)

    def get_folder(self):
        return os.path.dirname(self.file_path)

    def get_running_tasks(self):
        return apps.get_model('background_task.Task').objects.filter(
            creator_object_id=self.id,
            creator_content_type=ContentType.objects.get_for_model(self)
        )

    def get_video_resolution_text(self):
        h = self.md_video_height
        if h > 0:
            if h < 720:
                return u'SD'
            if 720 <= h < 1080:
                return u'HD'
            if h >= 1080:
                return u'Full HD'
        return u"LOW"

    def get_file_process(self):
        saved_size = self.file_size
        task_process = self.get_running_tasks().first()
        current = saved_size
        if task_process:
            params = eval(task_process.task_params)
            dest_path = params[0][1]
            if os.path.exists(dest_path):
                current = fileutils.filesize(dest_path)
            else:
                current = 0
        if saved_size == 0:
            return 0
        return (float(current) / float(saved_size)) * 100.

    def is_completed(self):
        return self.get_file_process() == 100.

    def get_file_process_text(self):
        disk = u"Unkn"
        if self.show_storage:
            disk = self.show_storage.storagefolder.disk.name
        return u"From %(disk)s @ %(proc).1f%%" % {'proc': self.get_file_process(), 'disk': disk}

    def get_current_file_size(self):
        size = -1
        if self.file_exists():
            size = fileutils.filesize(self.file_path)
            if size == 0:
                size = -1
        return size

    def get_current_file_size_display(self):
        return filesizeformat(self.get_current_file_size())

    def get_size_display(self):
        return filesizeformat(self.file_size)

    def file_exists(self):
        return os.path.exists(self.file_path)

    def read_metadata(self):
        if self.file_exists():
            if self.file_path.endswith('.mkv'):
                import enzyme
                try:
                    with open(self.file_path, 'rb') as f:
                        mkv = enzyme.MKV(f)
                        self.md_title = mkv.info.title
                        if mkv.info.duration:
                            self.md_duration = mkv.info.duration.total_seconds()
                        else:
                            self.md_duration = -1
                        vtrack = mkv.video_tracks[0]
                        self.md_video_width = vtrack.width
                        self.md_video_height = vtrack.height
                        for tag in mkv.tags:
                            for st in tag.simpletags:
                                if st.name == 'TVCHANNEL':
                                    self.md_channel = st.string[:500]
                                elif st.name == 'SUMMARY':
                                    string = st.string[:500]
                                    if string and u', ' in string:
                                        if string.count(u", ") >= 2:
                                            string_list = string.split(u", ")
                                            string = u", ".join(string_list[:len(string_list) - 2])
                                    if not self.md_summary:
                                        self.md_summary = string
                                    self.md_summary_raw = st.string
                                elif st.name == 'DESCRIPTION':
                                    self.md_description = st.string
                        self.save()
                except (IOError, enzyme.MalformedMKVError):
                    print "Error reading", self.file_path

    def assign_by_filename(self):
        matched_show = None
        episode_resource = None
        if self.show_storage:
            matched_show = self.show_storage.show

        if matched_show:
            fn = self.get_basename()

            seas_ep_match = re.findall(r"(?:s|season|-)(\d{2})(?:e|x|episode|\n)(\d{2})", fn, re.I)
            if seas_ep_match:
                season_int = int(seas_ep_match[0][0])
                episode_int = int(seas_ep_match[0][1])
                matched_episode = ShowEpisode.objects.filter(season__show=matched_show, season__nr=season_int, nr=episode_int).first()
                if matched_episode:
                    episode_resource, er_created = EpisodeResource.objects.get_or_create(
                        episode=matched_episode,
                        file_res=self,
                        defaults={
                            'match_similarity': 1,
                            'match_method': u'v3,assign_by_filename'
                        }
                    )
                    return episode_resource

            seps = [
                u' (odc. ',
                u'x',
                u'-afl ',  # hollandse, KetOp12
                u'-ep ',  # french, Boomerang
            ]
            part_a, part_b = None, None
            for sep in seps:
                if sep in fn:
                    try:
                        splitted = fn.split(sep)
                        part_a, part_b = splitted[0:2]
                    except IndexError:
                        pass

            if part_a and part_b:
                part_a_ints = [int(a) for a in re.findall('\d+', part_a)]
                part_b_ints = [int(b) for b in re.findall('\d+', part_b)]
                part_a_int, part_b_int = None, None
                if part_a_ints:
                    part_a_int = part_a_ints[-1]
                if part_b_ints:
                    part_b_int = part_b_ints[0]

                if part_a_int is not None and part_b_int is not None:
                    matched_episode = ShowEpisode.objects.filter(season__show=matched_show, season__nr=part_a_int, nr=part_b_int).first()
                    if matched_episode:
                        episode_resource, er_created = EpisodeResource.objects.get_or_create(
                            episode=matched_episode,
                            file_res=self,
                            defaults={
                                'match_similarity': 1,
                                'match_method': u'v3,assign_by_filename'
                            }
                        )

        return episode_resource

    def assign_by_title_in_filename(self):
        """

        :return:
        """
        matched_show = None
        episode_resource = None
        if self.show_storage:
            matched_show = self.show_storage.show

        if matched_show:
            fn = self.get_basename()
            if '.' in fn:
                show_title = fn.split('.')[0]
                episode_title = fn.split('.')[1]
                if ' - ' in show_title:
                    show_title = show_title.split(' - ')[0]

                if episode_title:
                    print "Looking up '%s'" % episode_title
                    matched_episodes = ShowEpisode.objects.annotate(
                        name_similarity=search.TrigramSimilarity(
                            'name', episode_title
                        ),
                        orig_name_similarity=search.TrigramSimilarity(
                            'orig_name', episode_title
                        )
                    ).filter(
                        models.Q(name__isnull=False) | models.Q(orig_name__isnull=False),
                        season__show=matched_show
                    ).order_by('-name_similarity', '-orig_name_similarity')

                    matched_episodes = matched_episodes.filter(
                        models.Q(name_similarity__gt=0.4) | models.Q(orig_name_similarity__gt=0.4),
                    )

                    if matched_episodes.count() == 1:
                        matched_episode = matched_episodes.first()
                        by_name = 'name'
                        similarity = matched_episode.name_similarity
                        if matched_episode.orig_name_similarity > matched_episode.name_similarity:
                            by_name = 'orig_name'
                            similarity = matched_episode.orig_name_similarity
                        episode_resource, er_created = EpisodeResource.objects.get_or_create(
                            episode=matched_episode,
                            file_res=self,
                            defaults={
                                'match_similarity': similarity,
                                'match_method': u'v4,assign_by_title_in_filename,%(by_name)s' % {'by_name': by_name}
                            }
                        )

        return episode_resource

    def auto_assign(self):
        results = {
            'episode_resources': [],
        }
        matched_show = None

        def lookup_query_name(file_res, query_name, query_by, fallback=False):
            er = None
            matched_episodes = ShowEpisode.objects.annotate(
                similarity=search.TrigramSimilarity(
                    'name', qn
                )
            ).filter(
                similarity__gt=0.5,
                name__isnull=False,
                season__show=matched_show
            ).order_by('-similarity')

            if matched_episodes.count() == 1:
                matched_episode = matched_episodes.first()
                er, er_created = EpisodeResource.objects.get_or_create(
                    episode=matched_episode,
                    file_res=file_res,
                    defaults={
                        'match_similarity': matched_episode.similarity,
                        'match_method': u'v1,%(query_by)s,TrigramSimilarity' % {'query_by': query_by}
                    }
                )
                results['episode_resources'].append(er)

            if fallback and not er:
                other_matched = ShowEpisode.objects.annotate(
                    similarity=search.TrigramSimilarity(
                        'name', qn
                    )
                ).filter(
                    season__show=matched_show,
                    name__isnull=False,
                    similarity__gt=0.1
                ).order_by('-similarity')

                if other_matched.exists():
                    matched_episode = other_matched.filter(similarity__gt=0.3).first()
                    if matched_episode:
                        print "  - other_matched <= 0.3:", matched_episode.name, "vs.", self.md_summary, matched_episode.similarity * 100., "%"
                        er, er_created = EpisodeResource.objects.get_or_create(
                            episode=matched_episode,
                            file_res=file_res,
                            defaults={
                                'match_similarity': matched_episode.similarity,
                                'match_method': u'v2,%(query_by)s,TrigramSimilarity' % {'query_by': query_by}
                            }
                        )
                        results['episode_resources'].append(er)

        if self.file_source == 'dl':
            if self.show_storage:
                matched_show = self.show_storage.show
                if not self.episoderesource_set.exists():
                    matched_er_by_fn = self.assign_by_filename()
                    if matched_er_by_fn:
                        results['episode_resources'].append(matched_er_by_fn)

        else:
            if self.md_summary or (self.md_duration > 0 and self.md_title):
                if self.show_storage:
                    matched_show = self.show_storage.show

                if not matched_show:
                    print "=== Looking up Show ==="
                    print self.md_title
                    vector = search.SearchVector('name')
                    query = search.SearchQuery(self.md_title)
                    matched_shows_sr = Show.objects.annotate(
                        rank=search.SearchRank(
                            vector, query)).order_by('-rank')
                    matched_shows_sim = Show.objects.annotate(
                        similarity=search.TrigramSimilarity(
                            'name', self.md_title)).filter(similarity__gt=0.8).order_by('-similarity')

                    print "  SearchRank", matched_shows_sr
                    print "  TrigramSimilarity", matched_shows_sim

                    if matched_shows_sim.count() == 1:
                        matched_show = matched_shows_sim.first()

                if matched_show:
                    query_names_md_summary = []
                    query_names_md_description = []
                    if matched_show.auto_assign_multiep:
                        if self.md_summary and matched_show.auto_assign_multiep_sep in self.md_summary:
                            query_names_md_summary.extend(self.md_summary.split(matched_show.auto_assign_multiep_sep))
                        if self.md_description and matched_show.auto_assign_multiep_sep in self.md_description:
                            query_names_md_description.extend(self.md_description.split(matched_show.auto_assign_multiep_sep))

                    if not query_names_md_summary:
                        query_names_md_summary = [self.md_summary]

                    if not query_names_md_description:
                        query_names_md_description = [self.md_description]

                    for qn in query_names_md_summary:
                        lookup_query_name(file_res=self, query_name=qn, query_by='md_summary', fallback=True)

                    if not results['episode_resources']:
                        for qn in query_names_md_description:
                            lookup_query_name(file_res=self, query_name=qn, query_by='md_description', fallback=False)

            if not self.episoderesource_set.exists():
                matched_er_by_fn = self.assign_by_filename()
                if matched_er_by_fn:
                    results['episode_resources'].append(matched_er_by_fn)

            file_similarity_thresold = 0.5
            if not self.episoderesource_set.filter(match_similarity__gte=file_similarity_thresold).exists():
                matched_er_by_title_in_fn = self.assign_by_title_in_filename()
                if matched_er_by_title_in_fn:
                    results['episode_resources'].append(matched_er_by_title_in_fn)

            # cleanup lower episode resources
            if matched_show and not matched_show.auto_assign_multiep:
                ordered_ers = self.episoderesource_set.all().order_by('-match_similarity')
                if ordered_ers.count() > 1:
                    cleanuped_ers = 0
                    top_match = ordered_ers.first()
                    other_ers = ordered_ers.exclude(pk=top_match.pk)
                    for other in other_ers:
                        other.delete()
                        cleanuped_ers += 1

                    results['episode_resources'] = [top_match]
                    results['cleanuped_ers'] = cleanuped_ers

        return results

    def delete_from_disk(self):
        deleted = False
        if self.file_exists():
            try:
                os.remove(self.file_path)
                deleted = True
            except (IOError, OSError):
                pass
        return deleted

    class Meta:
        ordering = ('show_storage', 'file_path')


class EpisodeResource(models.Model):
    episode = models.ForeignKey(ShowEpisode)
    file_res = models.ForeignKey(FileResource)
    match_similarity = models.FloatField(default=1)
    match_method = models.CharField(max_length=255, null=True, blank=True)
    created = models.DateTimeField(null=True, blank=True)

    def get_rename_filename(self):
        episode_resources = self.file_res.episoderesource_set.all().order_by('episode__season__nr', 'episode__nr')
        text_parts = [
            slugify(self.episode.season.show.name),
        ]
        episodes = []
        for er in episode_resources:
            episodes.append(u'%(seas)02dx%(ep)02d' % {'seas': er.episode.season.nr, 'ep': er.episode.nr})

        text_parts.append(u'-'.join(episodes))

        if episode_resources.count() == 1:
            text_parts.append(slugify(self.episode.name))

        new_fn = u'.'.join(text_parts)
        return new_fn

    def is_renamed(self):
        return self.get_rename_filename() in self.file_res.get_basename()

    is_renamed.boolean = True

    def delete_from_disk(self):
        file_deleted = self.file_res.delete_from_disk()
        self.file_res.delete()
        self.delete()
        return file_deleted

    def rename_file_res(self):
        new_fn = self.get_rename_filename()
        res = self.file_res
        file_exists = res.file_exists()
        is_completed = res.is_completed()
        renamed = False

        if file_exists and is_completed and not self.is_renamed():
            old_basename = res.get_basename()
            old_root, ext = os.path.splitext(old_basename)
            ext = ext.lower()
            new_basename = new_fn + ext
            new_file_path = os.path.join(res.get_folder(), new_basename)
            try:
                os.rename(res.file_path, new_file_path)
                # shutil.move(res.file_path, new_file_path)
                res.file_path = new_file_path
                res.save()
                renamed = True
            except OSError:
                pass

        return {
            'file_exists': file_exists,
            'is_completed': is_completed,
            'renamed': renamed,
        }

    def save(self, *args, **kwargs):
        if not self.created:
            self.created = timezone.now()
        return super(EpisodeResource, self).save(*args, **kwargs)

    class Meta:
        ordering = ('episode', '-file_res__file_size')


class MovieResource(models.Model):
    movie = models.ForeignKey(Movie)
    file_res = models.ForeignKey(FileResource)

    class Meta:
        ordering = ('movie', 'file_res')
