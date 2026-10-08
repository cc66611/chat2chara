#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_card.py — 角色卡 JSON 校验 + 结构统计

改卡之后必跑。它检查：
  - JSON 是否合法
  - 是否 chara_card_v2 规范
  - 关键字段是否非空
  - first_mes / mes_example 的回复行数（对应「行数控制」那条铁律）
  - 世界书条目数量与触发词

用法：
    python validate_card.py -i card.json
    python validate_card.py -i card.json -o report.txt
"""
import argparse
import json
from pathlib import Path

# ---- 输出语言（--lang zh|en，默认 zh）----
LANG = "zh"


def T(zh, en=None, **kw):
    """面向用户的文案。默认返回中文；--lang en 时返回英文（没给英文就回退中文）。"""
    s = en if (LANG == "en" and en) else zh
    return s.format(**kw) if kw else s



def count_lines(s):
    return len([x for x in (s or "").split("\n") if x.strip()])


def main():
    ap = argparse.ArgumentParser(description="校验 SillyTavern 角色卡")
    ap.add_argument("-i", "--input", required=True, help="角色卡 JSON")
    ap.add_argument("-o", "--output", help="报告输出路径（默认打印）")
    ap.add_argument("--max-lines", type=int, default=6,
                    help="first_mes 行数上限告警阈值")
    ap.add_argument("--max-example-lines", type=int, default=5,
                    help="示例回复行数上限告警阈值")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh",
                    help="输出语言：zh（默认）中文 / en English")
    args = ap.parse_args()
    global LANG
    LANG = args.lang

    L = []
    warn = []

    try:
        _p = Path(args.input)
        if not _p.exists():
            raise SystemExit(T("角色卡文件不存在：{p}\n"
                               "  提示：可以先拿 templates/chara_card_v2_blank.json 试跑一遍。",
                               "Character card file not found: {p}\n"
                               "  Tip: try templates/chara_card_v2_blank.json first.",
                               p=_p))
        card = json.loads(_p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        msg = T("这不是合法的 JSON：{p}\n"
                "  第 {ln} 行第 {col} 列 —— {msg}\n"
                "  提示：角色卡必须是完整的一段 JSON，常见的坑是结尾多了逗号。",
                "Not valid JSON: {p}\n"
                "  At line {ln}, column {col} — {msg}\n"
                "  Tip: a card must be one complete JSON document; a trailing comma is the usual culprit.",
                p=args.input, ln=e.lineno, col=e.colno, msg=e.msg)
        if args.output:
            Path(args.output).write_text(msg, encoding="utf-8")
        raise SystemExit(msg)
    except Exception as e:
        msg = T("JSON 解析失败：{e}", "JSON parse failed: {e}", e=e)
        if args.output:
            Path(args.output).write_text(msg, encoding="utf-8")
        raise SystemExit(msg)

    spec = card.get("spec", "")
    d = card.get("data", card)

    L.append(T("=== 角色卡校验报告 ===", "=== Character Card Validation ==="))
    L.append(T("spec: {s}", "spec: {s}",
               s=spec or T("(未声明，按 v1 平铺字段处理)", "(not declared, treated as v1 flat fields)")))
    if spec == "chara_card_v3":
        L.append(T("      → V3。SillyTavern 现版本读 V3 优先；老版本会回落到 V2 字段。",
                   "      -> V3. Current SillyTavern reads V3 first; older builds fall back to the V2 fields."))
    elif spec == "chara_card_v2":
        L.append(T("      → V2。所有版本都能读，最稳。",
                   "      -> V2. Readable by every version — the safest choice."))
    elif spec in ("", "chara_card_v1"):
        L.append(T("      → V1（平铺字段）。能导入，但不支持世界书 / 多开场白。",
                   "      -> V1 (flat fields). Imports fine, but no lorebook and no alternate greetings."))
    else:
        warn.append(T("spec 是「{s}」，不属于已知的 v1 / v2 / v3 —— SillyTavern 可能不识别",
                      "spec is \"{s}\", not one of the known v1 / v2 / v3 — SillyTavern may not recognize it",
                      s=spec))
    L.append(T("name: {n}", "name: {n}",
               n=d.get("name", "") or T("(空)", "(empty)")))
    L.append("")

    # 必填字段
    L.append(T("--- 字段检查 ---", "--- Field checks ---"))
    for field in ("name", "description", "personality", "scenario",
                  "first_mes", "mes_example"):
        val = d.get(field, "")
        n = len(val) if isinstance(val, str) else 0
        flag = "OK" if n > 0 else T("空！", "EMPTY!")
        if n == 0:
            warn.append(T("字段 {f} 为空", "Field {f} is empty", f=field))
        L.append(T("  {f:<16} {n:>6} 字符  [{flag}]", "  {f:<16} {n:>6} chars  [{flag}]",
                   f=field, n=n, flag=flag))

    phi = d.get("post_history_instructions", "")
    L.append(T("  {f:<16} {n:>6} 字符  [{flag}]", "  {f:<16} {n:>6} chars  [{flag}]",
               f="post_history_instructions", n=len(phi),
               flag="OK" if phi else T("空（建议填写，这是最强的行为控制器）",
                                       "EMPTY (fill this in — it's the strongest behavior control)")))
    if not phi:
        warn.append(T("post_history_instructions 为空，行为控制力会明显下降",
                      "post_history_instructions is empty; behavior control drops noticeably"))
    L.append("")

    # 行数检查（铁律一）
    L.append(T("--- 行数检查（铁律一：模型会模仿示例的行数）---",
               "--- Line-count check (rule #1: the model copies the example's line count) ---"))
    fm = count_lines(d.get("first_mes", ""))
    L.append(T("  first_mes 非空行数：{n}", "  first_mes non-empty lines: {n}", n=fm))
    if fm > args.max_lines:
                warn.append(T("first_mes 有 {a} 行，超过 {b} 行，模型会学着一次输出这么多",
                      "first_mes has {a} lines (limit {b}); the model will learn to output that many",
                      a=fm, b=args.max_lines))

    examples = d.get("mes_example", "")
    groups = examples.split("{{user}}")
    idx = 0
    for g in groups:
        if "{{char}}" not in g:
            continue
        reply = g.split("{{char}}", 1)[1]
        n = count_lines(reply)
        idx += 1
        flag = ""
        if n > args.max_example_lines:
            flag = T("  ← 超长，会导致抢戏", "  <- too long, causes scene-hogging")
            warn.append(T("示例 {i} 回复 {n} 行，超过 {m} 行",
                          "Example {i} reply has {n} lines (limit {m})",
                          i=idx, n=n, m=args.max_example_lines))
        L.append(T("  示例 {i} 回复行数：{n}{f}", "  Example {i} reply lines: {n}{f}", i=idx, n=n, f=flag))
    if idx == 0:
        warn.append(T("mes_example 里没有找到 {{char}} 回复，格式可能不对",
                      "No {{char}} reply found in mes_example; the format may be wrong"))
    L.append("")

    # 世界书
    book = d.get("character_book", {})
    entries = book.get("entries", []) if isinstance(book, dict) else []
    L.append(T("--- 世界书 ---", "--- Lorebook ---"))
    L.append(T("  条目数：{n}", "  Entries: {n}", n=len(entries)))
    for i, e in enumerate(entries, 1):
        keys = e.get("keys", [])
        content = e.get("content", "")
        L.append(T("    {i:>2}. 触发词 {k} ({n} 字符)", "    {i:>2}. Keys {k} ({n} chars)",
                   i=i, k=keys, n=len(content)))
    if len(entries) == 0:
        warn.append(T("世界书为空，建议加 8-15 条覆盖典型场景",
                      "Lorebook is empty; 8-15 entries covering typical scenes are recommended"))
    L.append("")

    # 备选开场白
    alts = d.get("alternate_greetings", [])
    L.append(T("--- alternate_greetings: {n} 条 ---", "--- alternate_greetings: {n} ---", n=len(alts)))
    for i, a in enumerate(alts, 1):
        L.append(T("    {i}. {n} 行", "    {i}. {n} lines", i=i, n=count_lines(a)))
    L.append("")

    if warn:
        L.append(T("=== 需要关注 ===", "=== Needs attention ==="))
        for w in warn:
            L.append(T("  ! {w}", "  ! {w}", w=w))
    else:
        L.append(T("=== 全部检查通过 ===", "=== All checks passed ==="))

    report = "\n".join(L)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"OK -> {args.output}")
        print(T("告警 {n} 条", "{n} warning(s)", n=len(warn)))
    else:
        print(report)


if __name__ == "__main__":
    main()
