import csv
import pandas as pd
import requests, time, re  # 发送请求，接收JSON数据，正则解析
from pathlib import Path
from prettytable import PrettyTable  # 美化展示
from fake_useragent import UserAgent  # 随机请求头
from lxml import etree  # 进行xpath解析
from urllib import parse  # 将中文转换为url编码


search_url = "https://s.weibo.com/weibo?q=%s"  # 搜索要使用的url
base_url = "https://weibo.com/ajax/statuses/buildComments"  # 获取评论需要使用的url

# 微博有cookie反爬，如果要使用其搜索功能的话，最好添加cookie
headers = {
    'authority': 's.weibo.com',
    'method': 'GET',
    'scheme': 'https',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'accept-encoding': 'gzip, deflate, br',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'cache-control': 'no-cache',
    'cookie': 'SCF=Ahtrp6yMG3gNHVUGmDRuqrlKBKpqnWlmCvPDetdRydxDrZEd2EZHgU1q4KORr1ZI46R_0QNh9VPQn__P8t3ivLA.; SUB=_2A25E7O0fDeRhGeFH7FQX9C7MwjSIHXVngGDXrDV6PUJbktAbLRfMkW1NemZ8ynDuPJ4LO-Lzg41Qj3zwr_YDCwWt; SUBP=0033WrSXqPxfM725Ws9jqgMF55529P9D9WFfBFNhJkgxNiw9TRdi7Fhq5JpX5KMhUgL.FoM4S0qcSh571Kn2dJLoIp7LxKML1KBLBKnLxKqL1hnLBoMN1KMcSoB7eh.R; ALF=1779444303; _T_WM=51588094326; MLOGIN=1; WEIBOCN_FROM=1110005030; XSRF-TOKEN=a7fd60; mweibo_short_token=8aed5177a6; M_WEIBOCN_PARAMS=lfid%3D102803%26luicode%3D20000174%26uicode%3D20000174',
    'pragma': 'no-cache',
    'referer': 'https://weibo.com/',
    'sec-ch-ua': '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-site',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': UserAgent().random,
}

# 输出路径：与脚本同目录，避免工作目录不同写错文件
COMMIT_CSV = Path(__file__).resolve().parent / "commit.csv"

# 每条微博最多爬多少「页」评论（get_first_commit 算第 1 页）；达到后不再翻页
MAX_PAGES_PER_POST = 15
# 每个关键词最多累积多少条评论写入 commit.csv；0 表示不按条数限制
MAX_COMMENTS_PER_KEYWORD = 200

commit_data = []  # 存储获取到的数据
index = 0  # 已完成的评论页数（0 起算），用于打印与上限判断；每条微博在 main 里会清零

def get_id_uid(name):
    name = parse.quote(name.encode('utf-8'))
    """传入要搜索的内容"""
    info = []  # 这里面存放uid和mid形成的元组
    table = PrettyTable(["序号", "发布人", "发布时间", "发布主题"])
    headers.update({
        'path': f'/weibo?q={name}',
        "user-agent": UserAgent().random
    })  # 防止反爬
    resp = requests.get(search_url % name, headers=headers)  # 发送请求
    resp.encoding = resp.apparent_encoding  # 设置编码
    html = etree.HTML(resp.text)  # 提交给xpath解析
    divs = html.xpath('//*[@id="pl_feedlist_index"]/div[2]/div')  # 获取到存储内容的div
    print(divs)
    info = []  # 这里面存放uid和mid形成的元组
    table = PrettyTable(["序号", "发布时间", "作者", "主题"])  # 进行美化输出
    index = 0
    for index, div in enumerate(divs):
        try:
            mid = div.xpath("./@mid")[0]  # 获取mid
            # print(mid)
            u_url = div.xpath("./div[@class='card']/div[1]/div/a/@href")[0]  # 先获取链接，再解析数据
            uid = re.search("weibo.com/(?P<uid>\d+)\?refer", u_url).group("uid")  # 解析出uid
            # print(uid)
            info.append((mid, uid))  # 添加到列表中
        except:
            return info
    return info  # 返回对应的mid和uid


def get_first_commit(arg):  # 传入文章id和作者id所组成的元组
    global index
    params_ = {
        'is_reload': 1,  # 是否重新加载数据到页面
        'id': arg[0],  # 微博文章的id，可以在搜索页面中获得
        'is_show_bulletin': 2,
        'is_mix': 0,
        'count': 10,  # 推测是获取每页评论条数
        'uid': arg[1],  # 发布这篇微博的用户id
    }
    # print(params_)
    resp = requests.get(url=base_url, params=params_, headers=headers)
    data = resp.json()
    max_id = data["max_id"]
    for i in data["data"]:
        text = i["text"]
        text = re.sub("<.*?>", "", text)
        text = text.strip()
        city = i['user']['location']
        gender = i['user']['gender']
        followers_count = i['user']['followers_count']
        friends_count = i['user']['friends_count']
        statuses_count = i['user']['statuses_count']
        created_at = i['created_at']
        if text:
            commit_data.append([text, city, gender, followers_count, friends_count, statuses_count, created_at])
            print(text)
    print("-----------------------------------------------------")
    _mid_hint = "（0 表示没有下一页）" if max_id in (0, "0") else "（非 0 时用于请求下一页）"
    print(f"max_id 下一页游标: {max_id}{_mid_hint}")
    print(f"爬取完第 {index + 1} 页评论，休息4秒钟")
    print("------------------------------------------------------")
    index += 1
    time.sleep(4)

    return max_id  # 返回max_id


def get_other_commit(arg, max_id):
    global index
    if max_id == 0:
        return "大部分内容获取完成！"
    if index >= MAX_PAGES_PER_POST:
        return f"已达单条微博页数上限（{MAX_PAGES_PER_POST}页）"
    if MAX_COMMENTS_PER_KEYWORD and len(commit_data) >= MAX_COMMENTS_PER_KEYWORD:
        return "已达本关键词评论条数上限"
    params = {
        'flow': 0,  # 根据什么获取，0为热度，1为发布时间
        'is_reload': 1,  # 是否重新加载数据到页面
        'id': arg[0],  # 微博文章的id
        'is_show_bulletin': 2,
        'is_mix': 0,
        'max_id': max_id,  # 用来控制页数的，这个可以在上一个数据包的响应的max_id
        'count': 20,  # 推测是获取每页评论条数
        'uid': arg[1],  # 发布这篇微博的用户id
    }
    resp = requests.get(url=base_url, params=params, headers=headers)
    data = resp.json()
    new_max_id = data["max_id"]
    commit = data["data"]
    if commit:
        for i in commit:
            if MAX_COMMENTS_PER_KEYWORD and len(commit_data) >= MAX_COMMENTS_PER_KEYWORD:
                return "已达本关键词评论条数上限"
            text = i["text"]
            text = re.sub("<.*?>", "", text)
            text = text.strip()
            city = i['user']['location']
            gender = i['user']['gender']
            followers_count = i['user']['followers_count']
            friends_count = i['user']['friends_count']
            statuses_count = i['user']['statuses_count']
            created_at = i['created_at']
            if text:
                commit_data.append([text, city, gender, followers_count, friends_count, statuses_count, created_at])
                print(text)
        print("-----------------------------------------------------")
        _mid_hint = "（0 表示没有下一页）" if new_max_id in (0, "0") else "（非 0 时继续翻页）"
        print(f"max_id 下一页游标: {new_max_id}{_mid_hint}")
        print(f"爬取完第 {index + 1} 页评论，休息4秒钟")
        print("------------------------------------------------------")
        index += 1
        time.sleep(4)
        # 接口若反复返回同一 max_id，继续递归只会重复同一页
        if new_max_id == max_id:
            return "max_id未前进，停止翻页"
        if index >= MAX_PAGES_PER_POST:
            return f"已达单条微博页数上限（{MAX_PAGES_PER_POST}页）"
        if MAX_COMMENTS_PER_KEYWORD and len(commit_data) >= MAX_COMMENTS_PER_KEYWORD:
            return "已达本关键词评论条数上限"
        return get_other_commit(arg, new_max_id)
    return "大部分内容获取完成！"


def main(name):
    global index
    arg = get_id_uid(name)
    print(arg)
    if arg:
        commit_data.clear()  # 每个关键词单独一批，避免与上一关键词混写
        for uid in arg:
            if MAX_COMMENTS_PER_KEYWORD and len(commit_data) >= MAX_COMMENTS_PER_KEYWORD:
                break
            index = 0  # 每条微博单独计页数
            next_max_id = get_first_commit(uid)
            if index >= MAX_PAGES_PER_POST:
                pass
            elif MAX_COMMENTS_PER_KEYWORD and len(commit_data) >= MAX_COMMENTS_PER_KEYWORD:
                pass
            else:
                print(get_other_commit(uid, next_max_id))
        with open(COMMIT_CSV, "a+", encoding="utf-8", newline='') as f:
            for data in commit_data:
                csvwriter = csv.writer(f)
                csvwriter.writerow(data + [name])


if __name__ == '__main__':
    keywodsList = ["考研", "猪肉自由了"]
    for keywod in keywodsList:
        main(keywod)
