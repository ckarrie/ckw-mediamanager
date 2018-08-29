from django.apps import AppConfig

__author__ = 'ckw'


class DefaultMMConfig(AppConfig):
    name = 'mediamanager'
    verbose_name = 'Media Manager'

    def ready(self):
        super(DefaultMMConfig, self).ready()
        # import signal handlers
        import signals
        signals.register_signals(config=self)