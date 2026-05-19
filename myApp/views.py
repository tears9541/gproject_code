"""
myApp 主要视图模块（Django views）。

这里包含三类逻辑：
- **页面渲染**：index / data_list / ksh1_* / ksh2 / spider_data
- **AJAX 接口**：ksh1_1 / ksh1_2 / ksh1_3 / ksh2_1（给 ECharts 提供 JSON 数据）
- **模型推理**：LSTM 情感分析（加载模型、把文本编码成序列、输出积极/中性/消极）

新手阅读建议：
1) 先看 `spider_data`：它把“爬虫 → 入库 → 情感推理 → 展示”串起来了
2) 再看 `ksh1_* / ksh2`：它们是把数据库数据聚合成图表需要的格式
3) 最后看 `_encode_and_predict_sentiment`：它是模型推理核心
"""

from collections import defaultdict  # 用来统计“日期 -> 数量”的简单计数器
from datetime import datetime
import json
import os
import pickle

import jieba
import numpy as np
import pandas as pd
from asgiref.sync import sync_to_async  # 在 async view 里安全调用同步 ORM/函数
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Avg, Count, FloatField, Sum  # ORM 聚合函数：平均/计数/求和
from django.db.models.functions import Cast, TruncDate  # Cast: 字符串转数值；TruncDate: 按天截断时间
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from tensorflow.keras.models import load_model  # 加载已训练的 LSTM 模型
from tensorflow.keras.preprocessing.sequence import pad_sequences  # 把不同长度序列补齐到统一长度

from myApp.models import CommentInfo
from myApp.web_spdier import spider, WeiboSpiderError
from user.models import UserInfo
from myApp import until

_lstm_model = None  # 缓存：避免每次请求都从磁盘加载模型（很慢）
_lstm_word_dict = None  # 缓存：字符->id 的字典（训练时保存的）
_LSTM_INPUT_LEN = 180  # 模型输入序列的固定长度（训练时设定）


def _load_lstm_artifacts():
    """
    加载已训练好的 LSTM 模型和分词字典（只在进程内加载一次）。
    """
    global _lstm_model, _lstm_word_dict  # 这里要修改全局缓存，所以声明 global
    if _lstm_model is not None and _lstm_word_dict is not None:
        return _lstm_model, _lstm_word_dict  # 缓存命中：直接返回

    # 模型文件与字典文件都放在 build_model 目录下（与训练脚本保持一致）
    base_dir = os.path.join(settings.BASE_DIR, "build_model")
    model_path = os.path.join(base_dir, "model", "corpus_model.h5")
    word_dict_path = os.path.join(base_dir, "word_dict.pk")

    with open(word_dict_path, "rb") as f:
        _lstm_word_dict = pickle.load(f)  # 反序列化出训练时保存的字典
    _lstm_model = load_model(model_path)  # 从 .h5 加载模型结构+权重
    return _lstm_model, _lstm_word_dict


def _encode_and_predict_sentiment(texts, max_length=_LSTM_INPUT_LEN):
    """
    使用与离线脚本相同的方式，对评论文本进行编码并调用 LSTM 模型预测情感。
    返回 [(label, score), ...] 列表。
    """
    if not texts:  # 空输入直接返回，避免模型报错
        return []

    model, word_dict = _load_lstm_artifacts()
    # 这里是“按字符”编码（不是按词），因为训练时用的就是字符级别字典。
    # 未登录字典的字符统一映射为 0。
    sequences = [[word_dict.get(ch, 0) for ch in str(text)] for text in texts]  # 每条文本 -> id 序列
    x = pad_sequences(sequences=sequences, maxlen=max_length, padding="post", value=0)  # 补齐到固定长度
    preds = model.predict(x, verbose=0)  # shape: (n, 3) 约定为 [neg, neu, pos]

    results = []
    for p in preds:
        neg, neu, pos = float(p[0]), float(p[1]), float(p[2])  # 三分类概率
        # 经验阈值：为了减少“摇摆”预测，只有明显更大才判为积极/消极，否则归中性。
        if neg > max(neu, pos) + 0.2:
            label = "消极"
            score = neg
        elif pos > max(neu, neg) + 0.1:
            label = "积极"
            score = pos
        else:
            label = "中性"
            score = neu
        results.append((label, score))
    return results

def index(request):
    """主页：展示总量指标 + 用户注册趋势 + 随机评论示例。"""
    comment_counts = CommentInfo.objects.count()  # 评论总条数
    area_counts = CommentInfo.objects.values('area').distinct().count()  # 出现过的地区数量
    weibo_counts = CommentInfo.objects.aggregate(total=Sum('pub_num'))['total']  # 微博发布数汇总（用户维度字段求和）
    user_counts = UserInfo.objects.count()  # 注册用户数

    user_infos = UserInfo.objects.all()
    date_counts = defaultdict(int)  # key=日期字符串，value=当天注册人数
    for user in user_infos:
        creation_time = user.create_time  # 用户创建时间（数据库字段）
        formatted_date = creation_time.strftime('%Y-%m-%d')  # 只保留日期，便于画折线图
        date_counts[formatted_date] += 1
    date_list = list(date_counts.keys())
    count_list = list(date_counts.values())
    random_comments = CommentInfo.objects.order_by('-comment_date')[:5]  # 示例评论（按时间倒序取最新 5 条）
    result = {
        'comment_counts': comment_counts,
        'area_counts': area_counts,
        'weibo_counts': weibo_counts,
        'user_counts': user_counts,
        'date_list': date_list,
        'count_list': count_list,
        'random_comments':random_comments,
        'avatar': request.session['avatar']
    }
    return render(request, 'index.html', result)

def data_list(request):
    """数据展示页：分页展示评论明细，并支持按关键词/文本搜索筛选。"""
    search_query = request.GET.get('search', '')  # 搜索框：按评论内容模糊匹配
    keyword_filter = request.GET.get('keyword', '')  # 下拉：按热搜词筛选
    comments = CommentInfo.objects.all()  # QuerySet：后面会叠加 filter
    if search_query:
        comments = comments.filter(comment_text__icontains=search_query)  # icontains=不区分大小写包含
    if keyword_filter:
        comments = comments.filter(keyword=keyword_filter)
    # 必须显式排序，否则 Paginator 会警告且翻页结果不稳定（无默认 Meta.ordering 时）
    comments = comments.order_by("-comment_date", "-id")
    paginator = Paginator(comments, 20)  # 每页 20 条
    page_number = request.GET.get('page')  # 当前页码（字符串）
    page_obj = paginator.get_page(page_number)  # 超界会自动返回最后一页

    keywords = CommentInfo.objects.values_list('keyword', flat=True).distinct()  # 下拉候选：所有出现过的 keyword

    context = {
        'page_obj': page_obj,
        'keywords': keywords,
        'search_query': search_query,
        'selected_keyword': keyword_filter,
        'avatar': request.session.get('avatar')
    }
    return render(request, 'data_list.html', context)

def ksh1_map(request):
    """
    地图页面：各地区评论分布（合并所有热搜词）。

    说明：
    - `CommentInfo.area` 实际存的是 weibo 返回的 user.location（属地/地区）
    - 这里统计的是“评论条数”，不是发布微博数（更容易在小数据量下看出分布）
    """
    # 这里的 area 在模型里存的是 weibo user.location（属地/地区）
    rows = (
        CommentInfo.objects.exclude(area__exact="")  # 排除空地区
        .values("area")  # 以 area 分组
        .annotate(value=Count("id"))  # 每个地区的评论条数
        .order_by("-value")  # 评论多的排前面
    )
    map_value = [{"name": (r["area"] or "未知"), "value": int(r["value"])} for r in rows]
    max_value = max([v["value"] for v in map_value], default=0)  # 给前端 visualMap 用来自动缩放

    return render(request, "ksh1_map.html", {"map_value": map_value, "max_value": max_value, "avatar": request.session.get("avatar")})


def ksh1_charts(request):
    """
    舆情数据分析页面：包含两个图表（趋势 + 性别参与度）。

    该页面本身只负责提供下拉框候选项；
    具体图表数据通过 AJAX 调用 `ksh1_1/ksh1_2` 获取。
    """
    preferred = ["爱情", "人生"]  # 让这两个优先显示在下拉顶部（不影响全量展示）
    existing = list(
        CommentInfo.objects.exclude(keyword__exact="")  # 排除空 keyword
        .values_list("keyword", flat=True)
        .distinct()  # 去重
    )
    keyword_list = [k for k in preferred if k in existing] + [k for k in existing if k not in preferred]
    default_trend = keyword_list[0] if keyword_list else ""  # 默认选中的热搜词

    return render(
        request,
        "ksh1_charts.html",
        {
            "keyword_list": keyword_list,
            "avatar": request.session.get("avatar"),
            "default_trend": default_trend,
        },
    )


def ksh1_wordcloud(request):
    """
    热搜评论词云页面。

    该页面本身只负责提供下拉框候选项；
    具体词云数据通过 AJAX 调用 `ksh1_3` 获取。
    """
    preferred = ["爱情", "人生"]
    existing = list(
        CommentInfo.objects.exclude(keyword__exact="")
        .values_list("keyword", flat=True)
        .distinct()
    )
    keyword_list = [k for k in preferred if k in existing] + [k for k in existing if k not in preferred]
    default_trend = keyword_list[0] if keyword_list else ""

    return render(
        request,
        "ksh1_wordcloud.html",
        {
            "keyword_list": keyword_list,
            "avatar": request.session.get("avatar"),
            "default_trend": default_trend,
        },
    )

def ksh1_1(request):
    """AJAX：返回某个热搜词的“按天评论数趋势”。"""
    selected_trend = (request.POST.get("trend") or "").strip()  # 前端下拉框传来的热搜词
    if not selected_trend:
        return JsonResponse({"date_list": [], "value_list": []})

    rows = (
        CommentInfo.objects.filter(keyword=selected_trend)  # 只看该热搜词的评论
        .annotate(d=TruncDate("comment_date"))  # comment_date 截断到“天”
        .values("d")  # 按天分组
        .annotate(c=Count("id"))  # 每天评论条数
        .order_by("d")  # 时间正序
    )
    date_list = [r["d"].strftime("%Y-%m-%d") if r["d"] else "" for r in rows]
    value_list = [int(r["c"] or 0) for r in rows]
    return JsonResponse({"date_list": date_list, "value_list": value_list})

def ksh1_2(request):
    """AJAX：返回某个热搜词的性别分布（用于饼图）。"""
    selected_trend = (request.POST.get("trend") or "").strip()  # 前端下拉框传来的热搜词
    if not selected_trend:
        return JsonResponse({"data_list": [], "avatar": request.session.get("avatar")})

    rows = (
        CommentInfo.objects.filter(keyword=selected_trend)  # 只看该热搜词
        .exclude(gender__exact="")  # 排除空性别
        .values("gender")  # 按 gender 分组
        .annotate(value=Count("id"))  # 每种性别的评论条数
        .order_by("-value")  # 多的排前
    )
    data_list = [{"name": (r["gender"] or "未知"), "value": int(r["value"])} for r in rows]
    return JsonResponse({"data_list": data_list, "avatar": request.session.get("avatar")})


def ksh1_3(request):
    """AJAX：返回某个热搜词的评论词云数据（从数据库评论文本分词统计）。"""
    selected_trend = (request.POST.get("trend") or "").strip()  # 前端下拉框传来的热搜词
    if not selected_trend:
        return JsonResponse({"wordclout_dict": [], "avatar": request.session.get("avatar")})

    texts = list(
        CommentInfo.objects.filter(keyword=selected_trend)  # 只看该热搜词
        .values_list("comment_text", flat=True)[:5000]  # 限制条数：避免一次性分词太慢
    )
    wordclout_dict = creatwc_from_texts(texts)
    return JsonResponse({"wordclout_dict": wordclout_dict, "avatar": request.session.get("avatar")})

def ksh2(request):
    """
    情感分析可视化页：
    - 图表数据全部从数据库 CommentInfo 实时聚合（不依赖 CSV / part 表）
    - 通过“热搜下拉框”切换当前关键词，更新饼图/词云
    """
    preferred = ["爱情", "人生"]
    existing_keywords = list(
        CommentInfo.objects.exclude(keyword__exact="")  # 排除空 keyword
        .values_list("keyword", flat=True)
        .distinct()  # 去重得到所有热搜词
    )
    keyword_list = [k for k in preferred if k in existing_keywords] + [
        k for k in existing_keywords if k not in preferred
    ]

    selected_keyword = (request.GET.get("keyword") or "").strip()  # 从 querystring 读取当前选择的热搜词
    if not selected_keyword:
        selected_keyword = keyword_list[0] if keyword_list else ""

    # 基础 QuerySet：用于“当前关键词”的所有统计
    qs_base = CommentInfo.objects.all()  # 当前热搜词的基础 QuerySet（后续统一基于它做统计）
    if selected_keyword:
        qs_base = qs_base.filter(keyword=selected_keyword)  # 只保留当前热搜词

    # 饼图：当前关键词下，各 lstm_result 评论条数
    dist_rows = qs_base.values("lstm_result").annotate(value=Count("id")).order_by("-value")  # 情感分布：按 lstm_result 分组计数
    lstm_res = [
        {"name": (row["lstm_result"] or "未知"), "value": row["value"]}
        for row in dist_rows
    ]

    # 下拉：当前关键词下出现的情感类别（稳定顺序）
    sentiments = list(
        qs_base.exclude(lstm_result__exact="")  # 排除空情感
        .values_list("lstm_result", flat=True)
        .distinct()  # 去重得到下拉候选
    )
    _order = {"积极": 0, "中性": 1, "消极": 2, "未知情感": 3}
    sentiments.sort(key=lambda x: _order.get(x, 99))
    default_selection = sentiments[0] if sentiments else ""

    # 柱图：展示全部关键词（但“爱情/人生”优先排前）
    bar_keywords = keyword_list  # 柱图显示的关键词列表（这里按下拉顺序）
    keyword_rows = (
        CommentInfo.objects.filter(keyword__in=bar_keywords)  # 只统计这些热搜词
        .values("keyword")
        # lstm_score 在数据库里存的是字符串，这里 Cast 成 float 才能做 Avg
        .annotate(avg_score=Avg(Cast("lstm_score", output_field=FloatField())))
    )
    score_map = {row["keyword"]: round(float(row["avg_score"] or 0.0), 4) for row in keyword_rows}
    name_list = bar_keywords
    value_list = [score_map.get(k, 0.0) for k in bar_keywords]

    # 初始词云：当前关键词 + 当前默认选中情感下的评论文本
    initial_wordcloud: list = []
    if default_selection:
        texts = list(
            qs_base.filter(lstm_result=default_selection).values_list("comment_text", flat=True)[:5000]
        )
        initial_wordcloud = creatwc_from_texts(texts)

    result = {
        "lstm_res": mark_safe(json.dumps(lstm_res, ensure_ascii=False)),
        "lstm_result_list": sentiments,
        "name_list": mark_safe(json.dumps(name_list, ensure_ascii=False)),
        "value_list": mark_safe(json.dumps(value_list, ensure_ascii=False)),
        "avatar": request.session.get("avatar"),
        "select_lstm": default_selection,
        "initial_wordcloud": mark_safe(json.dumps(initial_wordcloud, ensure_ascii=False)),
        "keyword_list": keyword_list,
        "selected_keyword": selected_keyword,
    }
    return render(request, "ksh2.html", result)


def ksh2_1(request):
    """AJAX：按关键词 + 情感倾向筛选评论，从数据库生成词云 JSON。"""
    lstmSelect = (request.POST.get("lstmSelect") or "").strip()  # 情感下拉
    keyword = (request.POST.get("keyword") or "").strip()  # 热搜下拉（可选）

    if not lstmSelect:
        return JsonResponse({"error": "未选择情感倾向"}, status=400)

    try:
        qs = CommentInfo.objects.filter(lstm_result=lstmSelect)  # 先按情感筛选
        if keyword:
            qs = qs.filter(keyword=keyword)  # 再按热搜筛选（这样词云会更“聚焦”）
        texts = list(qs.values_list("comment_text", flat=True)[:5000])
        wordclout_dict = creatwc_from_texts(texts)

        return JsonResponse(
            {
                "wordclout_dict": wordclout_dict,
                "avatar": request.session.get("avatar"),
            }
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


async def spider_data(request):
    """
    数据爬取页：
    - GET：展示数据库里最近的评论数据（便于查看是否入库成功）
    - POST：触发爬虫抓取 → 写入 CommentInfo → 对新增评论做 LSTM 情感推理 → 页面展示结果

    注意：这是“演示型”实现，重点在把流程串起来。
    """
    avatar = await sync_to_async(lambda: request.session.get('avatar'))()
    if request.method == 'POST':
        search = request.POST.get('search')
        error = None
        results = []
        if search:
            try:
                # 默认：取搜索结果第 1 条微博，抓前 3 页评论
                spider_results = await spider(search, max_posts=1, max_pages=3, count_per_page=20)

                # 入库（简单去重：comment_text + keyword + comment_date）
                to_create = []
                sentiment_map = {}
                for item in spider_results:
                    comment_text = (item.get('comment_text') or '').strip()
                    comment_date_raw = (item.get('comment_date') or '').strip()
                    comment_date_dt = None
                    if comment_date_raw:
                        try:
                            comment_date_dt = datetime.strptime(comment_date_raw, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            comment_date_dt = None
                    if not comment_text:
                        continue
                    qs = CommentInfo.objects.filter(comment_text=comment_text, keyword=search)
                    if comment_date_dt is not None:
                        qs = qs.filter(comment_date=comment_date_dt)
                    exists = await sync_to_async(qs.exists)()
                    if exists:
                        continue
                    to_create.append(
                        CommentInfo(
                            comment_text=comment_text,
                            area=item.get('area') or '未知',
                            gender=item.get('gender') or '未知',
                            fans_num=int(item.get('fans_num') or 0),
                            follow_num=int(item.get('follow_num') or 0),
                            pub_num=int(item.get('pub_num') or 0),
                            comment_date=comment_date_dt or datetime.now(),
                            keyword=search,
                        )
                    )

                if to_create:
                    await sync_to_async(CommentInfo.objects.bulk_create)(to_create, batch_size=200)

                    # 使用已训练好的 LSTM 模型，为本次新增评论补充情感倾向与得分
                    new_texts = [obj.comment_text for obj in to_create]
                    try:
                        labels_scores = await sync_to_async(_encode_and_predict_sentiment)(new_texts)
                        for obj, (label, score) in zip(to_create, labels_scores):
                            obj.lstm_result = label
                            obj.lstm_score = str(round(score, 2))
                            sentiment_map[obj.comment_text] = (label, score)
                        await sync_to_async(CommentInfo.objects.bulk_update)(
                            to_create, ["lstm_result", "lstm_score"]
                        )
                    except Exception:
                        # 情感分析失败时，不影响基础数据入库
                        sentiment_map = {}

                # 页面展示：把本次抓取结果映射到模板字段（沿用原模板字段名），并附带情感结果
                for item in spider_results:
                    ct = item.get("comment_text")
                    label, score = sentiment_map.get(ct, (None, None))
                    results.append(
                        {
                            "content": ct,
                            "area": item.get("area") or "未知",
                            "gender": item.get("gender") or "未知",
                            "fans_num": item.get("fans_num") or 0,
                            "haoyou_num": item.get("follow_num") or 0,
                            "weibo_num": item.get("pub_num") or 0,
                            "pub_time": item.get("comment_date") or "",
                            "hot_name": search,
                            "lstm_result": label,
                            "lstm_score": score,
                        }
                    )
            except WeiboSpiderError as e:
                error = str(e)
            except Exception as e:
                error = f"爬取失败：{e}"

        context = {
            'results': results,
            'avatar': avatar,
            'error': error,
            'spider_post_mode': True,
            'page_obj': None,
        }
        return render(request, 'spider_data.html', context)

    # GET：分页展示数据库评论（每页 20 条）
    def _paginate_spider_list(req):
        qs = CommentInfo.objects.order_by("-id").values(
            "comment_text",
            "area",
            "gender",
            "fans_num",
            "follow_num",
            "pub_num",
            "comment_date",
            "keyword",
            "lstm_result",
            "lstm_score",
        )
        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(req.GET.get("page"))
        out = []
        for row in page_obj.object_list:
            score = row.get("lstm_score")
            try:
                score_val = float(score) if score is not None else None
            except (TypeError, ValueError):
                score_val = None
            out.append(
                {
                    "content": row["comment_text"],
                    "area": row["area"],
                    "gender": row["gender"],
                    "fans_num": row["fans_num"],
                    "haoyou_num": row["follow_num"],
                    "weibo_num": row["pub_num"],
                    "pub_time": row["comment_date"].strftime("%Y-%m-%d %H:%M:%S")
                    if row.get("comment_date")
                    else "",
                    "hot_name": row["keyword"],
                    "lstm_result": row.get("lstm_result"),
                    "lstm_score": score_val,
                }
            )
        return page_obj, out

    page_obj, results = await sync_to_async(_paginate_spider_list)(request)
    context = {
        "results": results,
        "avatar": avatar,
        "page_obj": page_obj,
        "spider_post_mode": False,
    }
    return render(request, "spider_data.html", context)


def creatwc_from_texts(texts):
    """
    从评论纯文本列表生成词云统计（规则与 creatwc 一致：长度、过滤纯数字）。
    供 ksh2 等从数据库 CommentInfo.comment_text 直接分词使用。
    """
    word_count: dict[str, int] = {}
    for text in texts:
        if not text:
            continue
        for word in jieba.cut(str(text)):
            if word in {"", " "}:
                continue
            if len(word) < 2:
                continue
            try:
                float(word)
                continue
            except ValueError:
                pass
            word_count[word] = word_count.get(word, 0) + 1
    pairs = sorted(word_count.items(), key=lambda d: d[1], reverse=True)
    return [{"name": k[0], "value": k[1]} for k in pairs]


def creatwc(df_data):
    word_count = {}
    for f, book in df_data.iterrows():
        words = jieba.cut(book['评论内容'])
        for word in words:
            if word in {''}:
                continue
            if len(word) < 2:
                continue
            try:
                float(word)
                continue
            except:
                if word in word_count:
                    word_count[word] += 1
                else:
                    word_count[word] = 1
    wordclout_dict = sorted(word_count.items(), key=lambda d:d[1], reverse=True)
    wordclout_dict = [{"name": k[0], 'value': k[1]} for k in wordclout_dict]
    return wordclout_dict