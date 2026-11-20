from django.urls import path

from . import views

app_name = 'security'
urlpatterns = [
    path('download/<int:pk>/', views.download, name='download'),
    path('fingerprints/extract/', views.extract, name='extract'),
]
