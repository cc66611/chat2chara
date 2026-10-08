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
    args = ap.parse_args()

    random.seed(args.seed)

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"输入文件不存在：{src}\n"
                         f"  提示：先用 json2txt.py（或 srt2txt.py）把原始记录转成标准 txt。")
    records = parse_txt(args.input)
    items = [(ts[:7], s, c) for ts, s, c in records if ts and c]
    total = len(items)
    if not total:
        raise SystemExit("没解析到消息")

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
        out.append(f"===== {mo} | 本月 {len(by_month[mo])} 条 → "
                   f"采样 {len(sel)} 条（{segs} 个连续片段）=====")
        for i in sel:
            _, s, c = items[i]
            out.append(f"{s}: {c}")
        grand += len(sel)
        stat.append(f"{mo}  {len(by_month[mo]):>7}  {len(sel):>8}  {segs:>8}")

    outpath = Path(args.output)
    outpath.write_text("\n".join(out), encoding="utf-8")
    statpath = outpath.with_name(outpath.stem + "_stats.txt")
    statpath.write_text("\n".join(stat) + f"\n合计采样：{grand} / {total}\n",
                        encoding="utf-8")

    print(f"采样 {grand} / {total} 条（{len(months)} 个月）")
    print(f"-> {outpath}")
    print(f"-> {statpath}")
    print("提示：把 sampled.txt 分批喂给 LLM 精读，提炼人设与对话示例")


if __name__ == "__main__":
    main()
