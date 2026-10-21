#!/usr/bin/env python3
"""面⑤散文提及选项三路互补差集近似全量审计（B6 G10-b，输入勘误计划 §2.13）。

面⑤按 Options 章节 #### 规则提取的组合词条目不能覆盖散文提及的选项
（已确认 `opt=addredundant`、`freq=nnroa` 两形态误报），本脚本按三路
互补差集产出候选缺口清单，供逐条人工复核后裁决入典：

- 路①：全分类页面（markdown/ 全部 md，不限 keyword 页）字面扫描
  「键=选项」形态——键限定为已知 route 关键字面（词典非组合词条目 ∪
  keyword 页 slug 集）、选项须大写字母开头的词形 token，覆盖跨页引用；
- 路②：keyword 页按页 slug 对正文（剥离代码围栏与行内代码后）大写
  开头裸词做归属推断——「slug=词」组合词不在词典者列为候选；
- 路③：官方测试语料（~/g16/tests/com，回归对照样本、决策点 11）route
  节 `key=opt` 命中形态全集，与词典组合词条目差集。

三路结果分别落 JSON（--out-dir，默认项目内 docs/plans/audit/），合并去重；
再经两层过滤产出复核面（B6 审查整改 R1 补齐入库，此前 1262→475 过渡层
无代码、不可复现）：

- warn 层：G8 判定链（check_route_options，词典取 --dict）复过滤——保留
  实际产生 route_option_unknown 的形态（键不在典/键无选项集/唯一前缀
  判活/值形白名单者零警告，不入复核面）→ warn_candidates.json；
- review 层：warn 形态中，非 P2-only（有字面「键=选项」或语料命中证据）
  直接保留；P2-only 形态的宿主条目抓取上下文（snippet 拼接，casefold）
  含选项语义词根 synonym / says to / default / option / keyword 之一者
  保留 → review_candidates.json，其余纯散文普通词提及归因排除 →
  excluded_candidates.json。

注意：warn 层谓词依赖判定链代码版本与词典快照的对应关系（如 field 值形
白名单入库后 field=* 形态不再警告），复现 B6 历史产物须用 B5 时点代码与
词典（程序见 docs/plans/input-verify-gap-b6-prose-audit.md §9）。

纯读取 + 确定性输出，幂等可重跑。

用法：python scripts/audit_prose_options.py [--kb-dir DIR] [--corpus DIR]
      [--dict FILE] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 键/选项词形（首字母字母；选项另要求大写开头——官方选项名书写惯例）
_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
_LIT_KV_RE = re.compile(
    r"(?<![A-Za-z0-9_-])([A-Za-z][A-Za-z0-9'-]*)=([A-Z][A-Za-z0-9'-]*)(?![A-Za-z0-9'-])")
# 路②裸词：大写开头、长度 ≥3、前后非字母（归属推断候选）
_BARE_RE = re.compile(r"(?<![A-Za-z])([A-Z][A-Za-z0-9]{2,30})(?![A-Za-z])")
# 代码围栏与行内代码剥离；markdown 链接整体剥离——链接文本多为他页
# 选项引用（[Freq=ROA](/freq/…)），其键归属属链接文本载体而非当前页 slug，
# 跨页引用由路①字面「键=选项」扫描承接（§2.13 三路互补口径）
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
# Options 章节（## 与 ### 层级，章节名含 option）与 #### 选项条目标题
_CHAPTER_HEADING = re.compile(r"^(##|###)\s+(.+)$")

# route 节定位（# 起始行至空行）
_ROUTE_START = re.compile(r"^[ \t]*#", re.MULTILINE)
# review 层 P2-only 形态的选项语义词根（snippet 拼接 casefold 子串匹配）：
# 官方句式（synonym/says to/default）与选项叙述措辞（option/keyword）。
# 与 B6 历史复核面（475）精确分割：401/401 保留、0/787 误排（R1 复原）。
_REVIEW_ANCHORS = ("synonym", "says to", "default", "option", "keyword")
# 排除归因（机械规则表述，随 excluded_candidates.json 落盘）
_EXCLUDE_REASON = ("P2-only 且宿主条目上下文无选项语义词根"
                   "（synonym/says to/default/option/keyword）"
                   "——纯散文普通词提及，不注入典复核面")
# 路②停用词：普通英文词与文档结构词（大小写敏感全词匹配后 casefold 比对）
_PROSE_STOP = frozenset((
    "the", "this", "that", "these", "those", "there", "then", "than",
    "and", "but", "for", "not", "are", "was", "were", "has", "have",
    "had", "can", "may", "will", "would", "should", "could", "must",
    "with", "without", "from", "into", "only", "also", "all", "any",
    "when", "where", "which", "while", "both", "each", "more", "most",
    "other", "some", "such", "same", "its", "his", "her", "our", "your",
    "their", "one", "two", "three", "first", "second", "third", "last",
    "next", "new", "old", "see", "use", "used", "using", "using", "via",
    "note", "notes", "example", "examples", "option", "options",
    "keyword", "keywords", "default", "defaults", "value", "values",
    "input", "output", "gaussian", "g16", "g09", "g03", "rev", "c01",
    "description", "availability", "related", "synonyms", "version",
))


def load_dict(path: Path) -> tuple[set[str], set[str]]:
    """词典 → (全部词条, 组合词条目)。"""
    words = {w for w in path.read_text(encoding="utf-8").splitlines() if w}
    combo = {w for w in words if "=" in w}
    return words, combo


def keyword_slugs(manifest_path: Path) -> set[str]:
    """keyword 分类页 slug 全集（剔除文章页，与 extract_keywords 同名单）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from extract_keywords import EXCLUDED_SLUGS
    pages = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {str(p.get("slug") or "") for p in pages
            if p.get("category") == "keyword"
            and str(p.get("slug") or "") not in EXCLUDED_SLUGS}


def _link_text(text: str) -> str:
    """markdown 链接 → 链接文本（[Freq=ROA](/freq/) → Freq=ROA）：路①的
    「键=选项」字面扫描保留跨页链接文本中的组合形态（键归属链接文本载体）。"""
    return _MD_LINK_RE.sub(
        lambda mo: mo.group(0)[1:mo.group(0).find("](")], text)


def path1_literal_kv(markdown_dir: Path, known_keys: set[str],
                     combo: set[str]) -> list[dict]:
    """路①：全分类页面字面「键=选项」扫描，与词典组合词条目差集。"""
    hits: dict[tuple[str, str], dict] = {}
    for page in sorted(markdown_dir.rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        rel = str(page.relative_to(markdown_dir))
        for m in _LIT_KV_RE.finditer(_link_text(_INLINE_CODE_RE.sub("", text))):
            key, opt = m.group(1).casefold(), m.group(2).casefold()
            if key not in known_keys or f"{key}={opt}" in combo:
                continue
            hits.setdefault((key, opt), {
                "source": "path1_literal", "key": key, "option": opt,
                "pages": [], "snippets": {}})
            if rel not in hits[(key, opt)]["pages"]:
                hits[(key, opt)]["pages"].append(rel)
                hits[(key, opt)]["snippets"][rel] = text[m.start():m.end() + 60]
    return sorted(hits.values(), key=lambda h: (h["key"], h["option"]))


def path2_prose_bare(markdown_dir: Path, slugs: set[str],
                     words: set[str]) -> list[dict]:
    """路②：keyword 页按 slug 对散文裸词做归属推断，组合词不在典者为候选。

    归属面收窄为「与页主题近邻」（§2.13 路②口径）：仅取 Options 章节
    （两级章节名含 option）#### 选项条目正文中的大写裸词——既有选项条目
    正文中提及的别名/同义词/子形态（opt 页 ModRedundant 条目正文提及
    AddRedundant、freq 页 ROA 条目正文提及 NNROA 为已确认先例）；条目标题
    本身已由面⑤提取，不再重复。全页散扫噪声（普通英文词）不属缺口信号，
    不收集。"""
    kdir = markdown_dir / "keyword"
    hits: dict[tuple[str, str], dict] = {}
    for page in sorted(kdir.glob("*.md")):
        slug = page.stem
        if slug not in slugs:
            continue
        raw_text = page.read_text(encoding="utf-8")
        # 定位 Options 章节内 #### 选项条目正文段落（至下一个标题行为止）
        lv2 = lv3 = None
        cur_opt: str | None = None
        blocks: dict[str, str] = {}  # 选项基名 → 条目正文（围栏外）
        for line in raw_text.splitlines():
            chap = _CHAPTER_HEADING.match(line)
            if chap:
                if chap.group(1) == "##":
                    lv2, lv3 = chap.group(2).strip(), None
                else:
                    lv3 = chap.group(2).strip()
                cur_opt = None
                continue
            if line.startswith("####"):
                cur_opt = None
                if (lv2 and "option" in lv2.casefold()) \
                        or (lv3 and "option" in lv3.casefold()):
                    t = line.lstrip("#").strip()
                    text_n = t.replace("*", "").replace("_", "")
                    text_n = re.sub(r"\[=.*\]$", "", text_n)
                    text_n = re.sub(r"\([^)]*\)", "", text_n)
                    text_n = text_n.split("=", 1)[0].strip()
                    if text_n and " " not in text_n:
                        cur_opt = text_n
                blocks.setdefault(cur_opt or "", "")
                continue
            if cur_opt is not None:
                if not line.startswith("```"):
                    blocks[cur_opt] += line + "\n"
        for opt_name, body in blocks.items():
            text = _MD_LINK_RE.sub(" ", _FENCE_RE.sub(" ",
                   _INLINE_CODE_RE.sub(" ", body)))
            for m in _BARE_RE.finditer(text):
                raw = m.group(1)
                if raw.casefold() in _PROSE_STOP \
                        or raw.casefold() == (opt_name or "").casefold():
                    continue
                opt = raw.casefold()
                if f"{slug}={opt}" in words:
                    continue
                hits.setdefault((slug, opt), {
                    "source": "path2_prose", "key": slug, "option": opt,
                    "raw": raw, "pages": [], "snippets": {}})
                if len(hits[(slug, opt)]["pages"]) < 3:
                    ctx = text[max(0, m.start() - 40):m.end() + 60]
                    hits[(slug, opt)]["pages"].append(
                        f"{slug}#{opt_name}")
                    hits[(slug, opt)]["snippets"][f"{slug}#{opt_name}"] \
                        = " ".join(ctx.split())
    return sorted(hits.values(), key=lambda h: (h["key"], h["option"]))


def path3_corpus(corpus_dir: Path, known_keys: set[str],
                 combo: set[str]) -> list[dict]:
    """路③：官方语料 route 节 key=opt 形态与词典组合词条目差集。"""
    tok_re = re.compile(
        r"(?<![A-Za-z0-9_-])((?:[A-Za-z][A-Za-z0-9'-]*)=([A-Za-z][A-Za-z0-9'()+,./=-]*))"
        r"(?![A-Za-z0-9'-])")
    hits: dict[tuple[str, str], dict] = {}
    files = sorted(corpus_dir.glob("*.com")) if corpus_dir.is_dir() else []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _ROUTE_START.search(text)
        if not m:
            continue
        route = text[m.start():text.find("\n\n", m.start())] \
            if "\n\n" in text[m.start():] else text[m.start():]
        for tm in tok_re.finditer(route.casefold()):
            key, opt = tm.group(1).split("=", 1)[0], tm.group(2)
            if key not in known_keys or f"{key}={opt}" in combo:
                continue
            hits.setdefault((key, opt), {
                "source": "path3_corpus", "key": key, "option": opt,
                "files": []})
            if f.name not in hits[(key, opt)]["files"]:
                hits[(key, opt)]["files"].append(f.name)
    return sorted(hits.values(), key=lambda h: (h["key"], h["option"]))


def warn_layer(merged: list[dict], words: set[str]) -> list[dict]:
    """warn 层：G8 判定链复过滤，保留实际产生 route_option_unknown 的形态。

    词典由调用方显式传入（--dict 快照），不经 load_keywords 缓存；判定链
    代码版本须与词典快照同代（docstring 复现程序说明）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from web.src.parse.keywords import check_route_options
    kept: list[dict] = []
    for entry in merged:
        form = f"{entry['key']}={entry['option']}"
        if any(w.get("kind") == "route_option_unknown"
               for w in check_route_options(form, dictionary=frozenset(words))):
            kept.append(entry)
    return kept


def review_layer(warn: list[dict],
                 p2_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """review 层：warn 形态分流为复核面与归因排除集（docstring 谓词口径）。

    复核面输出两段式：先字面/语料证据形态，后散文词根锚形态（各自保持
    warn 输入序，与 B6 历史产物结构一致）。返回 (review, excluded)；
    二者不相交且并集等于 warn 输入。"""
    snip = {(r["key"], r["option"]): " ".join(r["snippets"].values()).casefold()
            for r in p2_records}
    evidence: list[dict] = []
    anchored: list[dict] = []
    excluded: list[dict] = []
    for entry in warn:
        k = (entry["key"], entry["option"])
        if set(entry["sources"]) != {"path2_prose"}:
            evidence.append(entry)
        elif any(a in snip.get(k, "") for a in _REVIEW_ANCHORS):
            anchored.append(entry)
        else:
            excluded.append({**entry, "reason": _EXCLUDE_REASON})
    return evidence + anchored, excluded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="面⑤散文提及选项三路差集审计")
    parser.add_argument("--kb-dir", type=Path,
                        default=Path("~/gaussian-kb/data").expanduser())
    parser.add_argument("--corpus", type=Path,
                        default=Path("~/g16/tests/com").expanduser())
    parser.add_argument("--dict", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "web" / "src" / "parse" / "keywords.txt")
    parser.add_argument("--out-dir", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "docs" / "plans" / "audit")
    args = parser.parse_args(argv)

    words, combo = load_dict(args.dict)
    slugs = keyword_slugs(args.kb_dir / "page_manifest.json")
    # 已知键面 = 词典非组合词条目 ∪ keyword 页 slug
    known_keys = (words - combo) | slugs

    md = args.kb_dir / "markdown"
    p1 = path1_literal_kv(md, known_keys, combo) if md.is_dir() else []
    p2 = path2_prose_bare(md, slugs, words) if md.is_dir() else []
    p3 = path3_corpus(args.corpus, known_keys, combo) \
        if args.corpus.is_dir() else []

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("path1_literal.json", p1),
                       ("path2_prose.json", p2),
                       ("path3_corpus.json", p3)):
        (args.out_dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # 合并差集汇总：key=option 归并三路来源
    merged: dict[tuple[str, str], dict] = {}
    for item in p1 + p2 + p3:
        k = (item["key"], item["option"])
        entry = merged.setdefault(k, {"key": item["key"],
                                      "option": item["option"],
                                      "sources": []})
        if item["source"] not in entry["sources"]:
            entry["sources"].append(item["source"])
    summary = sorted(merged.values(), key=lambda h: (h["key"], h["option"]))
    (args.out_dir / "merged_candidates.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    warn = warn_layer(summary, words)
    review, excluded = review_layer(warn, p2)
    for name, data in (("warn_candidates.json", warn),
                       ("review_candidates.json", review),
                       ("excluded_candidates.json", excluded)):
        (args.out_dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"路① 字面 键=选项 差集：{len(p1)} 形态 → path1_literal.json")
    print(f"路② 散文裸词归属候选：{len(p2)} 形态 → path2_prose.json")
    print(f"路③ 语料命中形态差集：{len(p3)} 形态 → path3_corpus.json")
    print(f"合并候选（人工复核输入）：{len(summary)} 形态 → merged_candidates.json")
    print(f"warn 层（G8 判定链复过滤）：{len(warn)} 形态 → warn_candidates.json")
    print(f"review 层（字面/语料证据 ∨ 选项语义词根）：{len(review)} 形态"
          f" → review_candidates.json")
    print(f"review 层归因排除（纯散文普通词）：{len(excluded)} 形态"
          f" → excluded_candidates.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
