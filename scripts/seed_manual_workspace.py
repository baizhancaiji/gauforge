#!/usr/bin/env python3
"""人工测试实例种子数据填充（m4-acceptance 走查样本固化版）。

向已启动的隔离实例（development.md §6.2）导入 scripts/seed_samples/ 下的
种子候选，并自动接线 Link0 符号引用（@task:<id> 需导入后的真实任务 id，
脚本经分块编辑端点回填）。覆盖场景：

- 水分子三段链（opt→freq→sp，%OldChk 续读）、续用形态两段对（%Chk）
- 慢优化/续跑目标（拉伸萘 opt 约 5 分钟、TD 单点、苯环 freq）
- 组合流候选（乙醇 4 构象成队、甲醇单构象 <2 失败分支）
- 失败注入（伪关键字 opt）与依赖校验对（环/悬引用/前向引用）

幂等：按文件名比对既有候选，已存在者跳过导入；引用接线对已入队成员
（候选不可编辑）报告跳过、不视为错误。重复执行安全。

用法：uv run python scripts/seed_manual_workspace.py [--base-url http://127.0.0.1:8398]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent / "seed_samples"

# (文件名, 用途说明)——导入顺序即候选 id 升序，说明随汇总打印。
SEEDS: list[tuple[str, str]] = [
    ("w_opt.gjf", "水 opt（三段链首段/通用快样）"),
    ("w_freq.gjf", "水 freq（三段链中段，脚本接线 %OldChk）"),
    ("w_sp.gjf", "水 sp（三段链尾段，脚本接线 %OldChk）"),
    ("w_opt2.gjf", "水 opt（续用形态源）"),
    ("w_opt3.gjf", "水 opt（续用形态宿，脚本接线 %Chk）"),
    ("naph_deep_opt.gjf", "拉伸萘深优（约 5 分钟：停等窗口/强停续跑目标）"),
    ("naph_td.gjf", "萘 TD 单点（续跑目标：Guess=Read 注入分支）"),
    ("bz_freq_slow.gjf", "苯 freq（续跑目标：回落原样重跑分支）"),
    ("etoh.gjf", "乙醇（组合流：crest 成队 ~4 构象 → top-N 精修）"),
    ("meoh.gjf", "甲醇（组合流：单构象 <2 失败分支）"),
    ("w_opt_bad.gjf", "伪关键字 opt（失败联动/program_error 注入）"),
    ("cyc_a.gjf", "依赖校验：环对 a（脚本接线互指）"),
    ("cyc_b.gjf", "依赖校验：环对 b"),
    ("dang.gjf", "依赖校验：悬引用（@task:99999）"),
    ("fwd_a.gjf", "依赖校验：前向引用对（被引用方）"),
    ("fwd_b.gjf", "依赖校验：前向引用对（脚本接线指 fwd_a）"),
]

# 引用接线：(宿主文件名, 文法行, 前置行)——{stem} 经 format 回填为对应
# 候选 id（stem=去扩展名文件名）；前置行保持 Link0 合法形状。
WIRING: list[tuple[str, list[str], list[str]]] = [
    ("w_freq.gjf", "%OldChk=@task:{w_opt}", ["%chk=input.chk", "%nprocshared=2"]),
    ("w_sp.gjf", "%OldChk=@task:{w_freq}", ["%chk=input.chk", "%nprocshared=2"]),
    ("w_opt3.gjf", "%Chk=@task:{w_opt2}", ["%nprocshared=2"]),
    ("cyc_a.gjf", "%OldChk=@task:{cyc_b}", ["%chk=input.chk", "%nprocshared=2"]),
    ("cyc_b.gjf", "%OldChk=@task:{cyc_a}", ["%chk=input.chk", "%nprocshared=2"]),
    ("dang.gjf", "%OldChk=@task:99999", ["%chk=input.chk", "%nprocshared=2"]),
    ("fwd_b.gjf", "%OldChk=@task:{fwd_a}", ["%chk=input.chk", "%nprocshared=2"]),
]


def _get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _request(base: str, path: str, payload: bytes | None, *,
             content_type: str, method: str) -> tuple[int, dict | bytes]:
    req = urllib.request.Request(base + path, data=payload, method=method,
                                 headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            return resp.status, json.loads(body.decode("utf-8")) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body.decode("utf-8"))
        except ValueError:
            return exc.code, body


def _multipart(files: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = "seed-g16web-boundary"
    parts: list[bytes] = [b"--" + boundary.encode() + b"\r\n"
                          b'Content-Disposition: form-data; name="mode"\r\n'
                          b"\r\nfiles\r\n"]
    for name, data in files:
        parts.append(
            b"--" + boundary.encode()
            + f"\r\nContent-Disposition: form-data; name=\"files\"; "
              f"filename=\"{name}\"\r\nContent-Type: chemical/x-gaussian-input"
              f"\r\n\r\n".encode("utf-8") + data + b"\r\n")
    parts.append(b"--" + boundary.encode() + b"--\r\n")
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8398")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    status, health = _request(base, "/api/v1/system/health", None,
                              content_type="application/json", method="GET")
    if status != 200:
        print(f"实例不可达：{base}（HTTP {status}）——先按 development.md §6.2 拉起",
              file=sys.stderr)
        return 1
    print(f"实例 {base} OK（{health.get('version')}）")

    def candidate_map() -> dict[str, int]:
        items: list[dict] = []
        page = 1
        while True:
            data = _get(base, f"/api/v1/candidates?page={page}&page_size=100")
            items.extend(data.get("items") or [])
            if page * 100 >= int(data.get("total") or 0):
                break
            page += 1
        return {c["filename"]: c["id"] for c in items}

    names = {name for name, _ in SEEDS}
    existing = {n: tid for n, tid in candidate_map().items() if n in names}

    todo = [(n, (SAMPLES_DIR / n).read_bytes()) for n, _ in SEEDS
            if n not in existing]
    if todo:
        body, ctype = _multipart(todo)
        status, resp = _request(base, "/api/v1/candidates", body,
                                content_type=ctype, method="POST")
        if status != 201:
            print(f"导入失败（HTTP {status}）：{resp}", file=sys.stderr)
            return 1
        print(f"导入候选 {len(todo)} 个")
    else:
        print("种子候选已齐，跳过导入（幂等）")

    by_name = {c["filename"]: c["id"] for c in _all_candidates(base)
               if c["filename"] in names}
    by_stem = {Path(n).stem: tid for n, tid in by_name.items()}
    purpose = dict(SEEDS)

    wired = skipped = 0
    for host, ref_line, prefix in WIRING:
        tid = by_name.get(host)
        if tid is None:
            print(f"  接线跳过：{host} 不在候选列表（可能已入队）")
            continue
        line = ref_line.format(**by_stem)
        status, resp = _request(
            base, f"/api/v1/candidates/{tid}/blocks/link0",
            json.dumps({"lines": prefix + [line]}).encode("utf-8"),
            content_type="application/json", method="PUT")
        if status == 200:
            wired += 1
        else:
            skipped += 1
            print(f"  接线跳过：{host}（#{tid:03d}）HTTP {status}"
                  f"——已入队成员不可编辑，属正常")
    print(f"引用接线完成 {wired} 条，跳过 {skipped} 条")

    print("\n种子清单（id 文件名 — 用途）：")
    for tid in sorted(by_name.values()):
        name = next(n for n, i in by_name.items() if i == tid)
        print(f"  #{tid:03d}  {name:<20} — {purpose.get(name, '')}")
    print("\n提示：三段链/续用对可直接在候选页勾选「+ 队列」体验依赖派发；"
          "乙醇候选行「组合流」一键全链；拉伸萘约 5 分钟适合强停后续跑。")
    return 0


def _all_candidates(base: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        data = _get(base, f"/api/v1/candidates?page={page}&page_size=100")
        items.extend(data.get("items") or [])
        if page * 100 >= int(data.get("total") or 0):
            break
        page += 1
    return items


if __name__ == "__main__":
    sys.exit(main())
