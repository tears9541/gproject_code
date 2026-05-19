#!/usr/bin/env python
"""
Django 的命令行入口。

你在终端里运行的这些命令，本质都是通过这个文件启动的：
- `python manage.py runserver`：启动开发服务器
- `python manage.py migrate`：执行数据库迁移
- `python manage.py createsuperuser`：创建后台管理员

新手常见报错：
- “Couldn't import Django”：通常是没激活虚拟环境，或没安装 django
"""
import os
import sys


def main():
    """Run administrative tasks."""
    # 告诉 Django 去哪里找 settings.py（不设置会启动失败）
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weibo_project.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
