import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from main import (
    TZ, ReminderError, build_message, load_config, next_birthday,
    prepare_deliveries, recipient_openids, remaining, send_message,
)


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 20, 8, 7, tzinfo=TZ)
        self.weather = {
            "region": "许昌", "weather": "晴", "temp": "25°C",
            "wind_dir": "东南风", "attribution": "天气数据：和风天气",
        }
        self.config = {
            "birthdays": [{"name": "生日", "birthday": "2026-04-02"}],
            "love_date": "2026-08-21",
            "todos": [{"title": "记得带军训刀呦", "status": "pending"}],
            "note_ch": "该睡觉了，现在，马上！",
            "note_en": "It's time for bed, now!",
        }

    def test_config_resolves_environment(self):
        raw = {"weather_template_id": "${WECHAT_WEATHER_TEMPLATE_ID}",
               "reminder_template_id": "${WECHAT_REMINDER_TEMPLATE_ID}"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.txt"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with patch.dict(os.environ, {
                "WECHAT_WEATHER_TEMPLATE_ID": "weather-id",
                "WECHAT_REMINDER_TEMPLATE_ID": "reminder-id",
            }):
                config = load_config(path)
        self.assertEqual(config, {"weather_template_id": "weather-id",
                                  "reminder_template_id": "reminder-id"})

    def test_remaining_time(self):
        due = datetime(2026, 9, 20, 18, 7, tzinfo=TZ)
        self.assertEqual(remaining(due, self.now), "今天截止，还剩10小时0分钟")

    def test_next_solar_birthday(self):
        self.assertEqual(next_birthday("1997-01-01", date(2026, 9, 20)), date(2027, 1, 1))

    def test_requested_content_and_removals(self):
        pages = build_message(self.config, self.weather, self.now)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["region"]["value"], "许昌")
        self.assertEqual(pages[1]["todos"]["value"], "记得带军训刀呦")
        self.assertEqual(pages[1]["birthday"]["value"], "距离生日还有 194 天")
        self.assertEqual(pages[1]["love_day"]["value"], "已经 30 天")
        rendered = json.dumps(pages, ensure_ascii=False)
        for removed in ("剩余时间", "无截止时间", "该睡觉", "It's time", "和风天气", "内容一"):
            self.assertNotIn(removed, rendered)

    def test_long_task_is_not_cut_and_completed_task_is_excluded(self):
        title = "这是一条超过二十个字符但应该完整保留在一个字段里的待办事项"
        self.config["todos"] = [
            {"title": title}, {"title": "完成了", "status": "done"},
            {"title": "第二项\n下一行"},
        ]
        data = build_message(self.config, self.weather, self.now)[1]
        self.assertEqual(data["todos"]["value"], title + "；第二项 下一行")

    def test_two_recipients_and_empty_secret(self):
        config = {"user": ["openid-one", "openid-two", "", "openid-one"]}
        self.assertEqual(recipient_openids(config), ["openid-one", "openid-two"])

    def test_recipients_require_at_least_one_openid(self):
        with self.assertRaises(ReminderError):
            recipient_openids({"user": ["", "  "]})
        with self.assertRaises(ReminderError):
            recipient_openids({"user": "openid-one"})

    def test_empty_tasks(self):
        self.config["todos"] = []
        data = build_message(self.config, self.weather, self.now)[1]
        self.assertEqual(data["todos"]["value"], "今天没有未完成待办")

    def test_two_template_ids_route_correct_data_to_wechat(self):
        self.config.update(weather_template_id="weather-id", reminder_template_id="reminder-id")
        pages = build_message(self.config, self.weather, self.now)
        deliveries = prepare_deliveries(self.config, pages)
        response = Mock()
        response.json.return_value = {"errcode": 0, "msgid": "test"}
        with patch("main.requests.post", return_value=response) as post:
            for template_id, data in deliveries:
                send_message(self.config, "test-token", "test-user", data, template_id=template_id)
        payloads = [call.kwargs["json"] for call in post.call_args_list]
        self.assertEqual([p["template_id"] for p in payloads], ["weather-id", "reminder-id"])
        self.assertEqual(payloads[0]["data"], pages[0])
        self.assertEqual(payloads[1]["data"], pages[1])

    def test_partial_template_setup_fails_before_sending(self):
        self.config["weather_template_id"] = "weather-id"
        with self.assertRaises(ReminderError):
            prepare_deliveries(self.config, build_message(self.config, self.weather, self.now))

    def test_legacy_template_keeps_working_until_ids_are_added(self):
        self.config["template_id"] = "legacy-id"
        deliveries = prepare_deliveries(self.config, build_message(self.config, self.weather, self.now))
        self.assertEqual(len(deliveries), 2)
        self.assertEqual(deliveries[1][1]["line1"]["value"], "今日待办：记得带军训刀呦")
        self.assertEqual(deliveries[1][1]["line4"]["value"], " ")
        self.assertTrue(all(tid == "legacy-id" for tid, _ in deliveries))


if __name__ == "__main__":
    unittest.main()
