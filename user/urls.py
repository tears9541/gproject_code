from django.urls import path

from user import views

app_name = 'user'
urlpatterns = [
    path('login/', views.login, name='login'),
    path('', views.login, name='login'),
    path('register', views.register, name='register'),
    path('userinfo', views.userinfo, name='userinfo'),
    path('logout', views.logout, name='logout'),
]