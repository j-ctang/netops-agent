"""Agent tools: plain typed functions over MerakiClient. Each returns JSON-able data."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from .client import MerakiClient

ProductType = Literal["appliance", "switch", "wireless", "camera", "cellularGateway", "sensor"]
DeviceStatus = Literal["online", "alerting", "offline", "dormant"]


def list_organizations(client: MerakiClient) -> list[dict[str, Any]]:
    """List organizations the API key can access (id, name)."""
    return [{"id": o["id"], "name": o["name"]} for o in client.get("/organizations")]


def list_networks(client: MerakiClient, org_id: str) -> list[dict[str, Any]]:
    """List networks in an organization (id, name, productTypes, tags)."""
    return [
        {"id": n["id"], "name": n["name"], "productTypes": n.get("productTypes", []), "tags": n.get("tags", [])}
        for n in client.get(f"/organizations/{org_id}/networks", {"perPage": 1000})
    ]


def list_devices(
    client: MerakiClient,
    org_id: str,
    network_id: str | None = None,
    product_type: ProductType | None = None,
) -> list[dict[str, Any]]:
    """List devices in an organization, optionally filtered by network and product type."""
    devices = client.get(f"/organizations/{org_id}/devices", {"perPage": 1000})
    return [
        {k: d.get(k) for k in ("serial", "name", "model", "productType", "networkId")}
        for d in devices
        if (network_id is None or d.get("networkId") == network_id)
        and (product_type is None or d.get("productType") == product_type)
    ]


def get_device_statuses(
    client: MerakiClient,
    org_id: str,
    status: DeviceStatus | None = None,
    network_id: str | None = None,
) -> list[dict[str, Any]]:
    """Device status (online/alerting/offline/dormant) for devices in an organization."""
    rows = client.get(f"/organizations/{org_id}/devices/statuses", {"perPage": 1000})
    return [
        {k: d.get(k) for k in ("serial", "name", "model", "productType", "networkId", "status", "lastReportedAt")}
        for d in rows
        if (status is None or d.get("status") == status) and (network_id is None or d.get("networkId") == network_id)
    ]


def get_switch_port_statuses(client: MerakiClient, serial: str) -> list[dict[str, Any]]:
    """Status of every port on one switch (enabled, status, speed, errors, PoE)."""
    return [
        {
            k: p.get(k)
            for k in ("portId", "enabled", "status", "speed", "duplex", "errors", "isUplink", "powerUsageInWh")
        }
        for p in client.get(f"/devices/{serial}/switch/ports/statuses")
    ]


def get_client_counts_per_ssid(client: MerakiClient, network_id: str, timespan_seconds: int = 86400) -> dict[str, int]:
    """Number of clients seen on each SSID in a network over a timespan. Wired clients count as "(wired)"."""
    clients = client.get(f"/networks/{network_id}/clients", {"timespan": timespan_seconds, "perPage": 1000})
    return dict(Counter(c.get("ssid") or "(wired)" for c in clients))


def get_network_events(
    client: MerakiClient,
    network_id: str,
    product_type: ProductType,
    event_type: str | None = None,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    """Recent event log entries for a network and product type, optionally one event type (e.g. port_status)."""
    params: dict[str, Any] = {"productType": product_type, "perPage": per_page}
    if event_type:
        params["includedEventTypes[]"] = event_type
    data = client.get(f"/networks/{network_id}/events", params)
    return [
        {k: e.get(k) for k in ("occurredAt", "type", "description", "deviceSerial", "deviceName", "eventData")}
        for e in data.get("events", [])
        if event_type is None or e.get("type") == event_type
    ]


TOOLS = [
    list_organizations,
    list_networks,
    list_devices,
    get_device_statuses,
    get_switch_port_statuses,
    get_client_counts_per_ssid,
    get_network_events,
]
