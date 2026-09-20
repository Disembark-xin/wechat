import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from main import TZ, build_message, load_config, next_birthday, remaining


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 20, 8, 7, tzinfo=TZ)
        self.weather = {
            "region": "郑州", "weather": "晴", "temp": "25°C",
            "wind_dir": "东南风", "attribution": "天气数据：和风天气",
        }

    def test_config_resolves_environment(self):
        raw = {"app_secret": "${WECHAT_APP_SECRET}", "region": "郑州市"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.txt"
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"WECHAT_APP_SECRET": "secret-value"}):
                config = load_config(path)
        self.assertEqual(config["app_secret"], "secret-value")

    def test_remaining_time(self):
        due = datetime(2026, 9, 20, 18, 7, tzinfo=TZ)
        self.assertEqual(remaining(due, self.now), "今天截止，还剩10小时0分钟")

    def test_next_solar_birthday(self):
        self.assertEqual(next_birthday("1997-01-01", date(2026, 9, 20)), date(2027, 1, 1))

    def test_message_contains_weather_todo_and_countdown(self):
        config = {
            "birthdays": [],
            "todos": [
                {
                    "title": "提交报告",
                    "due": "2026-09-20T18:07:00"
                }
            ],
            "note_ch": "加油",
            "note_en": "Keep going"
        }

        data = build_message(config, self.weather, self.now)

        self.assertEqual(data["date"]["value"], "2026年09月20日 星期日")
        self.assertEqual(data["region"]["value"], "郑州")
        self.assertEqual(data["weather"]["value"], "晴")
        self.assertEqual(data["temp"]["value"], "25°C")
        self.assertEqual(data["wind_dir"]["value"], "东南风")
        self.assertIn("提交报告", data["todos"]["value"])
        self.assertIn("今天截止", data["remaining"]["value"])
        self.assertIn("生日提醒", data["birthday"]["value"])
        self.assertEqual(data["love_day"]["value"], "未设置纪念日")
        self.assertEqual(data["note_ch"]["value"], "加油")
        self.assertEqual(data["note_en"]["value"], "Keep going")
        self.assertEqual(data["attribution"]["value"], "天气数据：和风天气")


if __name__ == "__main__":
    unittest.main()
