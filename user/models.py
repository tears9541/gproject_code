"""
用户信息模型。

说明：
- 本项目未使用 Django 内置 auth.User，而是采用自定义表 `user_userinfo` 
- `avatar` 存储头像静态资源路径（如 `/static/img/default.jpg`），供模板直接引用。
"""

from django.db import models
from django.utils import timezone


class UserInfo(models.Model):
    """用户信息（登录/个人中心展示与修改）。"""
    username = models.CharField('用户名', max_length=20)
    password = models.CharField('密码', max_length=40)
    uemail = models.CharField('电子邮箱', max_length=30)
    uaddress = models.CharField('地址', max_length=30)
    uyoubian = models.CharField('邮编', max_length=30)
    uphone = models.CharField('手机号', max_length=30)
    create_time = models.DateTimeField('创建时间', default=timezone.now)
    avatar = models.TextField('头像', default='/static/img/default.jpg')

    def __str__(self):
        return self.username

    class Meta:
        verbose_name_plural = '用户管理'