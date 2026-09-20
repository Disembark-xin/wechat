# 最新微信模板（2026-09-20）

现在每次发送两张卡片。标签和变量必须写在同一行。
这两份模板配合本次新版代码使用；不要保留“内容一、内容二”。

## 模板一：每日天气

```text
日期：{{date.DATA}}
地区：{{region.DATA}}
天气：{{weather.DATA}}
温度：{{temp.DATA}}
风向：{{wind_dir.DATA}}
```

将模板 ID 保存为 GitHub Actions Repository Secret：
`WECHAT_WEATHER_TEMPLATE_ID`。

## 模板二：生活提醒

```text
今日待办：{{todos.DATA}}
生日提醒：{{birthday.DATA}}
在一起：{{love_day.DATA}}
```

将模板 ID 保存为 GitHub Actions Repository Secret：
`WECHAT_REMINDER_TEMPLATE_ID`。

## 设置及验证

1. 在微信测试号后台分别新建上述两个模板。
2. 在 GitHub 仓库 Settings → Secrets and variables → Actions → Secrets，
   添加以上两个 Repository Secrets，值分别为对应模板 ID。
3. Actions → 微信每日提醒 → Run workflow，选择 main，取消勾选 dry_run 后运行。
4. 收到的天气卡应显示“日期：…”而非“内容一：日期：…”；
   生活卡应只有待办、生日、在一起三项。

代码保留旧 WECHAT_TEMPLATE_ID 的兼容模式：尚未添加两个新 Secret 时，
仍使用旧的“内容一～内容五”模板发送删减后的两张卡。
只添加一个新 Secret 会报明确的配置错误，避免发出不匹配的卡片。
两个新 Secret 均配置后，旧 WECHAT_TEMPLATE_ID 不再用于发送，无需删除。

待办标签和内容在同一个模板行；多个待办以分号连接。长文字可能因手机宽度自然换行，
代码不再按 20 个字符截断或拆成多个字段。
不再显示剩余时间、无截止时间、中英文句子和天气来源。
配置中保留的 note_ch/note_en 不再用于本版消息。
本地预览使用示例天气，不能代替手机端实际显示验证。
