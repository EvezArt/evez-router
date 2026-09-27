#!/usr/bin/env python3
"""EVEZ ROUTER PROBE — check mesh router health and route one task.
Reads evez-router config, probes all providers, reports fastest free model."""
import json, urllib.request, time, os

ROUTER_DIR = os.path.expanduser("~/.openclaw/workspace/skills/evez-router")

def probe_provider(name, url):
    try:
        start = time.time()
        req = urllib.request.urlopen(url, timeout=5)
        elapsed = (time.time() - start) * 1000
        return {"name": name, "up": True, "latency_ms": round(elapsed, 1)}
    except Exception as e:
        return {"name": name, "up": False, "latency_ms": 999, "error": str(e)[:60]}

def main():
    # Load router config
    config = os.path.join(ROUTER_DIR, "config.json")
    if not os.path.exists(config):
        print("No router config found — run evez-router setup first")
        return
    
    d = json.load(open(config))
    providers = d.get("providers", {})
    
    results = []
    for name, cfg in providers.items():
        url = cfg.get("health_url", cfg.get("url", ""))
        if url:
            results.append(probe_provider(name, url))
    
    # Also probe local gateway
    results.append(probe_provider("local_gateway", "http://localhost:18789/healthz"))
    
    # Sort by latency
    results.sort(key=lambda x: x.get("latency_ms", 999))
    
    fastest = results[0] if results else None
    print(f"Router probe: {len(results)} providers checked")
    for r in results:
        status = "✅" if r["up"] else "❌"
        print(f"  {status} {r['name']}: {r.get('latency_ms','?')}ms")
    
    if fastest and fastest["up"]:
        print(f"\nFastest: {fastest['name']} ({fastest['latency_ms']}ms)")
    
    # Save probe result
    probe_file = os.path.join(ROUTER_DIR, "probe_result.json")
    with open(probe_file, 'w') as f:
        json.dump({"timestamp": time.time(), "results": results, "fastest": fastest}, f, indent=2)
    
    return fastest

if __name__ == "__main__":
    main()
