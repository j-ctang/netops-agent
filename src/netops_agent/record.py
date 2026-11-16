"""Save raw live API responses as fixtures: python -m netops_agent.record tests/fixtures"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from .client import MerakiClient, fixture_name

EVENT_TYPES = ("switch", "wireless", "appliance")


def record(out: Path, client: MerakiClient) -> None:
    out.mkdir(parents=True, exist_ok=True)
    base_path = httpx.URL(client.base_url).path

    def save(path: str, params: dict | None = None) -> object:
        data = client.get(path, params)
        req = httpx.Request("GET", client.base_url + path, params=params)
        (out / f"{fixture_name(req, base_path)}.json").write_text(json.dumps(data, indent=2) + "\n")
        return data

    for org in save("/organizations"):
        oid = org["id"]
        nets = save(f"/organizations/{oid}/networks", {"perPage": 1000})
        devices = save(f"/organizations/{oid}/devices", {"perPage": 1000})
        save(f"/organizations/{oid}/devices/statuses", {"perPage": 1000})
        for d in devices:
            if d.get("productType") == "switch":
                save(f"/devices/{d['serial']}/switch/ports/statuses")
        for n in nets:
            save(f"/networks/{n['id']}/clients", {"timespan": 86400, "perPage": 1000})
            for pt in EVENT_TYPES:
                if pt in n.get("productTypes", []):
                    save(f"/networks/{n['id']}/events", {"productType": pt, "perPage": 100})


if __name__ == "__main__":
    record(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures"), MerakiClient())
