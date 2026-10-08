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
    python analyze.py -i chat.txt -o stats.txt --char-name "对方" --lang en   # 英文报告
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

# 当前输出语言：zh（默认，中文）/ en（英文），由 --lang 决定。
# 要求：LANG 为 zh 时，输出必须与旧版逐字节一致；因此 zh 文案原样照抄。
LANG = "zh"

# 所有面向用户文案的中英对照表。键为用途，值为 {"zh": ..., "en": ...}；
# 统一用 str.format 占位符，渲染逻辑与语言无关。
TEXTS = {
    # ---- argparse 的 description / help ----
    "app_desc":   {"zh": "聊天记录风格画像（九维度）",
                   "en": "Chat log style profile (nine dimensions)"},
    "h_input":    {"zh": "标准格式 txt",
                   "en": "standard-format txt"},
    "h_output":   {"zh": "输出统计文件",
                   "en": "output stats file"},
    "h_char":     {"zh": "对方（角色）名，留空则取消息最多的人",
                   "en": "character (partner) name; defaults to the most active speaker"},
    "h_user":     {"zh": "本人名，留空则取消息第二多的人",
                   "en": "user (self) name; defaults to the second most active speaker"},
    "h_emoji_top": {"zh": "emoji 排行取前 N",
                    "en": "show the top N emoji"},
    "h_phrase_min": {"zh": "口头禅候选的最小出现次数",
                     "en": "minimum occurrences for a catchphrase candidate"},
    "h_lang":     {"zh": "输出语言：zh（默认）中文 / en 英文",
                   "en": "output language: zh (default) Chinese / en English"},

    # ---- 控制台信息 / 报错 ----
    "err_no_msgs": {"zh": "没解析到消息，请检查输入是否为标准 txt 格式",
                    "en": "No messages parsed; check that the input is in the standard txt format"},
    "err_no_char": {"zh": "数据里没有「{name}」这个人。\n  {tip}\n"
                          "  先用 json2txt.py --list-senders（或 srt2txt.py --list-speakers）确认名字。",
                    "en": "There is no \"{name}\" in the data.\n  {tip}\n"
                          "  Use json2txt.py --list-senders (or srt2txt.py --list-speakers) to confirm the name."},
    "err_no_user": {"zh": "数据里没有「{name}」这个人。\n  {tip}",
                    "en": "There is no \"{name}\" in the data.\n  {tip}"},
    "tip_prefix": {"zh": "实际出现的发言人：", "en": "Speakers found in the data: "},
    "tip_suffix": {"zh": " 等", "en": " etc."},
    "tip_sep":    {"zh": "、", "en": ", "},
    "ok_line":    {"zh": "OK -> {out}", "en": "OK -> {out}"},
    "done_line":  {"zh": "角色「{char}」/ 本人「{user}」，共 {n} 条",
                   "en": "Character \"{char}\" / User \"{user}\", {n} messages total"},

    # ---- 报告：抬头 ----
    "header":      {"zh": "=== 聊天记录风格画像 ===",
                    "en": "=== Chat Style Profile ==="},
    "summary_total": {"zh": "总消息 {n} 条 | 全程参与者 {p} 人",
                      "en": "{n} messages total | {p} participants"},
    "summary_pair": {"zh": "角色「{char}」 {cm} 条 | 本人「{user}」 {um} 条",
                     "en": "Character \"{char}\": {cm} messages | User \"{user}\": {um} messages"},
    "ratio_line":  {"zh": "双边消息比：{ratio:.2f} : 1",
                    "en": "Two-way message ratio: {ratio:.2f} : 1"},

    # ---- [1] 消息长度分布 ----
    "s1_title":    {"zh": "[1] 消息长度分布（角色）",
                    "en": "[1] Message length distribution (character)"},
    "s1_avg":      {"zh": "    平均 {avg:.1f} 字",
                    "en": "    Average {avg:.1f} chars"},
    "b1":          {"zh": "≤5字", "en": "≤5 chars"},
    "b2":          {"zh": "6-20字", "en": "6-20 chars"},
    "b3":          {"zh": "21-100字", "en": "21-100 chars"},
    "b4":          {"zh": ">100字", "en": ">100 chars"},
    "bucket_line": {"zh": "    {label:>8}  {n:>7}  {pct:>5.1f}%  {bar}",
                    "en": "    {label:>10}  {n:>7}  {pct:>5.1f}%  {bar}"},

    # ---- [2] 每月消息量 ----
    "s2_title":    {"zh": "[2] 每月消息量（关系热度曲线）",
                    "en": "[2] Monthly message volume (relationship heat curve)"},
    "month_line":  {"zh": "    {mo}  {n:>7}  {bar}",
                    "en": "    {mo}  {n:>7}  {bar}"},

    # ---- [3] 活跃时段 ----
    "s3_title":    {"zh": "[3] 角色活跃时段",
                    "en": "[3] Character active hours"},
    "hour_line":   {"zh": "    {h:02d}时  {n:>7}  {bar}",
                    "en": "    {h:02d}:00  {n:>7}  {bar}"},
    "s3_peak":     {"zh": "    → 峰值时段：{peak} 点",
                    "en": "    → Peak hour: {peak}:00"},

    # ---- [4] 方括号表情排行 ----
    "s4_title":    {"zh": "[4] 方括号表情排行（前 {top}，含摊薄率）",
                    "en": "[4] Bracket emoji ranking (top {top}, with dilution rate)"},
    "s4_note":     {"zh": "    摊薄率 = 平均每多少条消息才出现 1 次，写进卡里比「偶尔」有用",
                    "en": "    Dilution rate = messages on average per occurrence; "
                          "more useful in the card than \"occasionally\""},
    "bracket_line": {"zh": "    {e:<10} × {n:<6}  每 {d:.0f} 条出现 1 次",
                     "en": "    {e:<10} × {n:<6}  once every {d:.0f} messages"},

    # ---- [5] Unicode emoji 排行 ----
    "s5_title":    {"zh": "[5] Unicode emoji 排行（前 {top}）",
                    "en": "[5] Unicode emoji ranking (top {top})"},
    "emoji_line":  {"zh": "    {e}  × {n}", "en": "    {e}  × {n}"},

    # ---- [6] 口头禅候选 ----
    "s6_title":    {"zh": "[6] 口头禅候选（出现 ≥{min} 次的完整短句）",
                    "en": "[6] Catchphrase candidates (full phrases appearing ≥{min} times)"},
    "phrase_line": {"zh": "    「{s}」 × {n}", "en": "    \"{s}\" × {n}"},
    "s6_none":     {"zh": "    （没有达到 {min} 次的短句，可调低 --phrase-min）",
                    "en": "    (no phrase reaches {min} occurrences; try lowering --phrase-min)"},

    # ---- [7] 高频词片段 ----
    "s7_title":    {"zh": "[7] 高频词片段（2-4 字）",
                    "en": "[7] High-frequency n-grams (2-4 chars)"},
    "frag_line":   {"zh": "    {w} × {n}", "en": "    {w} × {n}"},
    "s7_none":     {"zh": "    （样本较少或阈值偏高，可调低权重）",
                    "en": "    (small sample or high threshold; try lowering the cutoff)"},

    # ---- [8] 句尾习惯 ----
    "s8_title":    {"zh": "[8] 句尾习惯", "en": "[8] Sentence-ending habits"},
    "tail_line":   {"zh": "    「{w}」结尾 × {n}", "en": "    ending \"{w}\" × {n}"},

    # ---- [9] 连发密度 ----
    "s9_title":    {"zh": "[9] 连发密度（角色一个回合平均发几条）",
                    "en": "[9] Burst density (avg messages per character turn)"},
    "s9_line":     {"zh": "    平均 {avg:.2f} 条/回合 | 最长 {mx} 条",
                    "en": "    Average {avg:.2f} msgs/turn | Longest {mx} msgs"},
    "dist_line":   {"zh": "    {k} 条连发：{n} 次",
                    "en": "    {k}-message burst: {n} times"},
}


def t(key, **kw):
    """按当前语言取文案并格式化；无占位符时直接返回。"""
    s = TEXTS[key][LANG]
    return s.format(**kw) if kw else s


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
    global LANG

    # 先单独解析 --lang，好让 --help 本身也能按所选语言显示；
    # 未知参数交给正式 parser，不在这一步报错。
    _pre = argparse.ArgumentParser(add_help=False)
    _pre.add_argument("--lang", choices=("zh", "en"), default="zh")
    _pre_args, _ = _pre.parse_known_args()
    LANG = _pre_args.lang

    ap = argparse.ArgumentParser(description=t("app_desc"))
    ap.add_argument("-i", "--input", required=True, help=t("h_input"))
    ap.add_argument("-o", "--output", default="stats.txt", help=t("h_output"))
    ap.add_argument("--char-name", default="", help=t("h_char"))
    ap.add_argument("--user-name", default="", help=t("h_user"))
    ap.add_argument("--emoji-top", type=int, default=30, help=t("h_emoji_top"))
    ap.add_argument("--phrase-min", type=int, default=10,
                    help=t("h_phrase_min"))
    ap.add_argument("--lang", choices=("zh", "en"), default="zh",
                    help=t("h_lang"))
    args = ap.parse_args()
    LANG = args.lang

    records = parse_txt(args.input)
    if not records:
        raise SystemExit(t("err_no_msgs"))

    # 自动判断双方
    counter = Counter(s for _, s, _ in records)
    ranked = counter.most_common()
    # 防呆：名字写错时，旧版本会静默产出一份空报告（所有维度都是空的），
    # 用户却看到 "OK"。这里直接拦下来并列出数据里真正有哪些发言人。
    names = [n for n, _ in ranked]
    _tip = (t("tip_prefix") + t("tip_sep").join(names[:12]) +
            (t("tip_suffix") if len(names) > 12 else ""))
    if args.char_name and args.char_name not in names:
        raise SystemExit(t("err_no_char", name=args.char_name, tip=_tip))
    if args.user_name and args.user_name not in names:
        raise SystemExit(t("err_no_user", name=args.user_name, tip=_tip))

    char = args.char_name or (ranked[0][0] if ranked else "")
    user = args.user_name or (ranked[1][0] if len(ranked) > 1 else "")
    # 若显式给了 char 名，user 默认取除 char 外最多者
    if args.char_name and not args.user_name:
        rest = [(n, c) for n, c in ranked if n != char]
        user = rest[0][0] if rest else ""

    texts = [(ts, s, c) for ts, s, c in records if c and not c.startswith("=====")]
    char_msgs = [x for x in texts if x[1] == char]

    L = []
    L.append(t("header"))
    L.append(t("summary_total", n=len(texts), p=len(counter)))
    L.append(t("summary_pair", char=char, cm=len(char_msgs), user=user,
               um=len([x for x in texts if x[1] == user])))
    ratio = len(char_msgs) / max(len([x for x in texts if x[1] == user]), 1)
    L.append(t("ratio_line", ratio=ratio))
    L.append("")

    # ---- 1. 消息长度分布 ----
    lens = [len(c) for _, _, c in char_msgs]
    tot = max(len(lens), 1)
    buckets = [("b1", lambda x: x <= 5), ("b2", lambda x: 5 < x <= 20),
               ("b3", lambda x: 20 < x <= 100), ("b4", lambda x: x > 100)]
    L.append(t("s1_title"))
    L.append(t("s1_avg", avg=sum(lens) / tot))
    for bkey, fn in buckets:
        n = sum(1 for x in lens if fn(x))
        L.append(t("bucket_line", label=t(bkey), n=n, pct=n / tot * 100,
                   bar='█' * int(n / tot * 40)))
    L.append("")

    # ---- 2. 月度量（关系热度曲线）----
    monthly = Counter(ts[:7] for ts, _, _ in texts)
    L.append(t("s2_title"))
    for mo in sorted(monthly):
        L.append(t("month_line", mo=mo, n=monthly[mo],
                   bar='█' * max(1, monthly[mo] // 200)))
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
    L.append(t("s3_title"))
    for h in sorted(hours):
        L.append(t("hour_line", h=h, n=hours[h],
                   bar='█' * max(1, hours[h] // 100)))
    if hours:
        peak = max(hours, key=hours.get)
        L.append(t("s3_peak", peak=peak))
    L.append("")

    all_char_text = "\n".join(c for _, _, c in char_msgs)

    # ---- 4. 方括号表情排行（关键：带摊薄率）----
    bracket = Counter(BRACKET_RE.findall(all_char_text))
    L.append(t("s4_title", top=args.emoji_top))
    L.append(t("s4_note"))
    for e, n in bracket.most_common(args.emoji_top):
        L.append(t("bracket_line", e=e, n=n, d=tot / max(n, 1)))
    L.append("")

    # ---- 5. Unicode emoji 排行 ----
    emojis = Counter(EMOJI_RE.findall(all_char_text))
    L.append(t("s5_title", top=args.emoji_top))
    for e, n in emojis.most_common(args.emoji_top):
        L.append(t("emoji_line", e=e, n=n))
    L.append("")

    # ---- 6. 口头禅候选（重复出现的完整短句）----
    short_sents = Counter()
    for _, _, c in char_msgs:
        c2 = c.strip().rstrip("~？！?!。，,、")
        if 2 <= len(c2) <= 8 and not c2.startswith("["):
            short_sents[c2] += 1
    L.append(t("s6_title", min=args.phrase_min))
    hit = False
    for s2, n in short_sents.most_common(80):
        if n >= args.phrase_min:
            L.append(t("phrase_line", s=s2, n=n))
            hit = True
    if not hit:
        L.append(t("s6_none", min=args.phrase_min))
    L.append("")

    # ---- 7. 高频词片段 ----
    frag = Counter()
    for _, _, c in char_msgs:
        if c.startswith("["):
            continue
        for n in (2, 3, 4):
            frag.update(ngrams(c, n))
    L.append(t("s7_title"))
    shown = 0
    for w, n in frag.most_common(800):
        if n < 50:
            break
        if all(ch in STOPWORDS for ch in w):
            continue
        if len(w) == 2 and w[0] in STOPWORDS and w[1] in STOPWORDS:
            continue
        L.append(t("frag_line", w=w, n=n))
        shown += 1
        if shown >= 50:
            break
    if shown == 0:
        L.append(t("s7_none"))
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
    L.append(t("s8_title"))
    for w, n in tails.most_common(15):
        L.append(t("tail_line", w=w, n=n))
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
        L.append(t("s9_title"))
        L.append(t("s9_line", avg=sum(bursts) / len(bursts), mx=max(bursts)))
        dist = Counter(bursts)
        for k in sorted(dist)[:8]:
            L.append(t("dist_line", k=k, n=dist[k]))
        L.append("")

    out = Path(args.output)
    out.write_text("\n".join(L), encoding="utf-8")
    print(t("ok_line", out=out))
    print(t("done_line", char=char, user=user, n=len(texts)))


if __name__ == "__main__":
    main()
