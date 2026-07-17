#!/usr/bin/env python3
"""Validate the immutable Umbrel app package for release."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from typing import Any, NoReturn

import yaml


ROOT = Path(__file__).resolve().parents[2]
APP_ID = "greg-umbrel-readonly-bridge"
APP_DIR = ROOT / APP_ID
VERSION = "1.0.7"
BRIDGE_IMAGE = (
    "ghcr.io/greg-built-it/umbrel-readonly-bridge:1.0.7@sha256:"
    "64d68675d941faaab661545fb1bdf64cb0e1457eb6c7e6dcb1f710e00121cca5"
)
PROXY_IMAGE = (
    "ghcr.io/greg-built-it/umbrel-openclaw-docker-proxy:1.0.7@sha256:"
    "3285e8c751aa96d02a774ebe6463b37f88841fd33983a5a97bfeb4026d8ec7c1"
)


def fail(message: str) -> NoReturn:
    print(f"VALIDATION_ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path) -> dict[str, Any]:
    data: Any
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid YAML in {path.relative_to(ROOT)}: {exc}")
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return data


def validate() -> None:
    manifest = load_yaml(APP_DIR / "umbrel-app.yml")
    compose = load_yaml(APP_DIR / "docker-compose.yml")
    store = load_yaml(ROOT / "umbrel-app-store.yml")

    if manifest.get("id") != APP_ID:
        fail("manifest app id mismatch")
    if manifest.get("version") != VERSION:
        fail(f"manifest version must be {VERSION}")
    if manifest.get("gallery") != []:
        fail("manifest gallery must be an empty list")
    if APP_ID not in store.get("apps", []):
        fail("app is missing from umbrel-app-store.yml")

    services = compose.get("services")
    if not isinstance(services, dict):
        fail("Compose services must be a mapping")
    expected_images = {
        "init-token": BRIDGE_IMAGE,
        "app": BRIDGE_IMAGE,
        "openclaw-docker-proxy": PROXY_IMAGE,
    }
    for service_name, expected_image in expected_images.items():
        service = services.get(service_name)
        if not isinstance(service, dict):
            fail(f"missing Compose service: {service_name}")
        if service.get("image") != expected_image:
            fail(f"unexpected immutable image reference for {service_name}")

    image_pattern = re.compile(
        rf"^ghcr\.io/[^\s]+:{re.escape(VERSION)}@sha256:[0-9a-f]{{64}}$"
    )
    for service_name, service in services.items():
        if not isinstance(service, dict):
            fail(f"Compose service {service_name} must be a mapping")
        volumes = service.get("volumes", [])
        if not isinstance(volumes, list) or not all(
            isinstance(volume, str) for volume in volumes
        ):
            fail(f"all volume entries for {service_name} must be strings")
        image = service.get("image")
        if image is not None and (
            not isinstance(image, str) or image_pattern.fullmatch(image) is None
        ):
            fail(f"image for {service_name} must be an immutable {VERSION} digest")

    package_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (APP_DIR / "umbrel-app.yml", APP_DIR / "docker-compose.yml")
    )
    if ":latest" in package_text:
        fail("latest image reference is forbidden")
    if ":1.0.5@sha256:" in package_text or ":1.0.6@sha256:" in package_text:
        fail("stale release image reference found")

    markers = ("PLACE" + "HOLDER", "TO" + "DO", "FIX" + "ME")
    secret_patterns = {
        "GitHub token": re.compile(
            r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{30,}|"
            r"github_pat_[A-Za-z0-9_]{40,})"
        ),
        "AWS access key": re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}"),
        "JWT": re.compile(
            r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
        ),
        "URL credentials": re.compile(r"https?://[^\s/:]+:[^\s/@]+@"),
    }
    private_key_marker = "".join(
        chr(code)
        for code in (
            45, 45, 45, 45, 45, 66, 69, 71, 73, 78, 32, 80, 82, 73, 86,
            65, 84, 69, 32, 75, 69, 89, 45, 45, 45, 45, 45,
        )
    )

    for path in sorted(APP_DIR.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in markers:
            if marker in text:
                fail(f"{marker} found in {path.relative_to(ROOT)}")
        if private_key_marker in text:
            fail(f"private key material found in {path.relative_to(ROOT)}")
        for label, pattern in secret_patterns.items():
            if pattern.search(text):
                fail(f"possible {label} found in {path.relative_to(ROOT)}")

    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        expected_tag = f"v{VERSION}"
        if os.environ.get("GITHUB_REF_NAME") != expected_tag:
            fail(f"release tag must be {expected_tag}")

    print(
        f"PACKAGE_VALIDATION=pass version={VERSION} gallery=[] "
        "volumes=strings images=immutable latest=absent stale=absent "
        "markers=clean secrets=clean"
    )


if __name__ == "__main__":
    validate()
