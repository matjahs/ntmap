"""NetBox REST API client used by ntmap instead of direct Postgres access."""

from __future__ import annotations

import requests


class NetBoxError(Exception):
    pass


class NetBoxClient:
    def __init__(self, url: str, token: str, timeout: int = 60):
        base = url.rstrip("/")
        if not base.endswith("/api"):
            base = f"{base}/api"
        self.base_url = base
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {token}",
                "Accept": "application/json",
            }
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.get(url, params=params or {}, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise NetBoxError(str(exc)) from exc

    def get_all(self, path: str, params: dict | None = None) -> list:
        params = dict(params or {})
        params.setdefault("limit", 1000)
        payload = self._get(path, params)
        if isinstance(payload, list):
            return payload
        results = list(payload.get("results") or [])
        next_url = payload.get("next")
        while next_url:
            try:
                response = self.session.get(next_url, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise NetBoxError(str(exc)) from exc
            results.extend(payload.get("results") or [])
            next_url = payload.get("next")
        return results

    @staticmethod
    def _nested_name(obj) -> str | None:
        if not obj:
            return None
        if isinstance(obj, dict):
            return obj.get("name")
        return None

    @staticmethod
    def _nested_id(obj) -> int | None:
        if not obj:
            return None
        if isinstance(obj, dict):
            return obj.get("id")
        return None

    @staticmethod
    def _type_value(obj) -> str | None:
        if not obj:
            return None
        if isinstance(obj, dict):
            return obj.get("value") or obj.get("label")
        return str(obj)

    def find_devices_by_name_pattern(self, name_pattern: str) -> list[dict]:
        devices = self.get_all(
            "dcim/devices/",
            {
                "name__ic": name_pattern,
                "exclude": "config_context",
            },
        )
        rows = []
        for device in devices:
            device_type = device.get("device_type") or {}
            manufacturer = device_type.get("manufacturer") if isinstance(device_type, dict) else None
            role = device.get("role") or device.get("device_role") or {}
            cluster = device.get("cluster")
            virtual_chassis = device.get("virtual_chassis")
            rows.append(
                {
                    "id": device.get("name"),
                    "netbox_id": device.get("id"),
                    "serial": device.get("serial"),
                    "virtual_chassis": self._nested_name(virtual_chassis),
                    "virtual_chassis_netbox_id": self._nested_id(virtual_chassis),
                    "position_in_vc": device.get("vc_position"),
                    "cluster": self._nested_name(cluster),
                    "type": self._nested_name(role),
                    "model": device_type.get("model") if isinstance(device_type, dict) else None,
                    "manufacturer": self._nested_name(manufacturer),
                    "class": "devices",
                }
            )
        return rows

    def find_providers_by_name_pattern(self, name_pattern: str) -> list[dict]:
        providers = self.get_all(
            "circuits/providers/",
            {"name__ic": name_pattern},
        )
        rows = []
        for provider in providers:
            asn = provider.get("asn")
            if asn is None:
                asns = provider.get("asns") or []
                if asns and isinstance(asns[0], dict):
                    asn = asns[0].get("asn")
            rows.append(
                {
                    "netbox_id": provider.get("id"),
                    "id": provider.get("name"),
                    "slug": provider.get("slug"),
                    "asn": asn,
                    "class": "circuits",
                    "type": "provider",
                }
            )
        return rows

    def find_circuits_for_provider(
        self,
        provider_node: dict,
        map_device_ids: set[int],
        group: float,
    ) -> list[dict]:
        circuits = self.get_all(
            "circuits/circuits/",
            {"provider_id": provider_node["netbox_id"]},
        )
        rows = []
        for circuit in circuits:
            circuit_id = circuit.get("id")
            circuit_type = circuit.get("type") or {}
            terminations = self.get_all(
                "circuits/circuit-terminations/",
                {"circuit_id": circuit_id},
            )
            for termination in terminations:
                interface = self._resolve_circuit_interface(termination)
                if not interface:
                    continue
                device = interface.get("device") or {}
                device_id = device.get("id") if isinstance(device, dict) else None
                if device_id not in map_device_ids:
                    continue
                cid = circuit.get("cid") or str(circuit_id)
                term_side = termination.get("term_side") or ""
                rows.append(
                    {
                        "provider_netbox_id": provider_node["netbox_id"],
                        "provider": provider_node["id"],
                        "provider_slug": provider_node.get("slug"),
                        "device": device.get("name") if isinstance(device, dict) else None,
                        "device_netbox_id": device_id,
                        "netbox_id": circuit_id,
                        "id": f"{cid}-{term_side}" if term_side else cid,
                        "commit_rate": circuit.get("commit_rate"),
                        "circuit_type": self._nested_name(circuit_type) or (
                            circuit_type.get("name") if isinstance(circuit_type, dict) else None
                        ),
                        "interface_netbox_id": interface.get("id"),
                        "class": "circuits",
                        "type": "circuit",
                        "group": group,
                    }
                )
        return rows

    def _resolve_circuit_interface(self, termination: dict) -> dict | None:
        """Return the device interface linked to a circuit termination, if any."""
        # Direct termination on an interface (NetBox 3.3+)
        term_obj = termination.get("termination")
        term_type = termination.get("termination_type") or ""
        if isinstance(term_type, dict):
            term_type = term_type.get("value") or term_type.get("label") or ""
        if term_obj and "interface" in str(term_type).lower():
            if term_obj.get("device"):
                return term_obj
            # brief nested interface — fetch full object
            iface_id = term_obj.get("id")
            if iface_id:
                try:
                    return self._get(f"dcim/interfaces/{iface_id}/")
                except NetBoxError:
                    return term_obj

        # Legacy field
        legacy_iface = termination.get("interface")
        if isinstance(legacy_iface, dict) and legacy_iface.get("id"):
            if legacy_iface.get("device"):
                return legacy_iface
            try:
                return self._get(f"dcim/interfaces/{legacy_iface['id']}/")
            except NetBoxError:
                return legacy_iface

        # Follow cable peers from the termination
        for peer in termination.get("link_peers") or termination.get("connected_endpoints") or []:
            if not isinstance(peer, dict):
                continue
            peer_type = peer.get("url") or ""
            if "/dcim/interfaces/" in peer_type or peer.get("device"):
                if peer.get("device"):
                    return peer
                peer_id = peer.get("id")
                if peer_id:
                    try:
                        return self._get(f"dcim/interfaces/{peer_id}/")
                    except NetBoxError:
                        return peer
        return None

    def get_device_interfaces(self, device_name: str, device_netbox_id: int) -> list[dict]:
        interfaces = self.get_all(
            "dcim/interfaces/",
            {"device_id": device_netbox_id},
        )
        rows = []
        for iface in interfaces:
            neighbor = self._peer_from_interface(iface)
            lag = iface.get("lag")
            rows.append(
                {
                    "device": device_name,
                    "netbox_id": iface.get("id"),
                    "name": iface.get("name"),
                    "mgmt_only": bool(iface.get("mgmt_only")),
                    "lag_netbox_id": self._nested_id(lag),
                    "lag": self._nested_name(lag),
                    "type": self._type_value(iface.get("type")),
                    "description": iface.get("description"),
                    "neighbor_interface_netbox_id": neighbor.get("neighbor_interface_netbox_id"),
                    "neighbor_interface": neighbor.get("neighbor_interface"),
                    "neighbor_interface_type": neighbor.get("neighbor_interface_type"),
                    "neighbor_interface_mgmt_only": neighbor.get("neighbor_interface_mgmt_only"),
                    "neighbor_netbox_id": neighbor.get("neighbor_netbox_id"),
                    "neighbor": neighbor.get("neighbor"),
                    "neighbor_class": "devices" if neighbor.get("neighbor") else None,
                }
            )
        return rows

    def _peer_from_interface(self, iface: dict) -> dict:
        empty = {
            "neighbor_interface_netbox_id": None,
            "neighbor_interface": None,
            "neighbor_interface_type": None,
            "neighbor_interface_mgmt_only": None,
            "neighbor_netbox_id": None,
            "neighbor": None,
        }
        peers = iface.get("connected_endpoints") or iface.get("link_peers") or []
        for peer in peers:
            if not isinstance(peer, dict):
                continue
            device = peer.get("device")
            # Only device interfaces (skip circuit terminations, etc.)
            if not device:
                continue
            return {
                "neighbor_interface_netbox_id": peer.get("id"),
                "neighbor_interface": peer.get("name"),
                "neighbor_interface_type": self._type_value(peer.get("type")),
                "neighbor_interface_mgmt_only": bool(peer.get("mgmt_only")),
                "neighbor_netbox_id": device.get("id") if isinstance(device, dict) else None,
                "neighbor": device.get("name") if isinstance(device, dict) else None,
            }
        return empty


def get_client_from_config(config) -> NetBoxClient:
    section = config["netbox"]
    url = section.get("url")
    token = section.get("token")
    if not url or not token:
        raise NetBoxError("NetBox url and token must be set in settings.ini [netbox]")
    return NetBoxClient(url=url, token=token)
