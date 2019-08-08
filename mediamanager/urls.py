from django.conf.urls import url, include
import views

urlpatterns = [
    url(r'^$', views.HomeView.as_view(), name='home'),
    url(r'^rec/endpoint/$', views.RecordingEndpointView.as_view(), name='rec_endpoint'),
]
