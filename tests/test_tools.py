from netops_agent import tools

ORG = "669910444571370859"
NET = "L_669910444571385303"
SWITCH = "QBSB-DU4U-25UB"


def test_list_organizations(client):
    assert tools.list_organizations(client) == [{"id": ORG, "name": "DevNet-47LAwcsYS1sK"}]


def test_list_networks(client):
    assert [n["name"] for n in tools.list_networks(client, ORG)] == ["branch_office"]


def test_list_devices_filters(client):
    assert len(tools.list_devices(client, ORG)) == 4
    assert [d["serial"] for d in tools.list_devices(client, ORG, product_type="switch")] == [SWITCH]
    assert len(tools.list_devices(client, ORG, network_id=NET)) == 4
    assert tools.list_devices(client, ORG, network_id="L_other") == []


def test_device_statuses_filter(client):
    assert len(tools.get_device_statuses(client, ORG, status="dormant")) == 4
    assert tools.get_device_statuses(client, ORG, status="online") == []


def test_switch_port_statuses(client):
    ports = tools.get_switch_port_statuses(client, SWITCH)
    assert len(ports) == 30
    assert {p["status"] for p in ports} == {"Disconnected"}
    assert all(p["errors"] == ["Port disconnected"] for p in ports)


def test_client_counts_per_ssid(client):
    assert tools.get_client_counts_per_ssid(client, NET) == {}


def test_network_events_by_type(client):
    assert tools.get_network_events(client, NET, "switch") == []
    assert tools.get_network_events(client, NET, "switch", event_type="port_status") == []
