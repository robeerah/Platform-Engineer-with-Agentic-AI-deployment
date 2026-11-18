#!/usr/bin/env python3
"""platformctl — the self-service CLI for the platform lab.

Developers (and CI) run this instead of writing Nomad HCL or calling the
APISIX Admin API by hand.

  platformctl.py validate <service_dir>
  platformctl.py render   <service_dir> --image IMAGE [--out FILE]
  platformctl.py deploy   <service_dir> --image IMAGE
  platformctl.py expose   <service_dir>
  platformctl.py status   <service_dir>
  platformctl.py onboard  <team>

Environment variables (defaults suit the local lab):
  NOMAD_ADDR        http://127.0.0.1:4646
  CONSUL_HTTP_ADDR  http://127.0.0.1:8500
  APISIX_ADMIN_URL  http://127.0.0.1:9180
  APISIX_ADMIN_KEY  platform-lab-admin-key
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: sudo apt install python3-yaml  (or pip install pyyaml)")

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
TEMPLATE = ROOT / "templates" / "service.nomad.hcl.tpl"
TEAMS_FILE = ROOT / "teams.yaml"
BUILD_DIR = REPO / "build"

CONSUL = os.getenv("CONSUL_HTTP_ADDR", "http://127.0.0.1:8500")
APISIX = os.getenv("APISIX_ADMIN_URL", "http://127.0.0.1:9180")
APISIX_KEY = os.getenv("APISIX_ADMIN_KEY", "platform-lab-admin-key")

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class PlatformError(Exception):
    pass


# ---------------------------------------------------------------- helpers
def info(msg):
    print(f"\033[36m[platformctl]\033[0m {msg}")


def ok(msg):
    print(f"\033[32m  ✔\033[0m {msg}")


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_service(service_dir):
    path = Path(service_dir) / "platform.yaml"
    if not path.exists():
        raise PlatformError(f"{path} not found — every service needs a platform.yaml")
    return load_yaml(path)


def http(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as err:
        return err.code, {"error": err.read().decode()}
    except urllib.error.URLError as err:
        raise PlatformError(f"cannot reach {url}: {err.reason}") from err


def run(cmd):
    info("$ " + " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise PlatformError(f"command failed ({result.returncode}): {' '.join(cmd)}")


# ---------------------------------------------------------------- validate
def validate(spec):
    """Guardrails: the platform team's rules, enforced before anything ships."""
    cfg = load_yaml(TEAMS_FILE)
    limits = cfg["platform"]["limits"]
    suffix = cfg["platform"]["domain_suffix"]
    errors = []

    for key in ("service", "team", "port", "health_path", "replicas", "resources"):
        if key not in spec:
            errors.append(f"missing required field '{key}'")
    if errors:
        raise PlatformError("; ".join(errors))

    if not NAME_RE.match(str(spec["service"])):
        errors.append("service must be lowercase letters, digits and dashes (2-41 chars)")
    if spec["team"] not in cfg["teams"]:
        errors.append(f"unknown team '{spec['team']}' — onboard it in platform/teams.yaml")
    if not isinstance(spec["port"], int) or not 1024 <= spec["port"] <= 65535:
        errors.append("port must be an integer between 1024 and 65535")
    if not 1 <= int(spec["replicas"]) <= limits["max_replicas"]:
        errors.append(f"replicas must be 1..{limits['max_replicas']}")

    res = spec["resources"] or {}
    if int(res.get("cpu", 0)) > limits["max_cpu"]:
        errors.append(f"cpu {res.get('cpu')} exceeds cap {limits['max_cpu']} MHz (ask the platform team)")
    if int(res.get("memory", 0)) > limits["max_memory"]:
        errors.append(f"memory {res.get('memory')} exceeds cap {limits['max_memory']} MB (ask the platform team)")
    if int(res.get("cpu", 0)) <= 0 or int(res.get("memory", 0)) <= 0:
        errors.append("resources.cpu and resources.memory must be positive")

    for key in (spec.get("env") or {}):
        if not ENV_KEY_RE.match(key):
            errors.append(f"env var '{key}' must be UPPER_SNAKE_CASE")

    expose = spec.get("expose")
    if expose:
        host = str(expose.get("host", ""))
        if not host.endswith("." + suffix):
            errors.append(f"expose.host must end with .{suffix}")
        rl = expose.get("rate_limit") or {}
        if int(rl.get("requests", 0)) > limits["max_rate_limit"]:
            errors.append(f"rate_limit.requests exceeds tier cap {limits['max_rate_limit']}")

    if errors:
        raise PlatformError("platform.yaml failed validation:\n  - " + "\n  - ".join(errors))
    return spec


# ---------------------------------------------------------------- render
def render(spec, image):
    env_lines = "\n".join(
        f'        {k} = "{str(v).replace(chr(34), chr(92) + chr(34))}"'
        for k, v in sorted((spec.get("env") or {}).items())
    )
    values = {
        "service": spec["service"],
        "team": spec["team"],
        "image": image,
        "port": spec["port"],
        "replicas": spec["replicas"],
        "cpu": spec["resources"]["cpu"],
        "memory": spec["resources"]["memory"],
        "health_path": spec.get("health_path", "/healthz"),
        "metrics_path": spec.get("metrics_path", "/metrics"),
        "env_lines": env_lines,
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    leftover = re.findall(r"\{\{\w+\}\}", text)
    if leftover:
        raise PlatformError(f"template has unfilled placeholders: {leftover}")
    return text


def write_job(spec, image, out=None):
    BUILD_DIR.mkdir(exist_ok=True)
    path = Path(out) if out else BUILD_DIR / f"{spec['service']}.nomad.hcl"
    path.write_text(render(spec, image), encoding="utf-8")
    ok(f"rendered Nomad job → {path.relative_to(REPO) if path.is_relative_to(REPO) else path}")
    return path


# ---------------------------------------------------------------- nomad
def ensure_namespace(team):
    cfg = load_yaml(TEAMS_FILE)
    desc = cfg["teams"].get(team, {}).get("description", team)
    run(["nomad", "namespace", "apply", "-description", desc, team])
    ok(f"namespace '{team}' ready")


def deploy(spec, image):
    job = write_job(spec, image)
    ensure_namespace(spec["team"])
    run(["nomad", "job", "validate", str(job)])
    # `nomad job run` follows the deployment and exits non-zero if it fails.
    run(["nomad", "job", "run", str(job)])
    ok(f"{spec['service']} deployed to namespace '{spec['team']}' with image {image}")


# ---------------------------------------------------------------- apisix
def admin(method, path, body=None):
    return http(method, f"{APISIX}/apisix/admin{path}", body, {"X-API-KEY": APISIX_KEY})


def expose(spec):
    exp = spec.get("expose")
    if not exp:
        raise PlatformError("no 'expose' block in platform.yaml — nothing to expose")
    svc, host = spec["service"], exp["host"]

    # Guardrail: a hostname belongs to exactly one service.
    status, existing = admin("GET", "/routes")
    if status == 200:
        for item in existing.get("list") or []:
            route = item.get("value", {})
            if route.get("host") == host and route.get("id") != svc:
                raise PlatformError(
                    f"host {host} is already used by route '{route.get('id')}' "
                    f"(team {route.get('labels', {}).get('team')})"
                )

    rl = exp.get("rate_limit") or {"requests": 100, "per_seconds": 60}
    route = {
        "name": svc,
        "desc": f"managed by platformctl for team {spec['team']}",
        "host": host,
        "uri": "/*",
        "labels": {"team": spec["team"], "managed_by": "platformctl"},
        "upstream": {
            "type": "roundrobin",
            "discovery_type": "consul",
            "service_name": svc,
        },
        "plugins": {
            "limit-count": {
                "count": int(rl["requests"]),
                "time_window": int(rl["per_seconds"]),
                "key_type": "var",
                "key": "remote_addr",
                "rejected_code": 429,
                "policy": "local",
            },
            "prometheus": {"prefer_name": True},
            "request-id": {"include_in_response": True},
        },
    }
    status, body = admin("PUT", f"/routes/{svc}", route)
    if status not in (200, 201):
        raise PlatformError(f"APISIX rejected the route ({status}): {body}")
    ok(f"route '{svc}' live: http://{host}:9080  (rate limit {rl['requests']}/{rl['per_seconds']}s per IP)")


# ---------------------------------------------------------------- status
def status(spec):
    svc, team = spec["service"], spec["team"]
    info(f"Nomad job '{svc}' (namespace {team})")
    subprocess.run(["nomad", "job", "status", "-namespace", team, svc])

    code, checks = http("GET", f"{CONSUL}/v1/health/service/{svc}")
    if code == 200:
        passing = sum(
            all(c["Status"] == "passing" for c in entry["Checks"]) for entry in checks
        )
        info(f"Consul: {passing}/{len(checks)} instances passing health checks")
        for entry in checks:
            s = entry["Service"]
            print(f"    {s['Address']}:{s['Port']}  tags={s['Tags']}")

    code, route = admin("GET", f"/routes/{svc}")
    if code == 200:
        host = route.get("value", {}).get("host")
        info(f"APISIX: route present → http://{host}:9080")
    else:
        info("APISIX: no route yet (run: platformctl.py expose <service_dir>)")


# ---------------------------------------------------------------- main
def main(argv=None):
    parser = argparse.ArgumentParser(prog="platformctl", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "expose", "status"):
        sub.add_parser(name).add_argument("service_dir")
    for name in ("render", "deploy"):
        p = sub.add_parser(name)
        p.add_argument("service_dir")
        p.add_argument("--image", required=True)
        if name == "render":
            p.add_argument("--out")
    sub.add_parser("onboard").add_argument("team")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "onboard":
            if args.team not in load_yaml(TEAMS_FILE)["teams"]:
                raise PlatformError(f"add '{args.team}' to platform/teams.yaml first (reviewed by the platform team)")
            ensure_namespace(args.team)
            return 0

        spec = validate(load_service(args.service_dir))
        if args.cmd == "validate":
            ok(f"{spec['service']} (team {spec['team']}) passes all platform guardrails")
        elif args.cmd == "render":
            write_job(spec, args.image, args.out)
        elif args.cmd == "deploy":
            deploy(spec, args.image)
        elif args.cmd == "expose":
            expose(spec)
        elif args.cmd == "status":
            status(spec)
        return 0
    except PlatformError as err:
        print(f"\033[31m[platformctl] {err}\033[0m", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
