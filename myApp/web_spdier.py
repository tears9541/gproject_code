"""
微博爬虫模块（用于“按热搜词抓取评论”）。

整体流程：
1) `spider(keyword)` 入口：从环境变量 `WEIBO_COOKIE` 读取 Cookie（或显式传参）
2) `search_mids_uids`：先去微博搜索页，根据关键词解析出一条微博的 mid + uid
3) `fetch_comments`：调用 weibo 的 ajax 评论接口，分页抓取评论 JSON
4) 返回结构化列表，交给 views 入库，并用 LSTM 模型补齐情感字段

常见失败原因：
- Cookie 过期/未登录：搜索页会跳转或返回验证页，解析不到 mid/uid
- 微博页面结构变化：xpath 规则会失效（已做 fallback，但不是万能）
- 风控：频率过快会被限制；代码里通过 sleep 做了轻度限速
"""

import asyncio
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from urllib import parse

import requests
from fake_useragent import UserAgent
from lxml import etree

search_url = "https://s.weibo.com/weibo?q=%s"
base_url = "https://weibo.com/ajax/statuses/buildComments"


class WeiboSpiderError(RuntimeError):
    """爬虫的业务异常：用于把“可读的失败原因”抛给上层页面展示。"""
    pass


def _debug_enabled() -> bool:
    """通过环境变量开关调试输出：WEIBO_DEBUG=1/true/yes 时启用。"""
    return os.environ.get("WEIBO_DEBUG", "").strip() in {"1", "true", "True", "yes", "YES"}


def _write_debug_file(filename: str, content: str) -> Optional[str]:
    """
    把抓到的 HTML 保存到 ./debug/ 目录，方便你用浏览器打开比对 xpath 是否失效。
    """
    try:
        debug_dir = os.path.join(os.getcwd(), "debug")
        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content or "")
        return path
    except Exception:
        return None


def _build_headers(*, cookie: str) -> Dict[str, str]:
    """
    构造请求头。

    重点：
    - Cookie 必须是“已登录微博”浏览器里复制出来的整段 Cookie
    - User-Agent 使用随机值，减少被简单识别为脚本的概率（不保证一定有效）
    """
    return {
        "authority": "s.weibo.com",
        "method": "GET",
        "scheme": "https",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "cookie": cookie,  # 关键：必须携带已登录的 Cookie，否则很容易返回验证页/空数据
        "pragma": "no-cache",
        "referer": "https://weibo.com/",
        "user-agent": UserAgent().random,
        "sec-ch-ua": '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-site",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
    }


def _clean_text(html_text: str) -> str:
    """把 weibo 返回的富文本（含 <a>、<img> 等）粗略转成纯文本。"""
    text = re.sub(r"<.*?>", "", html_text or "")
    return text.strip()


def _parse_created_at(created_at: str) -> str:
    """
    Weibo returns something like: 'Wed Jul 16 09:56:00 +0800 2025'
    Convert to 'YYYY-MM-DD HH:MM:SS' (local time, no tz).
    """
    if not created_at:
        return ""
    try:
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return created_at


def search_mids_uids(
    keyword: str,
    *,
    cookie: str,
    max_posts: int = 3,
    timeout: int = 15,
) -> List[Tuple[str, str]]:
    """
    在微博搜索页里解析出 (mid, uid)。

    - mid: 微博内容的唯一 id（后续评论接口需要）
    - uid: 发帖用户 id（评论接口需要）
    """
    q = parse.quote(keyword.encode("utf-8"))
    headers = _build_headers(cookie=cookie)
    headers.update({"path": f"/weibo?q={q}", "user-agent": UserAgent().random})

    resp = requests.get(search_url % q, headers=headers, timeout=timeout)  # 先抓搜索页 HTML
    resp.encoding = resp.apparent_encoding
    html_text = resp.text or ""
    html = etree.HTML(html_text)

    # 现有项目里使用的 xpath（可能随微博页面变化而失效），保留并做 fallback。
    divs = html.xpath('//*[@id="pl_feedlist_index"]/div[2]/div')  # 主 xpath（微博结构可能变）
    if not divs:
        divs = html.xpath('//*[@id="pl_feedlist_index"]/div/div')  # fallback xpath

    results: List[Tuple[str, str]] = []
    for div in divs:
        if len(results) >= max_posts:
            break
        try:
            mid = div.xpath("./@mid")[0]  # mid 是评论接口必须的参数
            u_url = div.xpath(".//a[contains(@href,'weibo.com')]/@href")[0]
            m = re.search(r"weibo\.com/(?P<uid>\d+)\?refer", u_url)
            if not m:
                continue
            uid = m.group("uid")  # uid 同样是评论接口必须的参数
            results.append((mid, uid))
        except Exception:
            continue

    if not results:
        debug_path = None
        if _debug_enabled():
            debug_path = _write_debug_file("weibo_search_debug.html", html_text)

        snippet = (re.sub(r"\s+", " ", html_text)[:300] or "").strip()
        hint_parts = [
            f"status={getattr(resp, 'status_code', 'unknown')}",
            f"url={getattr(resp, 'url', 'unknown')}",
        ]
        if debug_path:
            hint_parts.append(f"debug_file={debug_path}")
        if snippet:
            hint_parts.append(f"snippet={snippet}")

        raise WeiboSpiderError(
            "未能从微博搜索页解析到 mid/uid。"
            " 通常是 cookie 失效/未生效、被风控返回验证页，或搜索页结构变更导致解析规则失效。"
            " 详情：" + " | ".join(hint_parts)
        )
    return results


def fetch_comments(
    mid: str,
    uid: str,
    *,
    cookie: str,
    flow: int = 0,
    count: int = 20,
    max_pages: int = 3,
    sleep_range: Tuple[float, float] = (1.2, 2.5),
    timeout: int = 15,
) -> List[Dict[str, object]]:
    """
    返回结构化评论列表：
    {
      comment_text, area, gender, fans_num, follow_num, pub_num, comment_date, keyword(不在这里填)
    }

    注意：
    - 这里抓的是“评论”，不是原微博内容本身
    - weibo 评论接口是 JSON；`max_id` 用于翻页
    """
    headers = _build_headers(cookie=cookie)
    session = requests.Session()  # 用 Session 复用连接 + 让 cookies/header 行为更像浏览器
    max_id: Optional[int] = None
    out: List[Dict[str, object]] = []

    for _page in range(max_pages):
        params = {
            "flow": flow,
            "is_reload": 1,
            "id": mid,
            "uid": uid,
            "is_show_bulletin": 2,
            "is_mix": 0,
            "count": count,
        }
        if max_id is not None:
            params["max_id"] = max_id

        r = session.get(base_url, params=params, headers=headers, timeout=timeout)  # 评论接口返回 JSON
        data = r.json()  # 这里如果被风控返回 HTML，会抛异常（上层会捕获并提示）

        max_id = data.get("max_id")  # 翻页游标：下一页用 max_id 继续请求
        items = data.get("data") or []
        if not items:
            break

        for it in items:
            text = _clean_text(it.get("text", ""))
            if not text:
                continue
            user = it.get("user") or {}
            raw_gender = (user.get("gender") or "").lower()
            if raw_gender == "m":
                gender = "男"
            elif raw_gender == "f":
                gender = "女"
            else:
                gender = "未知"
            out.append(
                {
                    "comment_text": text,
                    "area": user.get("location") or "",
                    "gender": gender,
                    "fans_num": int(user.get("followers_count") or 0),
                    "follow_num": int(user.get("friends_count") or 0),
                    "pub_num": int(user.get("statuses_count") or 0),
                    "comment_date": _parse_created_at(it.get("created_at") or ""),
                }
            )

        # max_id == 0 表示没有下一页
        if max_id in (0, "0", None):
            break
        time.sleep(random.uniform(*sleep_range))

    return out


async def spider(
    keyword: str,
    *,
    max_posts: int = 1,
    max_pages: int = 3,
    count_per_page: int = 20,
    cookie: Optional[str] = None,
) -> List[Dict[str, object]]:
    """
    爬取关键词对应的微博评论（默认取搜索结果的第一条微博，抓前几页评论）。

    cookie 来源：
    - 显式传入 cookie
    - 或环境变量 WEIBO_COOKIE
    """
    cookie = cookie or os.environ.get("WEIBO_COOKIE", "").strip()
    if not cookie:
        raise WeiboSpiderError(
            "缺少微博 cookie：请在系统环境变量里设置 WEIBO_COOKIE（从已登录微博的浏览器请求头复制 Cookie）。"
        )

    mids_uids = search_mids_uids(keyword, cookie=cookie, max_posts=max_posts)
    results: List[Dict[str, object]] = []
    for mid, uid in mids_uids[:max_posts]:
        results.extend(
            fetch_comments(
                mid,
                uid,
                cookie=cookie,
                max_pages=max_pages,
                count=count_per_page,
            )
        )
        break

    # 让出事件循环（保持 async view 不至于完全饿死）
    await asyncio.sleep(0)
    return results

