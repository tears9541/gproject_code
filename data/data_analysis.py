import sys
from pathlib import Path

# 保证从 data/ 目录直接运行本脚本时也能 import 项目根目录下的 config
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pymysql
import pandas as pd
from config import Config

conn = pymysql.connect(host=Config.host, user=Config.user, password=Config.password, database=Config.db)

cursor = conn.cursor()

# 相对项目根目录，不依赖「从哪一级目录执行 python」时的当前工作目录
LSTM_RESULT = _ROOT / "build_model" / "LSTM_result.csv"
df = pd.read_csv(LSTM_RESULT)


def part1():
    area_avg_counts = df.groupby("地区")['用户发布微博数'].mean().reset_index()
    area_avg_counts.columns = ['地区', '平均用户发布微博数']

    area_avg_counts['平均用户发布微博数'] = area_avg_counts['平均用户发布微博数'].round(2)

    truncate_sql = 'truncate table part1'
    cursor.execute(truncate_sql)
    conn.commit()

    sql = 'insert into part1(name, value) values (%s,%s)'
    for index, row in area_avg_counts.iterrows():
        cursor.execute(sql, (row['地区'], row['平均用户发布微博数']))
    conn.commit()

def part2():
    df['评论时间'] = pd.to_datetime(df['评论时间'])

    df['年月日时'] = df['评论时间'].dt.strftime('%Y-%m-%d %H')

    trend_distribution = df.groupby(['评论所属热搜', '年月日时']).size().reset_index(name='评论数')

    print(trend_distribution)

    truncate_sql = 'truncate table part2'
    cursor.execute(truncate_sql)
    conn.commit()

    sql = 'insert into part2(keyword, comment_date, comment_num) values (%s,%s,%s)'
    for index, row in trend_distribution.iterrows():
        cursor.execute(sql, (row['评论所属热搜'], row['年月日时'], row['评论数']))
    conn.commit()

def part3():
    gender_counts = df.groupby(['评论所属热搜', '性别']).size().reset_index(name='评论数量')

    print(gender_counts)
    truncate_sql = 'truncate table part3'
    cursor.execute(truncate_sql)
    conn.commit()

    sql = 'insert into part3(keyword,gender,comment_num) values(%s,%s,%s)'
    for index, row in gender_counts.iterrows():
        cursor.execute(sql, (row['评论所属热搜'], row['性别'], row['评论数量']))
    conn.commit()

def part4():
    LSTM_counts = df['lstm_result'].value_counts()
    print(LSTM_counts)
    truncate_sql = 'truncate table part4'
    cursor.execute(truncate_sql)
    conn.commit()

    sql = 'insert into part4(name,value) values(%s,%s)'
    for index, row in LSTM_counts.items():
        cursor.execute(sql, (index, row))
    conn.commit()

def part5():
    average_scores = df.groupby('评论所属热搜')['lstm_score'].mean().reset_index()

    average_scores.columns = ['热搜', '平均情感得分']
    print(average_scores)
    truncate_sql = 'truncate table part5'
    cursor.execute(truncate_sql)
    conn.commit()

    sql = 'insert into part5(name,value) values(%s,%s)'
    for index, row in average_scores.iterrows():
        cursor.execute(sql, (row['热搜'], row['平均情感得分']))
    conn.commit()

if __name__ == '__main__':
    part1()
    part2()
    part3()
    part4()
    part5()