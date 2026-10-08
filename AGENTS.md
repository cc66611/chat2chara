# AGENTS.md

给 AI 编码助手 / 智能体的项目说明。人类请读 [README.md](README.md)。

## 这个项目是什么

chat2chara 把聊天记录（或字幕）转换成 SillyTavern 角色卡。

核心方法：**先从真实语料统计出说话风格特征（九维度），再用这些数字写卡**，
而不是让 AI 凭「你认为这个人是什么样」去编。差别见 README 第一屏的对比图。

## 当用户要求「做一个角色卡」时，按这个顺序做

1. **确定数据源**
   - 聊天记录 JSON → `scripts/json2txt.py`
   - 字幕 `.srt` / `.ass` → `scripts/srt2txt.py`
2. **`scripts/analyze.py` 出九维度统计** —— 这是整个项目的核心，不要跳过。
   输出里的「摊薄率」（平均每 N 条消息出现 1 次）是写卡的关键依据。
3. **`scripts/sample.py` 采样连续片段**（供精读用）
4. **写卡** —— 参照 `docs/02-card-authoring.md`，并遵守 `docs/03-tuning-rules.md` 的三条铁律
5. **`scripts/validate_card.py` 校验**
6. **交付** —— `scripts/deploy_card.js` 部署，或 `scripts/json2png.py` 打包成 PNG 卡

## 硬约束（不要违反）

- **零第三方依赖**：只用 Python 标准库。不要引入 requests / pandas / Pillow / numpy 等。
- **不调用任何 LLM API**：`analyze.py` 和 `sample.py` 全程本地计算。精读那一步可以交给用户自己用 LLM 做。
- **不上传任何数据**：整个管道离线运行。
- **不碰导出与解密**：本项目不提供、不指导、不涉及任何聊天记录的导出、解密或抓取手段。
  微信明确在此列（它从未提供可读导出，所有相关工具都要读加密数据库）。
  也不要把「游戏文本解包」这类逆向工程写进文档。
- **提交前必须跑** `python scripts/check_privacy.py` 并返回 0。

## 常用命令

```bash
cd scripts

# 环境自检（用虚构数据跑通全流程）
python make_demo_data.py -o ../examples/demo_chat.json -n 3000
python json2txt.py -i ../examples/demo_chat.json -o ../examples/demo_chat.txt --char-name "小鱼" --user-name "阿木"
python analyze.py  -i ../examples/demo_chat.txt  -o ../examples/demo_stats.txt --char-name "小鱼" --user-name "阿木"

# 字幕路线
python srt2txt.py -i ep01.srt --list-speakers
python srt2txt.py -i ep01.srt -o ep01.txt --date 2024-01-01

# 交付
python validate_card.py -i card.json
python json2png.py -i card.json -o card.png --avatar avatar.png
```

## 写代码的约定

- **注释和输出一律用中文。** 面向的是中文用户。
- **每个脚本都要防呆。** 文件不存在 / 格式损坏 / 产出为空 / 角色名对不上 ——
  一律给出**中文提示 + 告诉用户该走哪条路**，并返回退出码 1。
  绝对不要甩 Python traceback。（例如 `srt2txt.py` 拿到聊天记录时，
  会说「这看起来不是字幕文件，请改用 json2txt.py」。）
- **改了脚本要同步更新**：`README.md` 的目录结构、`README.en.md` 的对应内容。
- **不加没被要求的功能。** 这个项目的价值在方法论，不在功能数量。
