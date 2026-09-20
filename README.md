# 微信公众号每日提醒


项目结构与你给的示例一致：核心就是 `.github/`、`config.txt`、`main.py` 和 `requirements.txt`。它显示日期、星期、所在城市的天气、温度、风向、待办、生日倒计时和纪念日，并通过两张公众号模板卡片发送。

## 先处理已经暴露的密钥

你在聊天里粘贴过微信 `app_secret` 和和风天气 Key。请先在微信测试号/公众号后台重置 AppSecret，并在和风天气控制台删除旧 Key、创建新 Key。不要把新密钥直接写入 `config.txt`；本项目已用 `${...}` 从 GitHub Secrets 安全读取。

## 微信模板

最新版使用“每日天气”和“生活提醒”两个模板，完整可复制内容见 [TEMPLATES.md](TEMPLATES.md)。
模板标签与变量必须在同一行，如 `今日待办：{{todos.DATA}}`。

新增两个 GitHub Actions Repository Secrets：

- `WECHAT_WEATHER_TEMPLATE_ID`：天气模板 ID。
- `WECHAT_REMINDER_TEMPLATE_ID`：生活提醒模板 ID。

两个 ID 均配置后，不再显示“内容一、内容二”。
未配置时暂时兼容旧 `WECHAT_TEMPLATE_ID` 的 line1～line5 模板。
只配置一个 ID 会停止发送并给出明确错误。

## 配置 `config.txt`

普通信息直接编辑：

- `region`：城市，例如 `郑州市`。
- `birthdays`：支持多个；公历写 `1997-01-01`，农历写 `r1997-01-01`。
- `love_date`：纪念日，不需要就留空。
- `note_ch` / `note_en`：为兼容保留，新版提醒不显示这些句子。
- `todos`：`status` 为 `pending` 才提醒，完成后改成 `done`。`due` 可写日期或具体时间；不写表示无截止时间。
- `url`：点击微信消息跳转的网址，不需要就留空。

`config.txt` 是严格 JSON，不能写 `#` 注释，也不要使用 Python 的 `eval()` 读取配置。

## 和风天气

和风天气从 2026 年开始逐步停用 `geoapi.qweather.com`、`devapi.qweather.com` 等旧公共域名。请在和风天气控制台的“设置”页复制专属 `API Host`，形式类似 `abc123.xy.qweatherapi.com`。本项目优先调用新版实时天气 v1；`QWEATHER_API_HOST` 留空时仍会尝试旧接口。

## 上传 GitHub

1. 新建 GitHub 仓库，把本目录里的所有文件上传到默认分支。
2. 进入 `Settings → Secrets and variables → Actions`。
3. 在 `Secrets` 新增：

| Secret | 内容 |
| --- | --- |
| `WECHAT_APP_ID` | 新的公众号/测试号 AppID |
| `WECHAT_APP_SECRET` | 重置后的 AppSecret |
| `WECHAT_TEMPLATE_ID` | 旧 line1～line5 模板 ID，仅兼容模式使用 |
| `WECHAT_WEATHER_TEMPLATE_ID` | 天气模板 ID |
| `WECHAT_REMINDER_TEMPLATE_ID` | 生活提醒模板 ID |
| `WECHAT_OPEN_ID` | 接收人的 OpenID |
| `QWEATHER_API_KEY` | 新的和风天气 API Key |

4. 在 `Variables` 新增 `QWEATHER_API_HOST`，填写专属 API Host，不要带 `https://`。
5. 打开 `Actions → 微信每日提醒 → Run workflow`。第一次保留 `dry_run=true` 查看预览；第二次设成 `false` 实际发送。

当前工作流按你的配置每 5 分钟运行一次，可在 `.github/workflows/daily-reminder.yml` 修改 `cron`。

## 本地测试

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py --dry-run
```

## 常见错误

- `40013`：AppID 错误。
- `40125`：AppSecret 错误。
- `40037`：模板 ID 错误或不属于当前 AppID。
- `43004`：对应 OpenID 没关注测试号/公众号。
- `40164`：正式公众号设置了 IP 白名单。GitHub Actions 出口 IP 会变化，正式生产更适合部署到有固定出口 IP 的服务器。
- 定时任务可能延迟；以 Actions 的实际运行记录为准。
