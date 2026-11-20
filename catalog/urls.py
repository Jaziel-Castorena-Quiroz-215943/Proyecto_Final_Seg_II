from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    path('', views.home, name='home'),
    path('catalog/', views.product_list, name='list'),
    path('catalog/<int:pk>/', views.product_detail, name='detail'),
    path('catalog/manage/', views.manage, name='manage'),
    path('catalog/manage/create/', views.product_create, name='create'),
    path('catalog/manage/<int:pk>/edit/', views.product_edit, name='edit'),
]
