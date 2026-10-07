# shot-deps 🎬

A tiny, offline preflight for animation and AI-video shot dependencies. Find missing or changed assets, blocked shots, and the downstream impact of a reference change before spending another render credit.

**Python 3.10+ · standard library only · no install · no network · read-only**

[中文说明](README.zh-CN.md)

## Run in 30 seconds

Download this repository (Code → Download ZIP), extract it, and open a terminal in its folder:

```sh
python shot_deps.py examples/project.json --changed hero
python -m unittest discover -s tests -v
```

Or clone it:

```sh
git clone https://github.com/BohaoWorks/shot-deps.git
cd shot-deps
python shot_deps.py examples/project.json --changed hero --json
```

On systems where `python` is not available, use `python3` (macOS/Linux) or `py` (Windows).

The included text assets are synthetic stand-ins, not production media. The good demo prints:

```text
PASS
Asset hero: ok
Asset street: ok
Layer 1: S010
Layer 2: S020
Layer 3: S030
Impacted: S010, S020, S030
Unused assets: none
```

Try the intentionally broken demo:

```sh
python shot_deps.py examples/broken.json --json
```

It exits **1**: `voice` is missing, `S010` is blocked, and `S020` is blocked by `S010`. This failure is expected.

## Your project manifest

Create a UTF-8 JSON file next to your asset folder:

```json
{
  "version": 1,
  "assets": {
    "hero": {"path": "assets/hero.png"},
    "voice": {"path": "audio/line.wav"}
  },
  "shots": {
    "S010": {"assets": ["hero", "voice"], "needs": []},
    "S020": {"assets": ["hero"], "needs": ["S010"]}
  }
}
```

`needs` means an upstream shot must be processed before this shot. Layers show dependency order, **not completion state**: the tool does not know which shots have rendered or been approved. Shots in the same layer have no dependency on each other. An upstream block propagates to all dependents. Unknown IDs, missing files, hash mismatches, and cycles block affected shots. Independent healthy shots still receive runnable layers.

Assets resolve relative to the manifest's directory, even if the command runs elsewhere. Use `--root /path/to/project` to select another local asset root. Use portable `/` paths; absolute paths, Windows drives, backslashes and `..` are rejected. Symlinks resolving outside the root are reported and not read. Do not run this as a sandbox against hostile, concurrently modified filesystems.

Optional `sha256` pins an asset's approved bytes. A mismatch reports `changed` and its downstream impact. Generate a digest locally, then deliberately paste it into the manifest after reviewing the asset:

```sh
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('assets/hero.png').read_bytes()).hexdigest())"
```

The checker streams hashes in 1 MiB chunks; the convenience command above loads the asset in memory. With no digest, only file existence is checked. `--changed hero --changed voice` previews impact without editing files or blocking otherwise healthy shots. Unknown changed IDs are errors to catch typos.

## Output contract

- `--json`: stable field names; sorted IDs and deterministic layer ordering
- `asset_status`: `ok`, `missing`, `changed`, `outside_root`, or `unreadable`
- `blocked`: shot IDs and concrete reason strings
- `runnable_layers`: healthy dependency layers
- `cycle_or_downstream`: includes cycle members **and their downstream dependents**, not an exact cycle trace
- `impacted_shots`: transitive consumers of manually changed or hash-mismatched assets
- `unused_assets`: manifest assets not referenced by any shot

Exit codes: **0** clean, **1** asset/dependency problems, **2** invalid manifest or input. A missing unused asset also returns 1; it remains a declared project requirement. JSON input rejects duplicate keys, unknown fields and duplicate references. Empty projects are valid. Reports may include your local paths/IDs: review them before sharing. No files are uploaded or modified.

## Limits

This is a manifest checker, not a renderer, media decoder, timeline parser, visual-continuity judge, or task-management database. It cannot discover references hidden inside Blender, Premiere, Resolve or prompts. Add those references explicitly. Hashes detect byte changes, not meaningful visual differences. No automatic hash updates or asset deletion. No third-party runtime dependencies.

## Development

```sh
python -m unittest discover -s tests -v
```

22 tests cover hashes, missing/unknown references, cyclic and long dependency chains, symlink boundaries, schema validation, malformed JSON, and real CLI exit codes. CI runs on Linux, Windows and macOS with Python 3.10 and 3.13. A platform without symlink-creation permission skips that single symlink test.

MIT licensed. Built for small creator teams and local Codex workflows.
