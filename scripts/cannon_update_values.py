#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from io import StringIO

from ruamel.yaml import YAML


SHA_RE = re.compile(r"^sha-([0-9a-f]{12})$")
SEMVER_RE = re.compile(r"^(v[0-9]+\.[0-9]+\.[0-9]+)$")


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def parse_tag(image_tag: str) -> Tuple[str, Optional[str]]:
    """
    Returns (kind, sha12)
      kind: "sha" or "semver"
      sha12: 12-hex string if kind == "sha", else None
    """
    m = SHA_RE.match(image_tag)
    if m:
        return "sha", m.group(1)

    m = SEMVER_RE.match(image_tag)
    if m:
        return "semver", None

    return "invalid", None


def validate(environment: str, image_tag: str) -> Tuple[str, Optional[str]]:
    kind, sha12 = parse_tag(image_tag)
    if environment == "dev":
        if kind not in ("sha", "semver"):
            die("dev allows only sha-<12hex> or vX.Y.Z")
    elif environment in ("staging", "prod"):
        if kind != "semver":
            die(f"{environment} allows only semver vX.Y.Z")
    else:
        die("environment must be one of: dev, staging, prod")

    return kind, sha12


def ensure_mapping(root: Any, key: str) -> Dict[str, Any]:
    if not isinstance(root, dict):
        die("YAML root is not a mapping; cannot proceed safely")
    if key not in root or root[key] is None:
        root[key] = {}
    if not isinstance(root[key], dict):
        die(f"Expected '{key}' to be a mapping")
    return root[key]


def ensure_env_list(root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Helm values commonly store env as a list of {name: ..., value: ...}

    For Cannon, env must already exist. We refuse to create or reshape it
    to avoid YAML churn and unintended diffs.
    """
    env = root.get("env")
    if env is None:
        die("Required key 'env' not found in values.yaml; refusing to add new keys for minimal-diff safety")

    if not isinstance(env, list):
        die("Expected 'env' to be a list in values.yaml")

    for i, item in enumerate(env):
        if not isinstance(item, dict):
            die(f"Expected env[{i}] to be a mapping")
        if "name" not in item:
            die(f"Expected env[{i}] to have a 'name' key")
        if "value" not in item:
            die(f"env var '{item.get('name')}' exists but has no 'value' key; refusing to modify")

    return env  # type: ignore[return-value]


def get_env_entry(env_list: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for item in env_list:
        if str(item.get("name")) == name:
            return item
    return None


def set_env_value(env_list: List[Dict[str, Any]], name: str, value: str) -> bool:
    item = get_env_entry(env_list, name)
    if item is None:
        die(f"Required env var '{name}' not found in values file; refusing to add new keys for MVP safety")
    if "value" not in item:
        die(f"env var '{name}' exists but has no 'value' key; refusing to modify")
    old = str(item.get("value", ""))
    if old == value:
        return False
    item["value"] = value
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Cannon: update Helm env values safely")
    ap.add_argument("--environment", required=True, choices=["dev", "staging", "prod"])
    ap.add_argument("--image-tag", required=True)
    ap.add_argument("--values-file", required=True)
    args = ap.parse_args()

    environment: str = args.environment
    image_tag: str = args.image_tag
    values_file = Path(args.values_file)

    kind, sha12 = validate(environment, image_tag)

    if not values_file.exists():
        die(f"values file does not exist: {values_file}")

    original_text = values_file.read_text(encoding="utf-8")

    yaml = YAML(typ="rt")  # round-trip
    yaml.preserve_quotes = True
    yaml.width = 4096  # avoid reflow/wrapping diffs

    data = yaml.load(original_text)
    if not isinstance(data, dict):
        die("values.yaml did not parse to a mapping; cannot proceed safely")

    # Update image.tag
    image = ensure_mapping(data, "image")
    # Enforce exact key update only
    changed = False
    if str(image.get("tag", "")) != image_tag:
        image["tag"] = image_tag
        changed = True

    # Update env vars
    env_list = ensure_env_list(data)

    # APP_ENV must exist but we don't modify it; assert presence
    if get_env_entry(env_list, "APP_ENV") is None:
        die("Required env var 'APP_ENV' not found; refusing to proceed")

    # GIT_SHA and APP_VERSION must exist and stay consistent
    if kind == "sha":
        # sha tag: set GIT_SHA to <12>, set APP_VERSION to "unversioned" if not already that
        assert sha12 is not None
        changed |= set_env_value(env_list, "GIT_SHA", sha12)

        app_version_entry = get_env_entry(env_list, "APP_VERSION")
        if app_version_entry is None:
            die("Required env var 'APP_VERSION' not found; refusing to proceed")
        current = str(app_version_entry.get("value", ""))
        if current != "unversioned":
            changed |= set_env_value(env_list, "APP_VERSION", "unversioned")
    else:
        # semver: set APP_VERSION to vX.Y.Z, set GIT_SHA to empty string
        changed |= set_env_value(env_list, "APP_VERSION", image_tag)
        changed |= set_env_value(env_list, "GIT_SHA", "")

    if not changed:
        print("No changes needed.")
        return 0

    buf = StringIO()
    yaml.dump(data, buf)
    new_text = buf.getvalue()

    if new_text == original_text:
        print("No textual changes after dump.")
        return 0

    values_file.write_text(new_text, encoding="utf-8")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
