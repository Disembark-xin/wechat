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

    def test_message_is_paginated_into_five_short_fields(self):
        config = {
            "birthdays": [],
            "todos": [{"title": "提交报告", "due": "2026-09-20T18:07:00"}],
            "note_ch": "加油",
            "note_en": "Keep going"
        }

        pages = build_message(config, self.weather, self.now)

        self.assertGreaterEqual(len(pages), 2)
        self.assertTrue(all(set(page) == {"line1", "line2", "line3", "line4", "line5"} for page in pages))
        values = [page[f"line{i}"]["value"] for page in pages for i in range(1, 6)]
        self.assertTrue(all(len(value) <= 20 for value in values))
        message = "\n".join(values)
        self.assertIn("天气：晴", message)
        self.assertIn("提交报告", message)
        self.assertIn("今天截止", message)
        self.assertIn("生日提醒", message)
        self.assertIn("加油", message)


if __name__ == "__main__":
    unittest.main()
