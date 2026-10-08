#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
json2txt.py — 把通用聊天记录 JSON 转成管道标准 txt 格式

支持的输入结构（自动识别）：
  1. 消息数组：[{"time": "...", "sender": "...", "content": "...", "type": 1}, ...]
  2. 带包裹：  {"messages": [...]} / {"data": [...]} / {"chat": [...]}

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


def load_messages(path):
    """载入 JSON 并自动定位消息数组。"""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

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

    raise ValueError("无法识别 JSON 结构，请检查输入文件（需要是消息数组）")


def pick(msg, *keys):
    """从消息里按候选键取值。"""
    for k in keys:
        v = msg.get(k)
        if v not in (None, ""):
            return v
    return ""


def normalize(msg):
    """把一条消息规范成 (time, sender, content, type)。"""
    ts = str(pick(msg, "time", "timestamp", "createTime", "date", "ts"))
    sender = str(pick(msg, "sender", "senderName", "from", "talker", "nickname", "name"))
    content = str(pick(msg, "content", "text", "message", "msg"))
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
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"输入文件不存在：{src}")

    msgs = load_messages(src)

    if args.list_senders:
        counts = {}
        for m in msgs:
            _, sender, _, _ = normalize(m)
            counts[sender or "(空)"] = counts.get(sender or "(空)", 0) + 1
        print(f"共 {len(msgs)} 条消息，发言人：")
        for name, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {name or '(空)'}  × {n}")
        return

    dst = Path(args.output) if args.output else src.with_suffix(".txt")

    out_lines = []
    kept = 0
    skipped = 0
    for m in msgs:
        ts, sender, content, mtype = normalize(m)
        if not ts or not content:
            skipped += 1
            continue
        # 非文本消息：保留为占位标记，让上下文不断裂
        if str(mtype) not in ("1", "text", "Text") and not content.startswith("["):
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

    dst.write_text("\n".join(out_lines), encoding="utf-8")

    print(f"载入 {len(msgs)} 条，写出 {kept} 条，跳过 {skipped} 条")
    print(f"-> {dst}")

    # 校验：如果给了名字，提示实际命中数量
    if args.char_name or args.user_name:
        text = dst.read_text(encoding="utf-8")
        if args.char_name:
            print(f"  对方名「{args.char_name}」出现行数："
                  f"{text.count(args.char_name)}")
        if args.user_name:
            print(f"  本人名「{args.user_name}」出现行数："
                  f"{text.count(args.user_name)}")
        print("  提示：数字应接近消息条数，偏差过大说明名字没对上")


if __name__ == "__main__":
    main()
