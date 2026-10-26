#!/usr/bin/env python3
"""rdm-ui 验收脚本：扫 web/src，抓「写死值」与「风格跑偏值」。

用法：
    python .claude/skills/rdm-ui/scripts/check-tokens.py web/src
    python .claude/skills/rdm-ui/scripts/check-tokens.py docs/ui-design/demo --json
（任何目录都可以传；注释里出现的 #hex / rgb() 不算违规）

判定（任一 fail 即退出码 1）：
  R1 裸颜色：出现 #hex / rgb() / rgba() / hsl()（含 <style> 与内联 style）
  R2 圆角越界：border-radius 不属于 {0, 2px, 4px, 50%, 999px, inherit, var(--rdm-*)}
  R3 字重越界：font-weight 出现 600/700/bold/bolder
  R4 字号越界：font-size 不属于 tokens 的 6 档（12/14/16/18/20/24）
  R5 大阴影：box-shadow 出现 8px 以上模糊且非 var(--rdm-shadow-*)
  R6 !important 用在颜色/圆角/字重上（warn，不 fail）

逃生舱：在违规行尾加注释 `// rdm-allow: 原因` 或 `/* rdm-allow: 原因 */` 可放行该行
（用于第三方内容、用户自定义颜色等真实例外；放行条数会在汇总里打印）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXTS = {".vue", ".css", ".scss", ".sass", ".less", ".ts", ".tsx", ".js", ".html"}

ALLOWED_RADIUS = {"0", "2px", "4px", "50%", "999px", "100%", "inherit", "initial", "unset"}
ALLOWED_FONT_SIZE = {"12px", "14px", "16px", "18px", "20px", "24px", "inherit"}
BAD_WEIGHT = re.compile(r"font-weight\s*:\s*(600|700|bold|bolder)\b")

RE_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b|rgba?\(|hsla?\(")
RE_RADIUS = re.compile(r"border-radius\s*:\s*([^;}\n]+)")
RE_FONTSIZE = re.compile(r"font-size\s*:\s*([^;}\n]+)")
RE_SHADOW = re.compile(r"box-shadow\s*:\s*([^;}\n]+)")
RE_IMPORTANT = re.compile(r"!\s*important")

# 圆角/字号里出现的变量、calc、表达式都放行（由 tokens 保证其取值）
VAR_OK = re.compile(r"var\(--rdm-|calc\(|CLAMP\(|clamp\(", re.I)


def iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in EXTS and "node_modules" not in p.parts:
            yield p


def allowed_line(line: str) -> bool:
    return "rdm-allow" in line


def strip_comments(line: str) -> str:
    """去掉行内注释，避免注释里写 #hex 被误判（G22）。"""
    out = re.sub(r"/\*.*?(\*/|$)", "", line)
    out = re.sub(r"<!--.*?(-->|$)", "", out)
    # 截掉行尾 // 注释；跳过 http(s):// 里的 //
    m = re.search(r"(?<!:)\/\/", out)
    if m and "://" not in out[: m.start() + 1]:
        out = out[: m.start()]
    return out


def split_values(raw: str) -> list[str]:
    return [v.strip() for v in raw.split() if v.strip()]


def check_line(line: str) -> list[tuple[str, str]]:
    """返回 [(规则, 消息), ...]"""
    hits: list[tuple[str, str]] = []
    stripped = line.strip()

    if RE_COLOR.search(stripped):
        hits.append(("R1", "出现写死的颜色（#hex / rgb / hsl）；改用 var(--rdm-*) 或 --el-* 映射"))

    m = RE_RADIUS.search(stripped)
    if m and not VAR_OK.search(m.group(1)):
        values = split_values(m.group(1).replace("/", " "))
        bad = [v for v in values if v not in ALLOWED_RADIUS]
        if bad:
            hits.append(("R2", f"圆角 {bad} 不在允许集合 {{0,2px,4px,50%,999px}}"))

    if BAD_WEIGHT.search(stripped):
        hits.append(("R3", "字重出现 600/700；这套风格上限 500"))

    m = RE_FONTSIZE.search(stripped)
    if m and not VAR_OK.search(m.group(1)):
        value = split_values(m.group(1))[0] if split_values(m.group(1)) else ""
        if value not in ALLOWED_FONT_SIZE:
            hits.append(("R4", f"字号 {value} 不在 12/14/16/18/20/24 档位"))

    m = RE_SHADOW.search(stripped)
    if m and not VAR_OK.search(m.group(1)):
        nums = [int(n) for n in re.findall(r"(\d+)px", m.group(1))]
        if nums and max(nums) >= 8:
            hits.append(("R5", "手写阴影模糊 >=8px；只允许 var(--rdm-shadow-1/3)"))

    if RE_IMPORTANT.search(stripped) and re.search(r"color|radius|font-weight|shadow", stripped):
        hits.append(("R6", "!important 用在颜色/圆角/字重/阴影上（改为提升选择器层级或改映射层）"))

    return hits


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    root = Path(args[0]) if args else Path("web/src")
    if not root.exists():
        print(f"[rdm-ui] 目录不存在：{root}", file=sys.stderr)
        return 2

    fail: list[dict] = []
    warn: list[dict] = []
    allow_count = 0
    scanned = 0

    for path in iter_files(root):
        # tokens.css is the single source that DEFINES the raw values (and
        # check-tokens.py documents them); never lint the definitions file.
        if path.name == "tokens.css":
            continue
        scanned += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:  # pragma: no cover
            print(f"[rdm-ui] 跳过 {path}: {exc}", file=sys.stderr)
            continue
        for no, line in enumerate(lines, 1):
            if allowed_line(line):
                allow_count += 1
                continue
            code = strip_comments(line)
            hits = check_line(code)
            if not hits:
                continue
            for rule, msg in hits:
                item = {"rule": rule, "file": str(path), "line": no, "msg": msg,
                        "text": line.strip()[:160]}
                (warn if rule == "R6" else fail).append(item)

    errors = [i for i in fail if i["rule"] != "R6"]
    if as_json:
        print(json.dumps({"scanned": scanned, "fail": fail, "warn": warn,
                          "allow": allow_count}, ensure_ascii=False, indent=2))
    else:
        for item in fail + warn:
            flag = "FAIL" if item["rule"] != "R6" else "WARN"
            print(f"{flag} [{item['rule']}] {item['file']}:{item['line']}  {item['msg']}")
            print(f"      {item['text']}")
        print(f"\n[rdm-ui] 扫描 {scanned} 个文件：fail {len(errors)}，warn {len(warn)}，"
              f"rdm-allow 放行 {allow_count}")
        if not errors:
            print("[rdm-ui] PASS：写死值已清零。别忘了还要过 SKILL.md 的 10 条清单。")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
