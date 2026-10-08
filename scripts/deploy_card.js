#!/usr/bin/env node
/**
 * deploy_card.js — 校验 + 部署角色卡到 SillyTavern
 *
 * SillyTavern 运行中不会扫描角色卡目录，所以改卡后的正确姿势是：
 *   1. 跑这个脚本把卡复制进 characters 目录
 *   2. 浏览器里按 F5 刷新页面
 *   3. 开一个新聊天（旧聊天里的坏样本会持续带偏模型）
 *
 * 用法：
 *   node deploy_card.js -i card.json -d "C:/SillyTavern/data/default-user/characters"
 *   node deploy_card.js -i card.json -d <目录> --dry-run
 */

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const out = { dryRun: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-i" || a === "--input") out.input = argv[++i];
    else if (a === "-d" || a === "--dest") out.dest = argv[++i];
    else if (a === "--dry-run") out.dryRun = true;
    else if (a === "-h" || a === "--help") out.help = true;
  }
  return out;
}

const lineCount = (s) => (s || "").split("\n").filter((x) => x.trim() !== "").length;

function main() {
  const args = parseArgs(process.argv);

  if (args.help || !args.input || !args.dest) {
    console.log(`用法: node deploy_card.js -i <角色卡.json> -d <SillyTavern角色目录>
    -i, --input    角色卡 JSON 路径
    -d, --dest     SillyTavern 的 data/default-user/characters 目录
    --dry-run      只校验不复制`);
    process.exit(args.help ? 0 : 1);
  }

  const out = [];
  let card;

  try {
    const raw = fs.readFileSync(args.input, "utf-8");
    card = JSON.parse(raw);
    out.push("JSON 解析: OK");
  } catch (e) {
    console.error("JSON 解析失败: " + e.message);
    process.exit(1);
  }

  const d = card.data || card;
  out.push(`spec: ${card.spec || "(未声明)"}`);
  out.push(`name: ${d.name || "(空)"}`);
  out.push(`first_mes 行数: ${lineCount(d.first_mes)}`);

  const alts = d.alternate_greetings || [];
  alts.forEach((a, i) => out.push(`备选开场白 ${i + 1} 行数: ${lineCount(a)}`));

  const ex = (d.mes_example || "").split("{{user}}");
  let n = 0;
  ex.forEach((g) => {
    if (g.includes("{{char}}")) {
      n++;
      const reply = g.split("{{char}}")[1] || "";
      out.push(`示例 ${n} 回复行数: ${lineCount(reply)}`);
    }
  });

  const book = (d.character_book && d.character_book.entries) || [];
  out.push(`世界书条目: ${book.length}`);

  if (args.dryRun) {
    out.push("--dry-run 模式，未复制文件");
    out.push("提示：first_mes/示例行数如果偏多，模型会学会一次输出很多行");
    console.log(out.join("\n"));
    return;
  }

  if (!fs.existsSync(args.dest)) {
    console.error(`目标目录不存在: ${args.dest}`);
    console.error("请确认 SillyTavern 的 data/default-user/characters 路径");
    process.exit(1);
  }

  const filename = (d.name || path.basename(args.input, ".json"))
    .replace(/[\\/:*?"<>|]/g, "_") + ".json";
  const target = path.join(args.dest, filename);

  fs.copyFileSync(args.input, target);
  out.push(`已复制到: ${target}`);
  out.push(`大小: ${fs.statSync(target).size} bytes`);
  out.push("");
  out.push("接下来：");
  out.push("  1. 浏览器 F5 刷新 SillyTavern");
  out.push("  2. 开一个【新聊天】（旧聊天历史会持续带偏模型）");

  console.log(out.join("\n"));
}

main();
