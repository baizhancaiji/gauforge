#!/usr/bin/env python3
"""面⑧正文提及选项 R2 复扫候选生成（B6 续，3.4 unreleased，L5 误报触发）。

B6 三路审计（scripts/audit_prose_options.py）的补强复扫，专收其漏网类
——No-对正文形态（opt=NoEigenTest 误报事故即属此类）与 B6 误拒复查。
两路候选（对 B6 路②的放宽）：

- 路A：keyword 页 Options 章节 #### 条目正文中的全部大写词（不限 B6
  四句式锚，markdown 链接留文本）；
- 路B：keyword 页全文 No* 字面扫描（含 Options 章节外，标记「+章节外」）。

差集基准：入库词典（carrier=word 组合词）。噪声先验：B6 裁决留痕
（docs/plans/audit/review_decisions.txt）——reject_a 直接沿用（B6 已逐条
核实现行手册已删；R2 复核推翻的 4 条在裁决文件登记）；reject_noise 对
No* 候选不采信（R2 已实证存在误拒：td=NoIVOGuess、geom=NoKeepConstants
等），No* 逐条重裁。

输出 --out-dir（默认 docs/plans/audit/）：r2_candidates.json（全量候选，
含上下文句）+ r2_worksheet.txt（人工裁决工作单，按 No*→new→xref 排序）。
纯静态、幂等、输出路径参数化（AGENTS §七/§十）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from web.src.parse.keywords import load_keywords  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "ext", ROOT / "scripts" / "extract_keywords.py")
ext = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ext)

CAPWORD = re.compile(r"\b([A-Z][A-Za-z0-9]+)\b")
NOWORD = re.compile(r"\b(No[A-Z][A-Za-z0-9]*)\b")


def _b6_verdicts(path: Path) -> tuple[set[str], set[str], set[str]]:
    """B6 裁决留痕 → (reject_a, reject_noise, admitted) 形态集。"""
    reject_a: set[str] = set()
    reject_noise: set[str] = set()
    admitted: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return reject_a, reject_noise, admitted
    for ln in lines:
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        form, verdict = parts[0].casefold(), parts[2]
        if verdict == "reject_a":
            reject_a.add(form)
        elif verdict == "reject_noise":
            reject_noise.add(form)
        elif verdict.startswith("admit"):
            admitted.add(form)
    return reject_a, reject_noise, admitted


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接留文本
    text = text.replace("`", "")
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _iter_option_bodies(page: Path):
    """(条目名, 正文) 迭代，仅 Options 章节（与面⑦同规）。"""
    lv2 = lv3 = None
    cur: str | None = None
    body: list[str] = []
    for line in page.read_text(encoding="utf-8").splitlines() + [""]:
        m = ext._CHAPTER_HEADING.match(line)
        if m or line.startswith("####"):
            in_options = ((cur is not None and lv2
                           and "option" in lv2.casefold())
                          or (cur is not None and lv3
                              and "option" in lv3.casefold()))
            if in_options and cur is not None:
                yield cur, "\n".join(body)
            if m:
                if m.group(1) == "##":
                    lv2, lv3 = m.group(2).strip(), None
                else:
                    lv3 = m.group(2).strip()
                cur = None
            else:
                cur = line.lstrip("#").strip()
            body = []
            continue
        if cur is not None:
            body.append(line)


def collect(kb_markdown: Path, words: frozenset[str],
            b6_dir: Path) -> list[dict]:
    """两路扫描 + 差集过滤 → 候选列表（排序确定）。"""
    reject_a, reject_noise, admitted = _b6_verdicts(
        b6_dir / "review_decisions.txt")
    stop = set(ext._RULE_STOP) | set(ext._PROSE_STOP)
    admit_words = {f.split("=", 1)[1] for f in admitted if "=" in f}
    cands: dict[tuple[str, str], dict] = {}

    def add(carrier: str, word: str, path: str, ctx: str, in_options: bool):
        cf = word.casefold()
        key = (carrier.casefold(), cf)
        c = cands.setdefault(key, {
            "carrier": carrier.casefold(), "word": cf, "paths": [],
            "ctx": [], "in_options": in_options})
        if path not in c["paths"]:
            c["paths"].append(path)
        if ctx and ctx not in c["ctx"]:
            c["ctx"].append(ctx)
        c["in_options"] = c["in_options"] or in_options

    kdir = kb_markdown / "keyword"
    for page in sorted(kdir.glob("*.md")):
        slug = page.stem
        if slug in ext.EXCLUDED_SLUGS:
            continue
        for head, body in _iter_option_bodies(page):
            for s in _sentences(body):
                for m in CAPWORD.finditer(s):
                    add(slug, m.group(1), "A", s[:260], True)
        lv2 = lv3 = None
        cur_opt = False
        for line in page.read_text(encoding="utf-8").splitlines():
            m = ext._CHAPTER_HEADING.match(line)
            if m:
                if m.group(1) == "##":
                    lv2, lv3 = m.group(2).strip(), None
                else:
                    lv3 = m.group(2).strip()
                continue
            if line.startswith("####"):
                cur_opt = ((lv2 and "option" in lv2.casefold())
                           or (lv3 and "option" in lv3.casefold()))
            for m in NOWORD.finditer(line):
                add(slug, m.group(1), "B", line.strip()[:260], cur_opt)

    out = []
    for (carrier, cf), c in cands.items():
        form = f"{carrier}={cf}"
        if form in words or cf in stop or len(cf) < 3:
            continue
        if form in reject_a:
            continue  # A 类旧形态（B6 已核实），维持预期警告
        is_no = bool(re.match(r"^no[a-z]", cf))
        # B6 噪声裁决先验仅对非 No* 采信——R2 实证其 No* 存在误拒
        if not is_no and form in reject_noise:
            continue
        c["cls"] = "xref" if (cf in words or cf in admit_words) else "new"
        c["no_pair"] = is_no
        c["ctx"] = c["ctx"][:2]
        out.append(c)
    out.sort(key=lambda c: (not c["no_pair"], c["cls"] != "new",
                            c["carrier"], c["word"]))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="面⑧ R2 复扫候选生成")
    parser.add_argument("--kb-dir", type=Path,
                        default=Path("~/gaussian-kb/data").expanduser(),
                        help="gaussian-kb 结构化数据目录")
    parser.add_argument("--out-dir", type=Path,
                        default=ROOT / "docs" / "plans" / "audit",
                        help="候选产物输出目录")
    parser.add_argument("--dict", type=Path,
                        default=ROOT / "web" / "src" / "parse" / "keywords.txt",
                        help="词典路径（差集基准）")
    args = parser.parse_args(argv)
    words = frozenset(args.dict.read_text(encoding="utf-8").splitlines())
    out = collect(args.kb_dir / "markdown", words, args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "r2_candidates.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = []
    for c in out:
        tag = "No*" if c["no_pair"] else "   "
        lines.append(f"[{tag} {c['cls']}] {c['carrier']}={c['word']}"
                     f"  paths={','.join(c['paths'])}"
                     f"{' +章节外' if not c['in_options'] else ''}")
        for s in c["ctx"]:
            lines.append(f"      | {s}")
    (args.out_dir / "r2_worksheet.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print(f"候选 {len(out)} 条（No* {sum(1 for c in out if c['no_pair'])} 条）"
          f" → {args.out_dir / 'r2_candidates.json'} + r2_worksheet.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
