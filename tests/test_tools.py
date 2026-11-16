from netops_agent import tools

ORG = "1000001"


def test_list_organizations(client):
    assert tools.list_organizations(client) == [{"id": ORG, "name": "Synthetic Org"}]


def test_list_networks(client):
    assert [n["name"] for n in tools.list_networks(client, ORG)] == ["Branch-SJC", "Branch-RTP"]


def test_list_devices_filters(client):
    assert len(tools.list_devices(client, ORG)) == 8
    assert {d["name"] for d in tools.list_devices(client, ORG, product_type="switch")} == {
        "sjc-sw1",
        "sjc-sw2",
        "rtp-sw1",
    }
    assert len(tools.list_devices(client, ORG, network_id="N_1002")) == 3


def test_device_statuses_filter(client):
    assert [d["name"] for d in tools.get_device_statuses(client, ORG, status="offline")] == ["sjc-ap2"]


def test_switch_port_statuses(client):
    ports = tools.get_switch_port_statuses(client, "Q2BB-0001-0002")
    assert len(ports) == 8
    assert [p["portId"] for p in ports if p["errors"]] == ["2", "6"]


def test_client_counts_per_ssid(client):
    assert tools.get_client_counts_per_ssid(client, "N_1001") == {"Corp": 7, "Guest": 4, "(wired)": 3}


def test_network_events_by_type(client):
    evs = tools.get_network_events(client, "N_1001", "switch", event_type="port_status")
    assert len(evs) == 3
    assert {e["deviceName"] for e in evs} == {"sjc-sw1", "sjc-sw2"}
