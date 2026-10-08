#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze.py — 聊天记录全量风格画像（九维度，纯本地统计，不调用任何 LLM）

这是整条管道里最核心的一步。角色卡里每一句「她说话很碎」「她爱用某个表情」
都应该有这里的频次数据支撑，而不是凭印象写。

判据：真实频次 + 摊薄率。
  例如「[微笑] 在全部 N 条消息里只出现了 k 次」→ 摊薄率 = N/k。
  把这个数字写进角色卡的 post_history_instructions，模型才知道这是稀有表情。
  凭感觉写「偶尔用」是没用的，模型会把「偶尔」理解成「经常」。

用法：
    python analyze.py -i chat.txt -o stats.txt --char-name "对方" --user-name "我"
    python analyze.py -i chat.txt -o stats.txt --char-name "对方" --emoji-top 40
"""
import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

# emoji 匹配区间
EMOJI_RE = re.compile(
    r'[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF]'
)
# 方括号表情，如 [微笑] [月亮] [亲亲]
BRACKET_RE = re.compile(r'\[[^\[\]]{1,12}\]')

STOPWORDS = set("的了是我你他她它们呢吧啊呀哦哈嘛么在有不没就都也很要这那个人什")


def parse_txt(path):
    """读标准 txt：三行一组（时间/发言人/内容），空行分隔。"""
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


def ngrams(text, n):
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def main():
    ap = argparse.ArgumentParser(description="聊天记录风格画像（九维度）")
    ap.add_argument("-i", "--input", required=True, help="标准格式 txt")
    ap.add_argument("-o", "--output", default="stats.txt", help="输出统计文件")
    ap.add_argument("--char-name", default="", help="对方（角色）名，留空则取消息最多的人")
    ap.add_argument("--user-name", default="", help="本人名，留空则取消息第二多的人")
    ap.add_argument("--emoji-top", type=int, default=30, help="emoji 排行取前 N")
    ap.add_argument("--phrase-min", type=int, default=10,
                    help="口头禅候选的最小出现次数")
    args = ap.parse_args()

    records = parse_txt(args.input)
    if not records:
        raise SystemExit("没解析到消息，请检查输入是否为标准 txt 格式")

    # 自动判断双方
    counter = Counter(s for _, s, _ in records)
    ranked = counter.most_common()
    char = args.char_name or (ranked[0][0] if ranked else "")
    user = args.user_name or (ranked[1][0] if len(ranked) > 1 else "")
    # 若显式给了 char 名，user 默认取除 char 外最多者
    if args.char_name and not args.user_name:
        rest = [(n, c) for n, c in ranked if n != char]
        user = rest[0][0] if rest else ""

    texts = [(ts, s, c) for ts, s, c in records if c and not c.startswith("=====")]
    char_msgs = [x for x in texts if x[1] == char]

    L = []
    L.append(f"=== 聊天记录风格画像 ===")
    L.append(f"总消息 {len(texts)} 条 | 全程参与者 {len(counter)} 人")
    L.append(f"角色「{char}」 {len(char_msgs)} 条 | 本人「{user}」 "
             f"{len([x for x in texts if x[1] == user])} 条")
    ratio = len(char_msgs) / max(len([x for x in texts if x[1] == user]), 1)
    L.append(f"双边消息比：{ratio:.2f} : 1")
    L.append("")

    # ---- 1. 消息长度分布 ----
    lens = [len(c) for _, _, c in char_msgs]
    tot = max(len(lens), 1)
    buckets = [("≤5字", lambda x: x <= 5), ("6-20字", lambda x: 5 < x <= 20),
               ("21-100字", lambda x: 20 < x <= 100), (">100字", lambda x: x > 100)]
    L.append("[1] 消息长度分布（角色）")
    L.append(f"    平均 {sum(lens)/tot:.1f} 字")
    for label, fn in buckets:
        n = sum(1 for x in lens if fn(x))
        L.append(f"    {label:>8}  {n:>7}  {n/tot*100:>5.1f}%  "
                 f"{'█' * int(n/tot*40)}")
    L.append("")

    # ---- 2. 月度量（关系热度曲线）----
    monthly = Counter(ts[:7] for ts, _, _ in texts)
    L.append("[2] 每月消息量（关系热度曲线）")
    for mo in sorted(monthly):
        L.append(f"    {mo}  {monthly[mo]:>7}  {'█' * max(1, monthly[mo] // 200)}")
    L.append("")

    # ---- 3. 活跃时段 ----
    hours = Counter()
    for ts, _, _ in char_msgs:
        m = re.search(r'(\d{1,2}):\d{2}', ts)
        if m:
            hours[int(m.group(1))] += 1
        else:
            try:
                hours[int(ts[11:13])] += 1
            except (ValueError, IndexError):
                pass
    L.append("[3] 角色活跃时段")
    for h in sorted(hours):
        L.append(f"    {h:02d}时  {hours[h]:>7}  {'█' * max(1, hours[h] // 100)}")
    if hours:
        peak = max(hours, key=hours.get)
        L.append(f"    → 峰值时段：{peak} 点")
    L.append("")

    all_char_text = "\n".join(c for _, _, c in char_msgs)

    # ---- 4. 方括号表情排行（关键：带摊薄率）----
    bracket = Counter(BRACKET_RE.findall(all_char_text))
    L.append(f"[4] 方括号表情排行（前 {args.emoji_top}，含摊薄率）")
    L.append("    摊薄率 = 平均每多少条消息才出现 1 次，写进卡里比「偶尔」有用")
    for e, n in bracket.most_common(args.emoji_top):
        L.append(f"    {e:<10} × {n:<6}  每 {tot/max(n,1):.0f} 条出现 1 次")
    L.append("")

    # ---- 5. Unicode emoji 排行 ----
    emojis = Counter(EMOJI_RE.findall(all_char_text))
    L.append(f"[5] Unicode emoji 排行（前 {args.emoji_top}）")
    for e, n in emojis.most_common(args.emoji_top):
        L.append(f"    {e}  × {n}")
    L.append("")

    # ---- 6. 口头禅候选（重复出现的完整短句）----
    short_sents = Counter()
    for _, _, c in char_msgs:
        c2 = c.strip().rstrip("~？！?!。，,、")
        if 2 <= len(c2) <= 8 and not c2.startswith("["):
            short_sents[c2] += 1
    L.append(f"[6] 口头禅候选（出现 ≥{args.phrase_min} 次的完整短句）")
    hit = False
    for s2, n in short_sents.most_common(80):
        if n >= args.phrase_min:
            L.append(f"    「{s2}」 × {n}")
            hit = True
    if not hit:
        L.append(f"    （没有达到 {args.phrase_min} 次的短句，可调低 --phrase-min）")
    L.append("")

    # ---- 7. 高频词片段 ----
    frag = Counter()
    for _, _, c in char_msgs:
        if c.startswith("["):
            continue
        for n in (2, 3, 4):
            frag.update(ngrams(c, n))
    L.append("[7] 高频词片段（2-4 字）")
    shown = 0
    for w, n in frag.most_common(800):
        if n < 50:
            break
        if all(ch in STOPWORDS for ch in w):
            continue
        if len(w) == 2 and w[0] in STOPWORDS and w[1] in STOPWORDS:
            continue
        L.append(f"    {w} × {n}")
        shown += 1
        if shown >= 50:
            break
    if shown == 0:
        L.append("    （样本较少或阈值偏高，可调低权重）")
    L.append("")

    # ---- 8. 句尾习惯 ----
    tails = Counter()
    for _, _, c in char_msgs:
        c = c.strip()
        if not c or c.startswith("["):
            continue
        last = c[-1]
        if last in "！？。~…?!,，哈嘿嘻呵嗯啦呀哦嘛":
            tails[last] += 1
    L.append("[8] 句尾习惯")
    for w, n in tails.most_common(15):
        L.append(f"    「{w}」结尾 × {n}")
    L.append("")

    # ---- 9. 消息连发密度（一个"回合"平均几条）----
    bursts = []
    cur = 0
    prev = None
    for _, s, _ in texts:
        if s == char:
            cur += 1
        else:
            if cur:
                bursts.append(cur)
            cur = 0
        prev = s
    if cur:
        bursts.append(cur)
    if bursts:
        L.append("[9] 连发密度（角色一个回合平均发几条）")
        L.append(f"    平均 {sum(bursts)/len(bursts):.2f} 条/回合 | "
                 f"最长 {max(bursts)} 条")
        dist = Counter(bursts)
        for k in sorted(dist)[:8]:
            L.append(f"    {k} 条连发：{dist[k]} 次")
        L.append("")

    out = Path(args.output)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"OK -> {out}")
    print(f"角色「{char}」/ 本人「{user}」，共 {len(texts)} 条")


if __name__ == "__main__":
    main()
