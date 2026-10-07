#!/usr/bin/env python3
"""Offline, read-only asset and shot dependency preflight (Python 3.10+)."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys


class ManifestError(ValueError):
    """Invalid or ambiguous project manifest."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_manifest(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"),
                          object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(str(exc)) from exc


def validate(data):
    if not isinstance(data, dict) or set(data) != {"version", "assets", "shots"}:
        raise ManifestError("root must contain exactly version, assets, shots")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ManifestError("version must be 1")
    assets, shots = data["assets"], data["shots"]
    for label, entries in (("assets", assets), ("shots", shots)):
        if not isinstance(entries, dict):
            raise ManifestError(f"{label} must be an object keyed by ID")
        if any(not isinstance(k, str) or not k.strip() for k in entries):
            raise ManifestError(f"{label} IDs must be nonempty strings")
    for key, asset in assets.items():
        if not isinstance(asset, dict) or not {"path"} <= set(asset) <= {"path", "sha256"}:
            raise ManifestError(f"asset {key}: expected path and optional sha256")
        path = asset["path"]
        if not isinstance(path, str) or not path or "\x00" in path:
            raise ManifestError(f"asset {key}: invalid path")
        if ("\\" in path or PurePosixPath(path).is_absolute()
                or PureWindowsPath(path).drive or ".." in PurePosixPath(path).parts):
            raise ManifestError(f"asset {key}: path must be root-relative POSIX, without ..")
        if "sha256" in asset and (not isinstance(asset["sha256"], str)
                or not re.fullmatch(r"[a-fA-F0-9]{64}", asset["sha256"])):
            raise ManifestError(f"asset {key}: sha256 must be 64 hexadecimal characters")
    for key, shot in shots.items():
        if not isinstance(shot, dict) or set(shot) != {"assets", "needs"}:
            raise ManifestError(f"shot {key}: expected assets and needs")
        for field in ("assets", "needs"):
            values = shot[field]
            if (not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values)
                    or len(values) != len(set(values))):
                raise ManifestError(f"shot {key}: {field} must be a list of distinct IDs")
    return assets, shots


def asset_state(root, asset):
    try:
        target = (root / asset["path"]).resolve()
        if not target.is_relative_to(root):
            return "outside_root"
        if not target.is_file():
            return "missing"
        if "sha256" in asset:
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != asset["sha256"].lower():
                return "changed"
        return "ok"
    except (OSError, RuntimeError, ValueError):
        return "unreadable"


def analyze(data, root, changed=()):
    assets, shots = validate(data)
    root = Path(root).resolve()
    if not root.is_dir():
        raise ManifestError("asset root must be an existing directory")
    unknown = sorted(set(changed) - assets.keys())
    if unknown:
        raise ManifestError("unknown --changed asset IDs: " + ", ".join(unknown))
    states = {key: asset_state(root, assets[key]) for key in sorted(assets)}
    reasons = {key: [] for key in sorted(shots)}
    followers = {key: [] for key in shots}
    indegree = {}
    for key, shot in shots.items():
        for asset in shot["assets"]:
            if asset not in states:
                reasons[key].append(f"unknown_asset:{asset}")
            elif states[asset] != "ok":
                reasons[key].append(f"asset_{states[asset]}:{asset}")
        for dep in shot["needs"]:
            if dep not in shots:
                reasons[key].append(f"unknown_shot:{dep}")
            else:
                followers[dep].append(key)
        indegree[key] = sum(dep in shots for dep in shot["needs"])
    # Iterative topological layers avoid recursion limits on large shot chains.
    frontier = sorted(key for key, count in indegree.items() if count == 0)
    layers = []
    visited = set()
    while frontier:
        layers.append(frontier)
        next_layer = []
        for key in frontier:
            visited.add(key)
            for follower in followers[key]:
                indegree[follower] -= 1
                if indegree[follower] == 0:
                    next_layer.append(follower)
        frontier = sorted(next_layer)
    # Kahn remainder includes cycle members AND anything downstream of a cycle.
    cycle_blocked = sorted(shots.keys() - visited)
    for key in cycle_blocked:
        reasons[key].append("cycle_or_downstream")
    blocked = {key for key, value in reasons.items() if value}
    queue = list(sorted(blocked))
    for key in queue:
        for follower in sorted(followers[key]):
            if follower not in blocked:
                blocked.add(follower)
                queue.append(follower)
    for key in blocked:
        reasons[key].extend(f"blocked_shot:{dep}" for dep in shots[key]["needs"] if dep in blocked)
    changed_set = set(changed) | {key for key, state in states.items() if state == "changed"}
    impacted = {key for key, shot in shots.items() if changed_set.intersection(shot["assets"])}
    queue = list(sorted(impacted))
    for key in queue:
        for follower in followers[key]:
            if follower not in impacted:
                impacted.add(follower)
                queue.append(follower)
    unused = sorted(assets.keys() - {asset for shot in shots.values() for asset in shot["assets"]})
    runnable_layers = [[key for key in layer if key not in blocked] for layer in layers]
    return {
        "ok": not blocked and all(state == "ok" for state in states.values()),
        "asset_status": states,
        "blocked": {key: sorted(set(reasons[key])) for key in sorted(blocked)},
        "runnable_layers": [layer for layer in runnable_layers if layer],
        "cycle_or_downstream": cycle_blocked,
        "impacted_shots": sorted(impacted),
        "unused_assets": unused,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, help="asset root; defaults to manifest's directory")
    parser.add_argument("--changed", action="append", default=[], metavar="ASSET_ID",
                        help="report downstream impact; repeat for multiple asset IDs")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    try:
        result = analyze(read_manifest(args.manifest),
                         args.root if args.root is not None else args.manifest.parent,
                         args.changed)
    except (ManifestError, OSError, RuntimeError, ValueError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"Manifest error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["ok"] else "BLOCKED")
        for key, state in result["asset_status"].items():
            print(f"Asset {key}: {state}")
        for key, reasons in result["blocked"].items():
            print(f"Shot {key}: {', '.join(reasons)}")
        for index, layer in enumerate(result["runnable_layers"], 1):
            print(f"Layer {index}: {', '.join(layer)}")
        print("Impacted: " + (", ".join(result["impacted_shots"]) or "none"))
        print("Unused assets: " + (", ".join(result["unused_assets"]) or "none"))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
