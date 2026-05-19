"""
最小化的 MySQL 工具函数。

注意：
- 这个文件是“直连数据库”的方式（pymysql + 手写 SQL），并不经过 Django ORM。
- 项目里历史上有一部分统计图使用 `part1/part2/part3...` 这类表，
  会通过这里的 `qurey/insert` 去查/写（现在部分页面已改为直接用 ORM 聚合 CommentInfo）。

新手常见坑：
- 连接/游标必须关闭，否则会出现连接耗尽、进程退出慢等问题。
- 生产环境建议使用连接池，并避免拼接 SQL（有注入风险）；这里用于课程/演示。
"""

import pymysql

from config import Config


def coon():
    """
    建立一次新的数据库连接并返回 (connection, cursor)。

    - charset 使用 utf8mb4 以兼容 emoji/特殊字符（微博文本很常见）
    """
    con = pymysql.connect(
        host=Config.host,
        port=Config.port,
        user=Config.user,
        password=Config.password,
        db=Config.db,
        charset="utf8mb4",
    )
    cur = con.cursor()
    return con, cur


def close():
    """
    关闭一个“新建的连接”。

    历史原因保留该函数，但它并不会关闭 qurey/insert 中创建的那个连接（因为它重新 coon() 了一次）。
    为了不改变旧代码行为，这里暂不重构；如果你后续要改进，建议把连接对象传进来关闭。
    """
    con, cur = coon()
    cur.close()
    con.close()


def qurey(sql):
    """执行查询 SQL 并返回 fetchall() 结果。"""
    con, cur = coon()
    cur.execute(sql)
    res = cur.fetchall()
    # 这里调用的是上面的 close()（会再新建连接），属于历史写法；保留以兼容原项目。
    close()
    return res


def insert(sql):
    """执行写入类 SQL（insert/update/delete）并提交事务。"""
    con, cur = coon()
    cur.execute(sql)
    con.commit()
    close()
