"""G16 Web 控制台后端：纯标准库 HTTP 服务，JSON API + 静态页面。

启动: python3 server.py [--port 8160] [--host 127.0.0.1]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaussian  # noqa: E402
import hq  # noqa: E402
import inputfile  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
UPLOAD_DIR = os.path.expanduser("~/scratch/uploads")
STARTED = time.time()


def _iso_to_epoch(ts: str):
    """把 hq 的 '2026-09-21T14:58:05.876153780Z' 转成 epoch 秒。"""
    if not ts:
        return None
    m = re.match(r"(.+?)\.(\d+)(Z|[+-]\d{2}:\d{2})?$", ts)
    if not m:
        return None
    base, frac, zone = m.groups()
    import calendar
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(base)
    epoch = calendar.timegm(dt.timetuple())
    if zone and zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        hh, mm = int(zone[1:3]), int(zone[4:6])
        epoch -= sign * (hh * 3600 + mm * 60)
    return epoch + float("0." + frac)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------- 基础 ----------
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _fail(self, msg, code=400):
        self._json({"error": msg}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n))

    def _static(self, name="index.html"):
        path = os.path.normpath(os.path.join(STATIC_DIR, name))
        if not path.startswith(STATIC_DIR) or not os.path.isfile(path):
            return self._fail("not found", 404)
        with open(path, "rb") as f:
            data = f.read()
        ctype = "text/html; charset=utf-8"
        if name.endswith((".js",)):
            ctype = "text/javascript; charset=utf-8"
        elif name.endswith((".css",)):
            ctype = "text/css; charset=utf-8"
        self._send(200, data, ctype)

    # ---------- 业务 ----------
    def _job_view(self, j: dict, with_progress=True) -> dict:
        ts = j.get("task_stats", {})
        view = {"id": j["id"], "name": j.get("name") or f"job-{j['id']}",
                "state": hq.job_state(j), "task_count": j.get("task_count"),
                "stats": ts}
        if with_progress:
            view["progress"] = self._progress_for(view["id"], view["state"])
        return view

    def _progress_for(self, job_id: int, state: str) -> dict:
        try:
            info = hq.job_info(job_id)
        except Exception:
            return {}
        paths = hq.job_paths(info)
        prog = gaussian.parse_file(paths["log"]) if paths.get("log") else {"missing": True}
        started = _iso_to_epoch(info.get("started_at"))
        finished = _iso_to_epoch(info.get("finished_at"))
        if started:
            end = finished if finished else time.time()
            prog["elapsed"] = round(end - started)
        prog["summary"] = gaussian.progress_summary(prog)
        prog["log"] = paths.get("log")
        prog["cwd"] = paths.get("cwd")
        prog["input"] = paths.get("input")
        prog["state"] = state
        return prog

    # ---------- 路由 ----------
    def do_GET(self):
        try:
            self._route_get()
        except hq.HqError as e:
            self._fail(str(e), 502)
        except Exception as e:  # noqa: BLE001
            self._fail(f"内部错误: {e}", 500)

    def do_POST(self):
        try:
            self._route_post()
        except hq.HqError as e:
            self._fail(str(e), 502)
        except (ValueError, KeyError) as e:
            self._fail(f"请求无效: {e}")
        except Exception as e:  # noqa: BLE001
            self._fail(f"内部错误: {e}", 500)

    def _route_get(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])

        if path == "/api/status":
            return self._json({**hq.status(), "uptime": round(time.time() - STARTED)})

        if path == "/api/jobs":
            jobs = [self._job_view(j) for j in hq.job_list()]
            jobs.sort(key=lambda x: (-x["id"]))
            return self._json(jobs)

        m = re.match(r"^/api/job/(\d+)$", path)
        if m:
            jid = int(m.group(1))
            info = hq.job_info(jid)
            state = hq.job_state(info.get("info", {}))
            return self._json(self._progress_for(jid, state))

        m = re.match(r"^/api/job/(\d+)/log$", path)
        if m:
            from urllib.parse import parse_qs
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            lines = int(qs.get("lines", ["120"])[0])
            info = hq.job_info(int(m.group(1)))
            log = hq.job_paths(info).get("log")
            if not log or not os.path.isfile(log):
                return self._json({"path": log, "text": None})
            with open(log, encoding="utf-8", errors="replace") as f:
                text = "".join(f.readlines()[-lines:])
            return self._json({"path": log, "text": text})

        if path == "/api/files":
            from urllib.parse import parse_qs, unquote
            qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            target = unquote(qs.get("path", [os.path.expanduser("~")])[0])
            target = os.path.abspath(target)
            if not os.path.isdir(target):
                return self._fail(f"目录不存在: {target}", 404)
            entries = []
            try:
                for name in sorted(os.listdir(target), key=str.lower):
                    if name.startswith("."):
                        continue
                    full = os.path.join(target, name)
                    entries.append({"name": name, "dir": os.path.isdir(full),
                                    "size": os.path.getsize(full)
                                    if os.path.isfile(full) else None})
            except PermissionError:
                return self._fail("没有权限读取该目录", 403)
            dirs = [e for e in entries if e["dir"]]
            files = [e for e in entries if not e["dir"]]
            files.sort(key=lambda e: (not e["name"].endswith((".gjf", ".com", ".in")), e["name"]))
            parent = os.path.dirname(target)
            return self._json({"path": target, "parent": parent if parent != target else None,
                               "entries": dirs + files})

        self._fail("not found", 404)

    def _route_post(self):
        path = self.path.split("?", 1)[0]
        body = self._body()

        if path == "/api/preview":
            text, src = self._load_input(body)
            parsed = inputfile.parse_input(text)
            parsed["source"] = src
            parsed["text"] = text
            return self._json(parsed)

        if path == "/api/submit":
            slots = int(body.get("slots") or 2)
            text, src = self._load_input(body)
            parsed = inputfile.parse_input(text)
            if not parsed["valid"]:
                return self._fail("输入文件无效，请先检查预览中的警告", 422)
            if src == "content":
                if not body.get("filename"):
                    return self._fail("粘贴内容需要提供文件名")
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                name = body["filename"]
                target = os.path.join(UPLOAD_DIR, name)
                i = 2
                while os.path.exists(target):
                    stem, ext = os.path.splitext(name)
                    target = os.path.join(UPLOAD_DIR, f"{stem}-{i}{ext}")
                    i += 1
                with open(target, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text.replace("\r\n", "\n"))
                src = target
            cwd = os.path.dirname(os.path.abspath(src))
            input_name = os.path.basename(src)
            stem = os.path.splitext(input_name)[0]
            if not hq.ensure_server():
                return self._fail("hq server 启动失败，查看 ~/.hq-server.log", 502)
            if not hq.ensure_worker(slots):
                return self._fail("hq worker 启动失败，查看 ~/.hq-worker.log", 502)
            job_id = hq.submit(cwd, input_name, stem)
            return self._json({"job_id": job_id, "name": stem, "cwd": cwd,
                               "log": os.path.join(cwd, stem + ".log")})

        m = re.match(r"^/api/job/(\d+)/cancel$", path)
        if m:
            hq.cancel_job(int(m.group(1)))
            return self._json({"canceled": True})

        self._fail("not found", 404)

    def _load_input(self, body) -> tuple:
        """body 里 path 或 (content + filename) 二选一，返回 (text, src)。"""
        if body.get("path"):
            p = os.path.abspath(os.path.expanduser(body["path"]))
            if not os.path.isfile(p):
                raise ValueError(f"文件不存在: {p}")
            with open(p, encoding="utf-8", errors="replace") as f:
                return f.read(), p
        if "content" in body:
            return body["content"], "content"
        raise ValueError("需要 path 或 content 参数")


def main():
    ap = argparse.ArgumentParser(description="G16 Web 控制台")
    ap.add_argument("--port", type=int, default=8160)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"G16 Web 控制台: http://{args.host}:{args.port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
