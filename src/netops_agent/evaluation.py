"""Ground truth from raw API data, and answer scoring, for eval/questions.jsonl."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .client import MerakiClient

EVENT_TYPES = ("switch", "wireless", "appliance")


@dataclass
class Snapshot:
    """Every raw API response the questions need, fetched once."""

    orgs: list[dict[str, Any]]
    networks: list[dict[str, Any]]
    devices: list[dict[str, Any]]
    statuses: list[dict[str, Any]]
    ports: dict[str, list[dict[str, Any]]]  # serial -> port statuses
    clients: list[dict[str, Any]]
    events: dict[str, list[dict[str, Any]]]  # productType -> events

    @classmethod
    def fetch(cls, c: MerakiClient) -> Snapshot:
        orgs = c.get("/organizations")
        nets, devs, stats = [], [], []
        for o in orgs:
            nets += c.get(f"/organizations/{o['id']}/networks", {"perPage": 1000})
            devs += c.get(f"/organizations/{o['id']}/devices", {"perPage": 1000})
            stats += c.get(f"/organizations/{o['id']}/devices/statuses", {"perPage": 1000})
        ports = {
            d["serial"]: c.get(f"/devices/{d['serial']}/switch/ports/statuses")
            for d in devs
            if d.get("productType") == "switch"
        }
        clients: list[dict[str, Any]] = []
        events: dict[str, list[dict[str, Any]]] = {pt: [] for pt in EVENT_TYPES}
        for n in nets:
            clients += c.get(f"/networks/{n['id']}/clients", {"timespan": 86400, "perPage": 1000})
            for pt in EVENT_TYPES:
                if pt in n.get("productTypes", []):
                    events[pt] += c.get(f"/networks/{n['id']}/events", {"productType": pt, "perPage": 100})["events"]
        return cls(orgs, nets, devs, stats, ports, clients, events)


def _num(v: int) -> dict[str, Any]:
    return {"type": "number", "value": v}


def _set(v: list[str]) -> dict[str, Any]:
    return {"type": "set", "value": sorted(v)}


def _any(counter: Counter[str]) -> dict[str, Any]:
    if not counter:
        return {"type": "set", "value": []}
    top = max(counter.values())
    return {"type": "any_of", "value": sorted(k for k, v in counter.items() if v == top)}


def truth(kind: str, p: dict[str, Any], s: Snapshot) -> dict[str, Any]:
    names = {d["serial"]: d.get("name") or d["serial"] for d in s.devices}
    all_ports = [pt for ports in s.ports.values() for pt in ports]
    wireless = [c for c in s.clients if c.get("ssid")]
    match kind:
        case "org_count":
            return _num(len(s.orgs))
        case "org_names":
            return _set([o["name"] for o in s.orgs])
        case "network_count":
            return _num(len(s.networks))
        case "network_names":
            return _set([n["name"] for n in s.networks])
        case "networks_with_product":
            return _set([n["name"] for n in s.networks if p["product_type"] in n.get("productTypes", [])])
        case "device_count":
            pt = p.get("product_type")
            return _num(sum(1 for d in s.devices if pt is None or d.get("productType") == pt))
        case "devices_with_status":
            return _set([names.get(d["serial"], d["serial"]) for d in s.statuses if d.get("status") == p["status"]])
        case "status_count":
            return _num(sum(1 for d in s.statuses if d.get("status") == p["status"]))
        case "not_online_count":
            return _num(sum(1 for d in s.statuses if d.get("status") != "online"))
        case "top_model":
            return _any(Counter(d["model"] for d in s.devices))
        case "network_most_devices":
            net_names = {n["id"]: n["name"] for n in s.networks}
            return _any(Counter(net_names.get(d.get("networkId"), "?") for d in s.devices if d.get("networkId")))
        case "port_count":
            return _num(sum(1 for pt in all_ports if pt.get("status") == p["status"]))
        case "switches_with_port_errors":
            return _set([names[sn] for sn, ports in s.ports.items() if any(pt.get("errors") for pt in ports)])
        case "slow_ports":
            return _num(
                sum(
                    1
                    for pt in all_ports
                    if pt.get("status") == "Connected" and pt.get("speed") in ("10 Mbps", "100 Mbps")
                )
            )
        case "switch_most_connected":
            return _any(
                Counter(
                    {names[sn]: sum(pt.get("status") == "Connected" for pt in ports) for sn, ports in s.ports.items()}
                )
            )
        case "poe_ports":
            return _num(sum(1 for pt in all_ports if (pt.get("powerUsageInWh") or 0) > 0))
        case "top_ssid":
            return _any(Counter(c["ssid"] for c in wireless))
        case "wireless_client_count":
            return _num(len(wireless))
        case "ssid_count":
            return _num(len({c["ssid"] for c in wireless}))
        case "event_count":
            et = p.get("event_type")
            return _num(sum(1 for e in s.events[p["product_type"]] if et is None or e.get("type") == et))
        case "top_event_device":
            evs = [e for e in s.events[p["product_type"]] if e.get("type") == p["event_type"]]
            return _any(Counter(e.get("deviceName") or e.get("deviceSerial") for e in evs))
    raise ValueError(f"unknown question kind {kind}")


def score(answer: str, expected: dict[str, Any]) -> bool:
    text = answer.lower()
    value = expected["value"]
    if expected["type"] == "number":
        return value in {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)}
    if expected["type"] == "set":
        if not value:
            return bool(re.search(r"\b(none|no |zero|0)\b", text))
        return all(str(v).lower() in text for v in value)
    if expected["type"] == "any_of":
        return any(str(v).lower() in text for v in value)
    raise ValueError(expected["type"])
