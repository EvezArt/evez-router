#!/usr/bin/env python3
"""EVEZ-OS Mesh Router — free-tier model routing with health scoring.
Zero dependencies. Reads keys from openclaw.json env.vars; never stores secrets.
Usage: mesh_router.py probe | status | route --task <chat|code|fast> --message "..."
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
HEALTH_PATH = os.path.join(HERE, "health.json")
CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")
HEALTH_TTL = 300  # seconds

LADDERS = {
    "chat": ["openrouter:nvidia/nemotron-3.5-lightning:free",
             "openrouter:google/gemma-4-26b-a4b-it:free",
             "openrouter:inclusionai/ling-3.0-flash:free",
             "ollama:deepseek-r1:1.5b"],
    "code": ["openrouter:qwen/qwen-3-coder:free",
             "openrouter:nvidia/nemotron-3.5-lightning:free",
             "openrouter:google/gemma-4-26b-a4b-it:free",
             "ollama:deepseek-r1:1.5b"],
    "fast": ["openrouter:nvidia/nemotron-3.5-lightning:free",
             "openrouter:inclusionai/ling-3.0-flash:free",
             "ollama:qwen-3.2:1b"],
}
TASK_ALIASES = {"default": "chat", "general": "chat", "writing": "chat",
                "python": "code", "coding": "code", "dev": "code", "quick": "fast"}


def load_env_keys():
    keys = {}
    try:
        cfg = json.load(open(CONFIG))
        v = (cfg.get("env") or {}).get("vars") or {}
        for name, val in v.items():
            if name.startswith("OPENROUTER_API_KEY") and val:
                keys.setdefault("openrouter", []).append(val)
            if name.startswith("CEREBRAS_API_KEY") and val:
                keys.setdefault("cerebras", []).append(val)
    except Exception:
        pass
    keys.setdefault("openrouter", [])
    keys.setdefault("cerebras", [])
    return keys


def load_health():
    try:
        h = json.load(open(HEALTH_PATH))
        if time.time() - h.get("ts", 0) < HEALTH_TTL * 6:
            return h
    except Exception:
        pass
    return {"ts": 0, "nodes": {}}


def save_health(h):
    h["ts"] = time.time()
    json.dump(h, open(HEALTH_PATH, "w"), indent=1)


def chat(node, key, model, message, max_tokens=400, timeout=60):
    if node == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": message}], "max_tokens": max_tokens}
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
                   "User-Agent": "EvezRouter/1.0"}
    elif node == "cerebras":
        url = "https://api.cerebras.ai/v1/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": message}], "max_tokens": max_tokens}
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    else:  # ollama
        url = "http://127.0.0.1:11434/api/chat"
        payload = {"model": model, "messages": [{"role": "user", "content": message}], "stream": False}
        headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            text = body["choices"][0]["message"]["content"] if "choices" in body else body.get("message", {}).get("content", "")
            return {"ok": True, "node": node, "model": model, "latency": round(time.time() - t0, 2), "text": text}
    except urllib.error.HTTPError as e:
        return {"ok": False, "node": node, "model": model, "error": "HTTP %d" % e.code, "retryable": e.code in (408, 429, 500, 502, 503, 524)}
    except Exception as e:
        return {"ok": False, "node": node, "model": model, "error": str(e)[:80], "retryable": True}


def probe():
    keys = load_env_keys()
    health = {"ts": time.time(), "nodes": {}}
    for key in keys["openrouter"][:4]:
        r = chat("openrouter", key, "nvidia/nemotron-3.5-lightning:free", "ping", max_tokens=4, timeout=30)
        ident = "openrouter:" + key[-6:]
        health["nodes"][ident] = {"ok": r["ok"], "latency": r.get("latency", 0), "error": r.get("error", "")}
    for key in keys["cerebras"][:2]:
        r = chat("cerebras", key, "llama3.1-8b", "ping", max_tokens=4, timeout=30)
        ident = "cerebras:" + key[-6:]
        health["nodes"][ident] = {"ok": r["ok"], "latency": r.get("latency", 0), "error": r.get("error", "")}
    r = chat("ollama", "", "deepseek-r1:1.5b", "ping", max_tokens=4, timeout=25)
    health["nodes"]["ollama:local"] = {"ok": r["ok"], "latency": r.get("latency", 0), "error": r.get("error", "")}
    save_health(health)
    return health


def alive_nodes(health, node_kind):
    return [n for n, s in health["nodes"].items() if s["ok"] and n.startswith(node_kind)]


def route(task, message, max_tokens):
    keys = load_env_keys()
    health = load_health()
    if not health["nodes"] or time.time() - health["ts"] > HEALTH_TTL:
        health = probe()
    ladder = LADDERS.get(TASK_ALIASES.get(task, task), LADDERS["chat"])
    attempts = []
    for entry in ladder:
        node_kind, model = entry.split(":", 1)
        keylist = keys.get(node_kind if node_kind != "ollama" else "", [""]) if node_kind != "ollama" else [""]
        for key in keylist:
            r = chat(node_kind, key, model, message, max_tokens=max_tokens)
            attempts.append({k: r[k] for k in ("node", "model", "ok", "latency", "error") if k in r})
            if r["ok"]:
                r["attempts"] = attempts
                return r
    return {"ok": False, "error": "all ladder entries exhausted", "attempts": attempts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["probe", "status", "route"])
    p.add_argument("--task", default="chat")
    p.add_argument("--message", default="")
    p.add_argument("--max-tokens", type=int, default=400)
    a = p.parse_args()
    if a.cmd == "probe":
        h = probe()
        for n, s in sorted(h["nodes"].items()):
            print("%-24s %-4s %5ss %s" % (n, "UP" if s["ok"] else "DOWN", s["latency"], s["error"]))
    elif a.cmd == "status":
        h = load_health()
        if not h["nodes"]:
            print("no health data — run probe first")
            return
        age = int(time.time() - h["ts"])
        print("health age: %ss" % age)
        for n, s in sorted(h["nodes"].items()):
            print("%-24s %-4s %5ss" % (n, "UP" if s["ok"] else "DOWN", s["latency"]))
    else:
        r = route(a.task, a.message, a.max_tokens)
        if r["ok"]:
            print(json.dumps({"routed_via": r["node"] + "/" + r["model"], "latency": r["latency"]}))
            print(r["text"])
        else:
            print(json.dumps(r, indent=1))
            sys.exit(1)


if __name__ == "__main__":
    main()
