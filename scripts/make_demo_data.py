#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_demo_data.py — 生成一份完全虚构的示例聊天记录，用于测试整条管道

数据是程序合成的假数据，不含任何真实人物信息。
用于：
  1. 验证 scripts/ 下的脚本能跑通
  2. 作为仓库的 demo 数据，让新用户先跑通再换自己的数据

用法：
    python make_demo_data.py -o ../examples/demo_chat.json
"""
import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# ---- 输出语言（--lang zh|en，默认 zh）----
LANG = "zh"


def T(zh, en=None, **kw):
    """面向用户的文案。默认返回中文；--lang en 时返回英文（没给英文就回退中文）。
    两种语言都用 {name} 形式的占位符，参数走 kw；没有 kw 就不做格式化。"""
    s = en if (LANG == "en" and en) else zh
    return s.format(**kw) if kw else s


random.seed(42)

CHAR = "小鱼"
USER = "阿木"

# 虚构的说话素材
CHAR_SHORT = ["嗯", "好", "行", "在呢", "咋了", "没事儿", "乐了", "服了",
              "嗯哼", "睡吧", "摸摸", "笑死", "好叭", "贴贴", "抱抱"]
CHAR_WORDS = ["今天", "明天", "上班", "吃饭", "睡", "想", "烦", "开心", "累"]
CHAR_BRACKETS = ["[微笑]", "[月亮]", "[亲亲]", "[抱抱]", "[汗]", "[旺柴]"]
CHAR_EMOJI = ["😡", "🥺", "😭", "😊", "🙄", "😴"]

USER_LINES = ["今天怎么样", "吃饭了吗", "我到家了", "在忙吗", "睡了吗",
              "我有点想你", "明天有空吗", "今天好累", "你在干嘛"]


def gen_char_msg():
    r = random.random()
    if r < 0.45:
        return random.choice(CHAR_SHORT)
    if r < 0.62:
        w = random.choice(CHAR_WORDS)
        return f"{w}啊"
    if r < 0.75:
        return "".join(random.choice(CHAR_WORDS) for _ in range(random.randint(1, 2)))
    if r < 0.85:
        return random.choice(CHAR_SHORT) + random.choice(CHAR_BRACKETS)
    if r < 0.93:
        return random.choice(CHAR_SHORT) + random.choice(CHAR_EMOJI)
    return "".join(random.choice(CHAR_SHORT) for _ in range(random.randint(2, 4)))


def main():
    ap = argparse.ArgumentParser(description="生成虚构 demo 聊天记录")
    ap.add_argument("-o", "--output", default="demo_chat.json")
    ap.add_argument("-n", "--count", type=int, default=3000, help="生成消息条数")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh",
                    help="输出语言：zh（默认）中文 / en English")
    args = ap.parse_args()
    global LANG
    LANG = args.lang

    start = datetime(2024, 3, 1, 20, 0, 0)
    msgs = []
    t = start
    for _ in range(args.count):
        t += timedelta(minutes=random.randint(1, 90))
        if random.random() < 0.55:
            sender, content = CHAR, gen_char_msg()
        else:
            sender, content = USER, random.choice(USER_LINES)
        msgs.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "sender": sender,
            "content": content,
            "type": 1,
        })

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(msgs, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(T("生成 {n} 条虚构消息 -> {o}", "Generated {n} fictional messages -> {o}",
            n=len(msgs), o=out))


if __name__ == "__main__":
    main()
