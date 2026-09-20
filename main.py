#!/usr/bin/env python3
"""GitHub Actions + 微信公众号每日提醒。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

try:
    from zhdate import ZhDate
except ImportError:
    ZhDate = None

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/template/send"
TZ = ZoneInfo("Asia/Shanghai")
WEEKDAYS = "一二三四五六日"
ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)}$")


class ReminderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Task:
    title: str
    due: datetime | None


def resolve_env(value: Any) -> Any:
    """把配置中的 ${NAME} 替换为同名环境变量。"""
    if isinstance(value, str):
        matched = ENV_PATTERN.fullmatch(value.strip())
        return os.getenv(matched.group(1), "") if matched else value
    if isinstance(value, list):
        return [resolve_env(item) for item in value]
    if isinstance(value, dict):
        return {key: resolve_env(item) for key, item in value.items()}
    return value


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReminderError(f"找不到配置文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ReminderError(f"config.txt 格式错误：第 {exc.lineno} 行 {exc.msg}") from exc
    if not isinstance(config, dict):
        raise ReminderError("config.txt 顶层必须是 JSON 对象")
    return resolve_env(config)


def required(config: dict[str, Any], key: str) -> str:
    value = str(config.get(key, "")).strip()
    if not value:
        raise ReminderError(f"缺少配置：{key}")
    return value


def get_json(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=15, **kwargs)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ReminderError(f"网络请求失败：{exc}") from exc
    if not isinstance(result, dict):
        raise ReminderError("接口返回了无法识别的数据")
    return result


def get_access_token(config: dict[str, Any]) -> str:
    result = get_json(TOKEN_URL, params={
        "grant_type": "client_credential",
        "appid": required(config, "app_id"),
        "secret": required(config, "app_secret"),
    })
    token = result.get("access_token")
    if not token:
        raise ReminderError(f"获取微信 access_token 失败：{result.get('errcode')} {result.get('errmsg')}")
    return str(token)


def clean_host(host: str) -> str:
    return host.removeprefix("https://").removeprefix("http://").strip().strip("/")


def compass_chinese(compass: str) -> str:
    names = {
        "n": "北风", "nne": "东北偏北风", "ne": "东北风", "ene": "东北偏东风",
        "e": "东风", "ese": "东南偏东风", "se": "东南风", "sse": "东南偏南风",
        "s": "南风", "ssw": "西南偏南风", "sw": "西南风", "wsw": "西南偏西风",
        "w": "西风", "wnw": "西北偏西风", "nw": "西北风", "nnw": "西北偏北风",
        "vrb": "风向不定", "none": "无持续风向",
    }
    return names.get(compass.lower(), compass or "未知")


def get_weather(config: dict[str, Any]) -> dict[str, str]:
    """优先使用新版专属 API Host，未填写时兼容旧公共域名。"""
    region = required(config, "region")
    key = required(config, "weather_key")
    api_host = clean_host(str(config.get("weather_api_host", "")))
    headers = {"X-QW-Api-Key": key, "Accept-Encoding": "gzip"}
    geo_base = f"https://{api_host}" if api_host else "https://geoapi.qweather.com"
    geo = get_json(
        f"{geo_base}/geo/v2/city/lookup",
        params={"location": region, "range": "cn", "number": 1, "lang": "zh"},
        headers=headers,
    )
    locations = geo.get("location")
    if not isinstance(locations, list) or not locations:
        raise ReminderError(f"和风天气找不到地区：{region}（code={geo.get('code', 'unknown')}）")
    location = locations[0]

    if api_host:
        current = get_json(
            f"https://{api_host}/weather/v1/current/{location.get('lat')}/{location.get('lon')}",
            params={"lang": "zh"}, headers=headers,
        )
        condition = current.get("condition", {})
        temperature = current.get("temperature", {})
        wind = current.get("wind", {})
        direction = wind.get("direction", {}) if isinstance(wind, dict) else {}
        return {
            "region": str(location.get("name", region)),
            "weather": str(condition.get("text", "未知")),
            "temp": f"{temperature.get('value', '--')}{temperature.get('unit', '°C')}",
            "wind_dir": compass_chinese(str(direction.get("compass", ""))),
            "attribution": "天气数据：和风天气",
        }

    legacy = get_json(
        "https://devapi.qweather.com/v7/weather/now",
        params={"location": location.get("id"), "lang": "zh"}, headers=headers,
    )
    weather_now = legacy.get("now")
    if legacy.get("code") != "200" or not isinstance(weather_now, dict):
        raise ReminderError(f"获取天气失败：code={legacy.get('code', 'unknown')}")
    return {
        "region": str(location.get("name", region)),
        "weather": str(weather_now.get("text", "未知")),
        "temp": f"{weather_now.get('temp', '--')}°C（体感 {weather_now.get('feelsLike', '--')}°C）",
        "wind_dir": f"{weather_now.get('windDir', '未知')} {weather_now.get('windScale', '--')}级",
        "attribution": "天气数据：和风天气",
    }


def safe_solar_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        if month == 2 and day == 29:
            return date(year, 2, 28)
        raise


def next_birthday(raw: str, today: date) -> date:
    lunar = raw.startswith("r")
    value = raw[1:] if lunar else raw
    try:
        _, month_text, day_text = value.split("-")
        month, day = int(month_text), int(day_text)
    except (ValueError, AttributeError) as exc:
        raise ReminderError(f"生日格式错误：{raw}") from exc
    for year in (today.year, today.year + 1, today.year + 2):
        if lunar:
            if ZhDate is None:
                raise ReminderError("农历生日需要安装 zhdate")
            try:
                candidate = ZhDate(year, month, day).to_datetime().date()
            except (TypeError, ValueError):
                continue
        else:
            candidate = safe_solar_date(year, month, day)
        if candidate >= today:
            return candidate
    raise ReminderError(f"无法计算生日：{raw}")


def birthday_text(config: dict[str, Any], today: date) -> str:
    birthdays = config.get("birthdays", [])
    if not isinstance(birthdays, list):
        raise ReminderError("birthdays 必须是数组")
    lines: list[str] = []
    for item in birthdays:
        if not isinstance(item, dict) or not str(item.get("birthday", "")).strip():
            continue
        name = str(item.get("name", "")).strip() or "生日"
        days = (next_birthday(str(item["birthday"]), today) - today).days
        lines.append(f"今天是{name}！" if days == 0 else f"距离{name}还有 {days} 天")
    return "\n".join(lines) or "暂无生日提醒"


def parse_due(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReminderError(f"待办截止时间格式错误：{value}") from exc
    if result.tzinfo is None:
        if "T" not in value:
            result = result.replace(hour=23, minute=59, second=59)
        result = result.replace(tzinfo=TZ)
    return result.astimezone(TZ)


def load_tasks(config: dict[str, Any]) -> list[Task]:
    raw_tasks = config.get("todos", [])
    if not isinstance(raw_tasks, list):
        raise ReminderError("todos 必须是数组")
    tasks: list[Task] = []
    for index, item in enumerate(raw_tasks, 1):
        if not isinstance(item, dict):
            raise ReminderError(f"第 {index} 条待办必须是对象")
        if str(item.get("status", "pending")).lower() in {"done", "completed", "cancelled"}:
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            raise ReminderError(f"第 {index} 条待办缺少 title")
        tasks.append(Task(title, parse_due(item.get("due"))))
    return sorted(tasks, key=lambda item: (item.due is None, item.due or datetime.max.replace(tzinfo=TZ)))


def duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, remain = divmod(seconds, 86400)
    hours, remain = divmod(remain, 3600)
    minutes = remain // 60
    if days:
        return f"{days}天{hours}小时"
    if hours:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


def remaining(due: datetime | None, now: datetime) -> str:
    if due is None:
        return "无截止时间"
    seconds = (due - now).total_seconds()
    if seconds < 0:
        return f"已逾期{duration(-seconds)}"
    if due.date() == now.date():
        return f"今天截止，还剩{duration(seconds)}"
    return f"还剩{duration(seconds)}"


def build_message(config: dict[str, Any], weather: dict[str, str], now: datetime) -> list[dict[str, dict[str, str]]]:
    """两张卡：天气信息，以及一行待办、生日、纪念日。"""
    tasks = load_tasks(config)
    # 模板负责显示标签；值保持完整，手机可按屏幕宽度自然换行。
    todos = "；".join(" ".join(task.title.split()) for task in tasks) or "今天没有未完成待办"
    birthday = "；".join(birthday_text(config, now.date()).splitlines())

    love_day = "未设置纪念日"
    if str(config.get("love_date", "")).strip():
        try:
            start = date.fromisoformat(str(config["love_date"]).strip())
        except ValueError as exc:
            raise ReminderError(f"love_date 格式错误：{config['love_date']}") from exc
        love_day = f"已经 {max(0, (now.date() - start).days)} 天"

    def field(value: str) -> dict[str, str]:
        return {"value": value, "color": "#173177"}

    return [
        {
            "date": field(f"{now:%Y年%m月%d日} 星期{WEEKDAYS[now.weekday()]}"),
            "region": field(weather["region"]),
            "weather": field(weather["weather"]),
            "temp": field(weather["temp"]),
            "wind_dir": field(weather["wind_dir"]),
        },
        {
            "todos": field(todos),
            "birthday": field(birthday),
            "love_day": field(love_day),
        },
    ]


def prepare_deliveries(
    config: dict[str, Any], pages: list[dict[str, dict[str, str]]]
) -> list[tuple[str, dict[str, dict[str, str]]]]:
    """优先使用两个专用模板；尚未配置时兼容已工作的 line1～line5 模板。"""
    weather_id = str(config.get("weather_template_id", "")).strip()
    reminder_id = str(config.get("reminder_template_id", "")).strip()
    if weather_id or reminder_id:
        if not weather_id or not reminder_id:
            raise ReminderError("请同时配置 WECHAT_WEATHER_TEMPLATE_ID 和 WECHAT_REMINDER_TEMPLATE_ID")
        return [(weather_id, pages[0]), (reminder_id, pages[1])]

    template_id = required(config, "template_id")
    labels = {
        "date": "日期", "region": "地区", "weather": "天气",
        "temp": "温度", "wind_dir": "风向",
        "todos": "今日待办", "birthday": "生日提醒", "love_day": "在一起",
    }
    deliveries = []
    for page in pages:
        values = [f"{labels[key]}：{item['value']}" for key, item in page.items()]
        values += [" "] * (5 - len(values))
        data = {
            f"line{i}": {"value": value, "color": "#173177"}
            for i, value in enumerate(values, 1)
        }
        deliveries.append((template_id, data))
    return deliveries


def send_message(
    config: dict[str, Any], token: str, user: str,
    data: dict[str, dict[str, str]], *, template_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "touser": user,
        "template_id": template_id or required(config, "template_id"),
        "data": data,
    }
    if str(config.get("url", "")).strip():
        payload["url"] = str(config["url"]).strip()
    try:
        response = requests.post(SEND_URL, params={"access_token": token}, json=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ReminderError(f"发送微信消息失败：{exc}") from exc
    if result.get("errcode") != 0:
        raise ReminderError(f"发送给 OpenID …{user[-6:]} 失败：{result.get('errcode')} {result.get('errmsg')}")
    print(f"发送成功：OpenID …{user[-6:]}，msgid={result.get('msgid', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="微信公众号每日提醒")
    parser.add_argument("--config", default="config.txt")
    parser.add_argument("--dry-run", action="store_true", help="不请求天气和微信，只预览")
    args = parser.parse_args()
    config = load_config(Path(args.config))
    now = datetime.now(TZ)
    if args.dry_run:
        preview_weather = {
            "region": str(config.get("region", "未设置")), "weather": "晴（预览数据）",
            "temp": "25°C（预览数据）", "wind_dir": "东南风（预览数据）",
            "attribution": "天气数据：和风天气",
        }
        print(json.dumps(build_message(config, preview_weather, now), ensure_ascii=False, indent=2))
        return 0

    pages = build_message(config, get_weather(config), now)
    deliveries = prepare_deliveries(config, pages)
    token = get_access_token(config)
    users = config.get("user", [])
    if not isinstance(users, list) or not users:
        raise ReminderError("user 必须是包含至少一个 OpenID 的数组")
    for user in users:
        for template_id, data in deliveries:
            send_message(config, token, str(user).strip(), data, template_id=template_id)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReminderError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
