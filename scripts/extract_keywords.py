#!/usr/bin/env python3
"""G16 route 关键词字典生成（m2-plan B1，修订说明五）。

数据源：gaussian-kb MCP 结构化知识库的页面清单 page_manifest.json
（官方 HTML 经 gaussian-kb 抽取结构化，与 MCP list_gaussian_pages
同源同数），不再解析原始 HTML。

词条规则（m2-plan §2.1 定稿）：
- keyword 分类页剔除 8 篇文章/技术札记/版本说明页（标题逐一核对）；
- 词条 = slug 全集 + 标题等价变体——标题按「 and 」/「&」切分且各侧
  均为无空格单词时收两侧（如 DensityFit and NoDensityFit）；
- 词条小写化、按码点排序、去重——确定性输出，重跑幂等。

用法：python scripts/extract_keywords.py [--kb-dir DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

# 非关键词页剔除名单（A1 实地核查结论，m2-plan §2.1 留档）：
# 文章/技术札记/版本说明，标题非关键词名。
EXCLUDED_SLUGS = frozenset({
    "afc",             # Modeling Antiferromagnetic Coupling in Gaussian
    "g09_c01",         # Revision C.01（版本说明）
    "nmrcomp",         # Comparing NMR Methods in ChemDraw and Gaussian
    "oniom_technote",  # Investigating the Reactivity ... with ONIOM
    "qst2",            # Transition State Optimizations with Opt=QST2
    "thermo",          # Thermochemistry in Gaussian
    "vcd",             # Studying Chirality with VCD
    "vib",             # Vibrational Analysis in Gaussian
})

# 标题等价变体切分：「X and Y」/「X & Y」（HTML 实体先解码）。
_TITLE_SPLIT = re.compile(r"\s+and\s+|\s*&\s*")
_WORD_KEEP = re.compile(r"[^a-z0-9-]")


def _title_variants(title: str) -> list[str]:
    """标题派生变体：切分后各侧均为无空格单词才收（含单词标题自身）。"""
    text = html.unescape(title or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _TITLE_SPLIT.split(text) if p.strip()]
    if not parts or any(" " in p for p in parts):
        return []
    return parts


def extract(manifest_path: Path) -> list[str]:
    """从结构化页面清单产出排序去重的词条全集。"""
    pages = json.loads(manifest_path.read_text(encoding="utf-8"))
    words: set[str] = set()
    for page in pages:
        if page.get("category") != "keyword":
            continue
        slug = str(page.get("slug") or "")
        if not slug or slug in EXCLUDED_SLUGS:
            continue
        words.add(slug.casefold())
        for variant in _title_variants(str(page.get("title") or "")):
            word = _WORD_KEEP.sub("", variant.casefold())
            if len(word) >= 2:
                words.add(word)
    return sorted(words)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G16 route 关键词字典生成")
    parser.add_argument("--kb-dir", type=Path,
                        default=Path("~/gaussian-kb/data").expanduser(),
                        help="gaussian-kb 结构化数据目录（含 page_manifest.json）")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "web" / "src" / "parse" / "keywords.txt",
                        help="字典输出路径（默认入库位置）")
    args = parser.parse_args(argv)
    manifest = args.kb_dir / "page_manifest.json"
    if not manifest.is_file():
        print(f"页面清单不存在：{manifest}", file=sys.stderr)
        return 1
    words = extract(manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(w + "\n" for w in words), encoding="utf-8")
    print(f"词条 {len(words)} 个 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
