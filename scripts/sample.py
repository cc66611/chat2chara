#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sample.py — 时间分层加权采样

为什么不能随机抽句子：角色卡要学的是「对方怎么接话」，孤立句子学不出来。
所以要抽「连续片段」，保留上下文。同时为了避免只抽到热恋期、丢掉冷淡期，
按「月」分桶 + 按消息量加权配额。

产出给 LLM 精读用的紧凑样本，供后续提炼角色卡。

用法：
    python sample.py -i chat.txt -o sampled.txt --char-name "对方" --user-name "我"
    python sample.py -i chat.txt -o sampled.txt --target 8000 --seed 42
"""
import argparse
import random
from collections import defaultdict
from pathlib import Path

# ---- 输出语言（--lang zh|en，默认 zh）----
LANG = "zh"


def T(zh, en=None, **kw):
    """面向用户的文案。默认返回中文；--lang en 时返回英文（没给英文就回退中文）。
    两种语言都用 {name} 形式的占位符，参数走 kw；没有 kw 就不做格式化。"""
    s = en if (LANG == "en" and en) else zh
    return s.format(**kw) if kw else s



def parse_txt(path):
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    records = []
    i = 0
    while i < len(lines) - 2:
        ts, sender, content = lines[i], lines[i + 1], lines[i + 2]
        if ts.strip() and not content.startswith("====="):
            records.append((ts.strip(), sender.strip(), content))
            i += 4
        else:
            i += 1
    return records


def main():
    ap = argparse.ArgumentParser(description="按时间分层的连续片段采样")
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-o", "--output", default="sampled.txt")
    ap.add_argument("--target", type=int, default=6500, help="目标采样总条数")
    ap.add_argument("--base", type=int, default=120,
                    help="每月保底条数（保证冷月不被丢掉）")
    ap.add_argument("--seg-min", type=int, default=20, help="片段最短条数")
    ap.add_argument("--seg-max", type=int, default=45, help="片段最长条数")
    ap.add_argument("--seed", type=int, default=42, help="随机种子，固定则结果可复现")
    ap.add_argument("--char-name", default="", help="对方名（用于统计输出）")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh",
                    help="输出语言：zh（默认）中文 / en English")
    args = ap.parse_args()
    global LANG
    LANG = args.lang

    random.seed(args.seed)

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(T("输入文件不存在：{p}\n"
                           "  提示：先用 json2txt.py（或 srt2txt.py）把原始记录转成标准 txt。",
                           "Input file not found: {p}\n"
                           "  Tip: run json2txt.py (or srt2txt.py) first to convert your records into the standard txt format.",
                           p=src))
    records = parse_txt(args.input)
    items = [(ts[:7], s, c) for ts, s, c in records if ts and c]
    total = len(items)
    if not total:
        raise SystemExit(T("没解析到消息", "No messages parsed"))

    by_month = defaultdict(list)
    for i, (mo, _, _) in enumerate(items):
        by_month[mo].append(i)
    months = sorted(by_month)

    base_total = args.base * len(months)
    weight = max(args.target - base_total, 1)
    quota = {mo: int(args.base + len(by_month[mo]) / total * weight)
             for mo in months}

    picked = {}
    for mo in months:
        idxs = by_month[mo]
        q = quota[mo]
        got = set()
        tries = 0
        while len(got) < q and tries < 5000:
            tries += 1
            start = random.randrange(len(idxs))
            length = random.randint(args.seg_min, args.seg_max)
            end = min(start + length, len(idxs))
            for p in range(start, end):
                got.add(idxs[p])
        picked[mo] = got

    out = []
    stat = ["month    total   sampled  segments", "-" * 38]
    grand = 0
    for mo in months:
        sel = sorted(picked[mo])
        segs = 0
        prev = None
        for i in sel:
            if prev is None or i != prev + 1:
                segs += 1
            prev = i
        out.append(T("===== {mo} | 本月 {t} 条 → 采样 {s} 条（{g} 个连续片段）=====",
                     "===== {mo} | {t} this month -> sampled {s} ({g} continuous segments) =====",
                     mo=mo, t=len(by_month[mo]), s=len(sel), g=segs))
        for i in sel:
            _, s, c = items[i]
            out.append(f"{s}: {c}")
        grand += len(sel)
        stat.append(f"{mo}  {len(by_month[mo]):>7}  {len(sel):>8}  {segs:>8}")

    outpath = Path(args.output)
    outpath.write_text("\n".join(out), encoding="utf-8")
    statpath = outpath.with_name(outpath.stem + "_stats.txt")
    statpath.write_text("\n".join(stat) + "\n" +
                        T("合计采样：{g} / {t}", "Total sampled: {g} / {t}", g=grand, t=total) + "\n",
                        encoding="utf-8")

    print(T("采样 {g} / {t} 条（{m} 个月）", "Sampled {g} / {t} messages ({m} months)",
            g=grand, t=total, m=len(months)))
    print(f"-> {outpath}")
    print(f"-> {statpath}")
    print(T("提示：把 sampled.txt 分批喂给 LLM 精读，提炼人设与对话示例",
            "Tip: feed sampled.txt to an LLM in batches and read it closely to extract persona and dialogue examples."))


if __name__ == "__main__":
    main()
