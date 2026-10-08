#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
json2txt.py — 把通用聊天记录 JSON 转成管道标准 txt 格式

支持的输入结构（自动识别）：
  1. 消息数组：[{"time": "...", "sender": "...", "content": "...", "type": 1}, ...]
  2. 带包裹：  {"messages": [...]} / {"data": [...]} / {"chat": [...]}
  3. 文本为分段数组（Telegram 式富文本）："text": ["今天", {"type":"bold","text":"超累"}]

输出格式（管道统一标准）：
    时间行
    发言人行
    内容行
    <空行>

用法：
    python json2txt.py -i input.json -o chat.txt
    python json2txt.py -i input.json -o chat.txt --char-name "对方" --user-name "我"
    python json2txt.py -i input.json -o chat.txt --list-senders
"""
import argparse
import json
import sys
from pathlib import Path

# ---- 输出语言（--lang zh|en，默认 zh）----
LANG = "zh"


def T(zh, en=None, **kw):
    """面向用户的文案。默认返回中文；--lang en 时返回英文（没给英文就回退中文）。
    两种语言都用 {name} 形式的占位符，参数走 kw；没有 kw 就不做格式化。"""
    s = en if (LANG == "en" and en) else zh
    return s.format(**kw) if kw else s



def load_messages(path):
    """载入 JSON 并自动定位消息数组。"""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(T("这不是合法的 JSON 文件：{p}\n"
                   "  出错位置：第 {ln} 行第 {col} 列 —— {msg}\n"
                   "  提示：导出聊天记录时要选「JSON」格式。HTML / CSV / MHT 都要先转换。",
                   "Not a valid JSON file: {p}\n"
                   "  At line {ln}, column {col} — {msg}\n"
                   "  Tip: when exporting a chat log, choose the JSON format. HTML / CSV / MHT must be converted first.",
                   p=path, ln=e.lineno, col=e.colno, msg=e.msg))
    except UnicodeDecodeError:
        sys.exit(T("文件不是 UTF-8 编码：{p}\n"
                   "  提示：用记事本「另存为」选 UTF-8，或换一种导出格式。",
                   "The file is not UTF-8 encoded: {p}\n"
                   "  Tip: re-save it as UTF-8, or export in a different format.",
                   p=path))

    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        for key in ("messages", "data", "chat", "records", "msg"):
            val = raw.get(key)
            if isinstance(val, list):
                return val
        # 字典的 value 全是 list 的情况：取最长的那条
        lists = [v for v in raw.values() if isinstance(v, list)]
        if lists:
            return max(lists, key=len)

    keys = list(raw)[:10] if isinstance(raw, dict) else "（不是字典）"
    sys.exit(T("认不出这份 JSON 的结构：{p}\n"
               "  最外层应该是消息数组 [{{...}}, ...]，或者包在 messages / data / chat / records 里。\n"
               "  这份文件最外层是 {tp}，里面的键是：{keys}",
               "Unrecognized JSON structure: {p}\n"
               "  The top level should be an array of messages [{{...}}, ...], or wrap one in messages / data / chat / records.\n"
               "  This file's top level is {tp}; its keys are: {keys}",
               p=path, tp=type(raw).__name__, keys=keys))


def pick(msg, *keys):
    """从消息里按候选键取值。"""
    for k in keys:
        v = msg.get(k)
        if v not in (None, ""):
            return v
    return ""


def flat_text(v):
    """把文本字段拍平成字符串。

    有些平台（Telegram 等）的 text 是分段数组，用来表示富文本：
        ["今天", {"type": "bold", "text": "超累"}]
    直接 str() 会得到一串 Python 字面量。这里按键取片段再拼接。
    """
    if isinstance(v, list):
        parts = []
        for seg in v:
            if isinstance(seg, str):
                parts.append(seg)
            elif isinstance(seg, dict):
                parts.append(str(seg.get("text", "")))
            else:
                parts.append(str(seg))
        return "".join(parts)
    return str(v)


def normalize(msg):
    """把一条消息规范成 (time, sender, content, type)。"""
    ts = str(pick(msg, "time", "timestamp", "createTime", "date", "ts"))
    # ISO 风格时间（2024-03-01T21:22:00）归一成管道惯用的空格分隔
    if len(ts) > 10 and ts[10] == "T":
        ts = ts[:10] + " " + ts[11:]
    sender = str(pick(msg, "sender", "senderName", "from", "talker", "nickname", "name"))
    content = flat_text(pick(msg, "content", "text", "message", "msg"))
    mtype = pick(msg, "type", "msgType") or 1
    return ts, sender, content, mtype


def main():
    ap = argparse.ArgumentParser(description="聊天记录 JSON → 标准 txt")
    ap.add_argument("-i", "--input", required=True, help="输入 JSON 路径")
    ap.add_argument("-o", "--output", help="输出 txt 路径（默认与输入同目录同名）")
    ap.add_argument("--char-name", default="", help="对方（角色）显示名，用于统计校验")
    ap.add_argument("--user-name", default="", help="本人显示名，用于统计校验")
    ap.add_argument("--list-senders", action="store_true",
                    help="只列出所有发言人及消息数，不做转换")
    ap.add_argument("--keep-non-text", action="store_true",
                    help="保留非文本消息（默认保留，标记为 [类型]）")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh",
                    help="输出语言：zh（默认）中文 / en English")
    args = ap.parse_args()
    global LANG
    LANG = args.lang

    src = Path(args.input)
    if not src.exists():
        sys.exit(T("输入文件不存在：{p}", "Input file not found: {p}", p=src))

    msgs = load_messages(src)

    if args.list_senders:
        counts = {}
        for m in msgs:
            _, sender, _, _ = normalize(m)
            counts[sender or "(空)"] = counts.get(sender or "(空)", 0) + 1
        print(T("共 {n} 条消息，发言人：", "{n} messages, speakers:", n=len(msgs)))
        for name, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {name or T('(空)', '(none)')}  × {n}")
        return

    dst = Path(args.output) if args.output else src.with_suffix(".txt")

    if not msgs:
        sys.exit(T("文件里没找到任何消息：{p}\n"
                   "  提示：JSON 最外层应该是消息数组，或包在 messages / data / chat 字段里。",
                   "No messages found in the file: {p}\n"
                   "  Tip: the top level should be a message array, or wrapped in a messages / data / chat field.",
                   p=src))

    out_lines = []
    kept = 0
    skipped = 0
    for m in msgs:
        ts, sender, content, mtype = normalize(m)
        if not ts or not content:
            skipped += 1
            continue
        # 非文本消息：保留为占位标记，让上下文不断裂
        if str(mtype) not in ("1", "text", "Text", "message", "Message") and not content.startswith("["):
            if args.keep_non_text:
                content = f"[{mtype}]"
            else:
                skipped += 1
                continue
        out_lines.append(ts)
        out_lines.append(sender)
        out_lines.append(content)
        out_lines.append("")
        kept += 1

    if kept == 0:
        sys.exit(T("载入 {n} 条，但一条都没转换出来（全部跳过）。\n"
                   "  常见原因：\n"
                   "    1. 时间字段名不在候选键里（支持 time / timestamp / createTime / date / ts）\n"
                   "    2. 内容字段名不在候选键里（支持 content / text / message / msg）\n"
                   "    3. 全是图片/语音这类非文本消息（可加 --keep-non-text 保留占位）\n"
                   "  先跑一次 --list-senders 看看结构对不对。",
                   "Read {n} messages but converted none (all skipped).\n"
                   "  Common causes:\n"
                   "    1. Time field name not among the candidates (time / timestamp / createTime / date / ts)\n"
                   "    2. Content field name not among the candidates (content / text / message / msg)\n"
                   "    3. Everything is non-text (images/voice); add --keep-non-text to keep placeholders\n"
                   "  Run --list-senders first to check the structure.",
                   n=len(msgs)))

    dst.write_text("\n".join(out_lines), encoding="utf-8")

    print(T("载入 {n} 条，写出 {k} 条，跳过 {s} 条",
            "Loaded {n}, wrote {k}, skipped {s}",
            n=len(msgs), k=kept, s=skipped))
    print(f"-> {dst}")

    # 校验：如果给了名字，提示实际命中数量
    if args.char_name or args.user_name:
        text = dst.read_text(encoding="utf-8")
        if args.char_name:
            print(T("  对方名「{c}」出现行数：{n}",
                    "  Lines matching the character name \"{c}\": {n}",
                    c=args.char_name, n=text.count(args.char_name)))
        if args.user_name:
            print(T("  本人名「{u}」出现行数：{n}",
                    "  Lines matching the user name \"{u}\": {n}",
                    u=args.user_name, n=text.count(args.user_name)))
        print(T("  提示：数字应接近消息条数，偏差过大说明名字没对上",
                "  Tip: each count should be close to the message total; a big gap means the names don't match"))


if __name__ == "__main__":
    main()
