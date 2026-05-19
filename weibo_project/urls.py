"""
weibo_project URL Configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
本项目路由约定：
- `/user/`：登录/注册/个人中心（默认入口）
- `/myApp/`：舆情业务页面（数据列表、爬取、可视化、情感分析）
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    # 默认入口：跳转到登录页（避免直接暴露业务页面给未登录用户）
    path('', RedirectView.as_view(url='/user/')),
    path('myApp/', include('myApp.urls')),
    path('user/', include('user.urls')),
]
