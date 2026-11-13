#!/usr/bin/env python3
"""Record a host build on main; the updater also requires successful CI gates."""
import json
import os
from pathlib import Path
import subprocess
import sys

assert os.environ["GITHUB_EVENT_NAME"] == "push"
assert os.environ["GITHUB_REF"] == "refs/heads/main"
sha = os.environ["GITHUB_SHA"]
host = sys.argv[1] if len(sys.argv) > 1 else "ahimsa"
if host not in {"ahimsa", "ahimsa-vps"}:
    raise SystemExit("Unsupported CI host.")
flake = f"git+{Path(os.environ['GITHUB_WORKSPACE']).as_uri()}?rev={sha}"

def output(attribute):
    return subprocess.check_output([
        "nix", "eval", "--raw", "--no-update-lock-file", "--no-write-lock-file",
        f"{flake}#{attribute}",
    ], text=True).strip()

manifest = {
    "schema": 1,
    "repository": os.environ["GITHUB_REPOSITORY"],
    "sha": sha,
    "host": host,
    "system": "x86_64-linux",
    "user": "brenoslivio" if host == "ahimsa" else "root",
    "event": "push",
    "run_id": os.environ["GITHUB_RUN_ID"],
    "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
    "system_path": output(f"nixosConfigurations.{host}.config.system.build.toplevel.outPath"),
}
if host == "ahimsa":
    manifest["home_path"] = output("homeConfigurations.brenoslivio.activationPackage.outPath")
Path("manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
    stream.write(f"Tested `{sha}` for `{host}`.\n\n```json\n{json.dumps(manifest, indent=2)}\n```\n")
