#!/usr/bin/env python3
"""Expose only validated, public cache settings to GitHub Actions."""
import json
import os
from pathlib import Path
import re

cache = json.loads(Path('config/cache.json').read_text())
name, key = cache['name'], cache['publicKey']
if (name is None) != (key is None):
    raise SystemExit('Configure both cache name and public signing key.')
if name is not None and (not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name)
                        or not re.fullmatch(r'[A-Za-z0-9._-]+:[A-Za-z0-9+/]{43}=', key)):
    raise SystemExit('Invalid public cache configuration.')
with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
    stream.write(f'name={name or ""}\nkey={key or ""}\nurl={"https://" + name + ".cachix.org" if name else ""}\n')
