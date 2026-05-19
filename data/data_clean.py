import pandas as pd

df = pd.read_csv("D:\pycode\weibo_project\data\commit.csv", names=['评论内容', '地区', '性别', '粉丝数', '关注数', '用户发布微博数', '评论时间', '评论所属热搜'])
df = df[df['地区'] != '其他']
df['地区'] = df['地区'].str.split(' ').str[0]
df['评论时间'] = pd.to_datetime(df['评论时间'])
df['性别'] = df['性别'].replace('m', '男', regex=True)
df['性别'] = df['性别'].replace('f', '女', regex=True)
df = df.drop_duplicates()
df.to_csv("D:\pycode\weibo_project\data\clean.csv", index=False)
