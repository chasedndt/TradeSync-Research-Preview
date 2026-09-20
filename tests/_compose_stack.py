"""The compose stack as the bounded profile and its optional files merge it, for tests that read compose.

Services and top-level networks are merged in the order the deploy commands
pass the files: compose.full.yml, then compose.market-command.yml, then the
optional compose.ingress.yml and compose.signer.yml. Mappings such as
``environment`` and ``networks`` merge key by key, as compose merges them.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops"
STACK = ("compose.full.yml", "compose.market-command.yml", "compose.ingress.yml", "compose.signer.yml")


def load(name: str) -> dict:
    return yaml.safe_load((OPS / name).read_text(encoding="utf-8-sig")) or {}


def networks_of(service: dict) -> set[str]:
    """The networks a service joins; compose puts a service that declares none on default."""
    declared = service.get("networks")
    return {"default"} if declared is None else set(declared)


def stack() -> tuple[dict[str, dict], dict[str, dict]]:
    """Merged services and top-level networks."""
    services: dict[str, dict] = {}
    networks: dict[str, dict] = {}
    for name in STACK:
        data = load(name)
        for service, body in (data.get("services") or {}).items():
            merged = services.setdefault(service, {})
            for key, value in (body or {}).items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                else:
                    merged[key] = value
        for network, body in (data.get("networks") or {}).items():
            networks[network] = {**networks.get(network, {}), **(body or {})}
    return services, networks


def members(network: str) -> set[str]:
    services, _ = stack()
    return {name for name, body in services.items() if network in networks_of(body)}


def environment(service: str) -> dict[str, object]:
    services, _ = stack()
    return dict(services[service].get("environment") or {})
