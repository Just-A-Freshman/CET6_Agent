# Introduction
This is a series of learning agents designed to help you pass the CET-6.
这是一系列用于学习英语六级的AI Agent 或 程序。


# CET6 Translation
这是一个用于学习英语六级的Agent，发布在Coze上。它的核心功能是：
1. 每次从真题句子库（注意是一个句子，而非完整的段落）抽取一个中文翻译句子
2. 等待用户作答；
3. 调用工作流判题，包括确定用户的错误内容以及具体的错误类别，与过往错误（使用数据库存储）进行比较，以及给出最小化改进的参考译文，帮助用户以最小的步伐稳步前进。
4. 最后，判断用户作答情况是否达到预设分数（默认为10分）。如果没有达到，Agent会根据当前题目出一道结构相似的句子，然后回到第二步；反之回到第一步。

由于实现在Coze上，无法跑在本地上，因此仓库中`reading/`只是尽可能展示了这个Agent的所有实现细节。你可以尝试依据这些细节在Coze上复现这个Agent。

Coze网站在线使用：https://www.coze.cn/store/agent/7641143120905814068


# CET6 Reading
这是一个用于英语六级阅读学习的网站程序。它同样贯彻”最小化反馈”的理念，每次只是抽取阅读文章中的一个段落让用户理解，总结大意。它不会设定题目，而是专注于让你理解文章本身。程序内置了多级的降级策略，包括给出关键的单词释义、使用”/”切分句子、给出更多上下文提示。

## 环境要求
- Python 3.9+
- pip

## 安装依赖
```bash
cd ./reading/code
pip install -r requirements.txt
```

## 配置 API Key
在项目根目录创建 `.env` 文件（或编辑已有的），填入你的 DeepSeek API Key：
```ini
DEEPSEEK_API_KEY=sk-your-key-here
```

## 运行 Web 服务
```bash
cd ./reading/code
python reading_web.py
```
随后浏览器打开：http://127.0.0.1:5000

首次启动会自动从 JSON 数据文件初始化 SQLite 数据库（`知识库/reading.db`），之后数据（笔记、练习记录、对话历史）都会持久化在数据库中。

## 工具脚本
| 脚本 | 用途 |
|------|------|
| `reading_web.py` | Web 应用主程序（核心） |
| `build_reading_dataset.py` | 调用 DeepSeek API 将原始文本解析为结构化段落库 |
| `extract_reading_raw.py` | 从 PDF 真题提取原始文本 |
| `reading_practice.py` | CLI 版本的阅读练习（无需浏览器） |
| `migrate_to_sqlite.py` | 将 JSON 数据迁移到 SQLite，通常由 Web 应用自动执行 |