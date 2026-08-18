"""抖音 web API 客户端：搜索热点视频 + 读取评论区。

签名（a_bogus）融合自 github.com/Evil0ctal/Douyin_TikTok_Download_API（Apache-2.0），
vendored 于 backend/vendors/abogus.py。抖音 web 接口需要登录态：
在 .env.local 配置 DOUYIN_COOKIE（浏览器登录 www.douyin.com 后 F12 复制 Cookie 整串）。
"""
import logging
from urllib.parse import urlencode, quote

import httpx

from backend.config import DOUYIN_COOKIE
from backend.vendors.abogus import ABogus

logger = logging.getLogger(__name__)

_DOUYIN = "https://www.douyin.com"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"

# 公共参数（与签名项目 BaseRequestModel 一致；msToken 置空亦可签名）
_COMMON = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": 1,
    "version_code": "290100",
    "version_name": "29.1.0",
    "cookie_enabled": "true",
    "screen_width": 1920,
    "screen_height": 1080,
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "130.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "130.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": 12,
    "device_memory": 8,
    "platform": "PC",
    "downlink": "10",
    "effective_type": "4g",
    "round_trip_time": "0",
    "update_version_code": "170400",
    "msToken": "",
}


async def _signed_get(path: str, params: dict) -> dict:
    """带 a_bogus 签名的 GET。参数按字符串化后签名再 urlencode。"""
    flat = {**_COMMON, **{k: str(v) for k, v in params.items()}}
    a_bogus = quote(ABogus().get_value(flat), safe="")
    url = f"{_DOUYIN}{path}?{urlencode(flat)}&a_bogus={a_bogus}"
    async with httpx.AsyncClient(timeout=12, trust_env=False, headers={
        "User-Agent": _UA,
        "Cookie": DOUYIN_COOKIE,
        "Referer": f"{_DOUYIN}/",
    }) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def search_videos(keyword: str, count: int = 10) -> list[dict]:
    """按关键词搜索视频，返回 [{aweme_id, desc}]。"""
    params = {
        "search_channel": "aweme_video_web",
        "keyword": keyword,
        "search_source": "normal_search",
        "query_correct_type": 1,
        "is_filter_search": 0,
        "from_group_id": "",
        "offset": 0,
        "count": count,
        "need_awem_video": 0,
        "search_id": "",
        "list_type": 1,
        "pc_libra_divert": "Windows",
    }
    data = await _signed_get("/aweme/v1/web/search/item/", params)
    out = []
    for aw in (data.get("data") or {}).get("data") or []:
        a = (aw.get("aweme_info") or {})
        if a.get("aweme_id"):
            out.append({"aweme_id": a["aweme_id"], "desc": (a.get("desc") or "")[:40]})
    return out


async def fetch_comments(aweme_id: str, count: int = 20) -> list[str]:
    """读取视频评论，返回纯文本列表。"""
    params = {
        "aweme_id": aweme_id,
        "cursor": 0,
        "count": count,
        "item_type": 0,
        "insert_ids": "",
        "whale_cut_token": "",
        "cut_version": 1,
        "rcFT": "",
    }
    data = await _signed_get("/aweme/v1/web/comment/list/", params)
    out = []
    for c in (data.get("data") or {}).get("comments") or []:
        text = (c.get("text") or "").strip()
        if text:
            import re
            out.append(re.sub(r"<[^>]+>", "", text)[:160])
    return out


async def douyin_discuss(keyword: str, chat_text) -> dict:
    """热点关键词 → 搜视频 → 读热评 → LLM 概括讨论。"""
    if not DOUYIN_COOKIE:
        return {"ok": False, "reason": "js_or_login",
                "hint": "可选配置：.env.local 中设置 DOUYIN_COOKIE（浏览器登录 www.douyin.com 后 F12 复制 Cookie 整串），即可读取抖音热点的真实评论区"}
    try:
        videos = await search_videos(keyword, count=5)
        if not videos:
            return {"ok": False, "reason": "no_content"}
        comments: list[str] = []
        for v in videos:
            try:
                cs = await fetch_comments(v["aweme_id"], count=20)
                comments.extend(cs[:5])
            except Exception:
                continue
            if len(comments) >= 12:
                break
        if not comments:
            return {"ok": False, "reason": "no_content",
                    "hint": "已配置 DOUYIN_COOKIE，但未能读到评论（Cookie 可能过期或签名失效，可重新复制 Cookie 后重启）"}
    except Exception as e:
        logger.info("[douyin] discuss chain failed: %s", e)
        return {"ok": False, "reason": "js_or_login",
                "hint": "抖音接口请求失败（Cookie 过期或风控），建议重新复制浏览器 Cookie 更新 .env.local 后重启"}

    try:
        prompt = (
            f"热点标题：{keyword}\n\n以下是抖音网友的相关评论：\n" + "\n".join(comments) +
            "\n\n用2-3句话概括评论区主要在讨论什么（核心观点/争议/情绪）。只依据内容，不要编造。"
        )
        summary = await chat_text(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是新闻编辑，擅长提炼网络评论区的核心。",
            temperature=0.3,
        )
    except Exception as e:
        logger.warning("[douyin] llm failed: %s", e)
        return {"ok": False, "reason": "llm_failed"}

    text = (summary or "").strip()[:500]
    if not text:
        return {"ok": False, "reason": "llm_failed"}
    return {"ok": True, "kind": "douyin_comments", "summary": text}
