from django.urls import path

from myApp import views

app_name = 'myApp'
urlpatterns = [
    # 主页与数据列表
    path('index', views.index, name='index'),
    path('data_list', views.data_list, name='data_list'),

    # 可视化页面（地图/趋势/词云/情感分析）
    path('ksh1_map/', views.ksh1_map, name='ksh1_map'),
    path('ksh1_charts/', views.ksh1_charts, name='ksh1_charts'),
    path('ksh1_wordcloud/', views.ksh1_wordcloud, name='ksh1_wordcloud'),

    # AJAX 数据接口（返回 JSON，用于更新图表）
    path('ksh1_1', views.ksh1_1, name='ksh1_1'),
    path('ksh1_2', views.ksh1_2, name='ksh1_2'),
    path('ksh1_3', views.ksh1_3, name='ksh1_3'),
    path('ksh2', views.ksh2, name='ksh2'),
    path('ksh2_1', views.ksh2_1, name='ksh2_1'),

    # 数据爬取页：GET 展示历史数据；POST 触发爬取 + 实时情感推理
    path('spider_data', views.spider_data, name='spider_data'),
]