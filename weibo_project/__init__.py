import pymysql

pymysql.install_as_MySQLdb()

# 说明（给新手）：
# Django 默认 MySQL 驱动是 mysqlclient（导入名 MySQLdb），在 Windows 上安装经常需要编译环境。
# 这里用 PyMySQL 伪装成 MySQLdb，避免 “No module named 'MySQLdb'” 的启动错误。
