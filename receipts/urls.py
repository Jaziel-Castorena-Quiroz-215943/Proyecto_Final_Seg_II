from django.urls import path

from . import views

app_name = 'receipts'
urlpatterns = [
    path('verify/', views.verify, name='verify'),
    path('<uuid:pk>/', views.detail, name='detail'),
    path('<uuid:pk>/document/', views.document, name='document'),
]
