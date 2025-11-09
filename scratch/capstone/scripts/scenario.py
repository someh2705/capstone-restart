import networkx as nx
from collections import defaultdict
import yaml
import re
from typing import Set, Dict, List, Tuple
import addict
import argparse
import tomllib
from icecream import ic


class ScenarioGenerator:
    def __init__(self, meta):
        with open(meta, "rb") as f:
            self.config = addict.Dict(tomllib.load(f))

        self.nodes = self._parse_nodes()
        self.multicasts = self._parse_multicasts()
        self.graph, self.links = self._parse_link_paths()
        self.relays, self.gateways = self._parse_amt()
        self.applications = self._parse_applications()

        if True:
            ic(self.nodes)
            ic(self.multicasts)
            ic(self.links)
            ic(self.relays)
            ic(self.gateways)
            ic(self.applications)

    def _parse_nodes(self) -> Set[str]:
        nodes = set()
        for node in self.config.node.explicits:
            assert node not in nodes, f"Duplicated node: '{node}'"
            nodes.add(node)

        for pattern in self.config.node.get("patterns", []):
            for i in range(1, pattern.count + 1):
                node = f"{pattern.prefix}{i}"
                assert node not in nodes, f"Duplicated node pattern: '{node}'"
                nodes.add(node)

        return nodes

    def _parse_multicasts(self) -> Dict[str, addict.Dict]:
        multicasts = {}
        for multicast in self.config.multicasts:
            name = multicast.name

            assert name not in multicasts, f"Duplicated multicast: '{name}'"

            multicasts[name] = multicast

        return multicasts

    def _parse_link_paths(self) -> Tuple[nx.Graph, Dict[Tuple[str, str], addict.Dict]]:
        links = {}
        edges = []
        counter = 1

        for path in self.config.link.paths:
            segments = re.split(r"( -- | - )", path.strip())

            i = 0
            while i < len(segments) - 2:
                u = segments[i].strip()
                delimiter = segments[i + 1].strip()
                v = segments[i + 2].strip()

                assert u in self.nodes, f"Not found node '{u}'"
                assert v in self.nodes, f"Not found node '{v}'"

                d = {}
                d["multicast"] = delimiter == "-"
                d["subnet"] = f"10.0.{counter}.0"

                assert (u, v) not in links, f"Duplicated '{u, v}'"
                assert (v, u) not in links, f"Duplicated '{v, u}'"

                links[(u, v)] = addict.Dict(d)
                links[(v, u)] = addict.Dict(d)
                edges.append((u, v, d))

                i += 2
                counter += 1

        G = nx.Graph()
        G.add_nodes_from(self.nodes)
        G.add_edges_from(edges)

        return G, links

    def _parse_amt(self) -> Tuple[List[str], List[str]]:
        relays = []
        gateways = []
        for relay in self.config.amt.relays:
            assert relay not in relays, f"Duplicated relay: '{relay}'"
            relays.append(relay)

        for gateway in self.config.amt.gateways:
            assert gateway not in gateways, f"Duplicated gateway: '{gateway}'"
            gateways.append(gateway)

        return relays, gateways

    def _parse_applications(self) -> Dict[str, addict.Dict]:
        applications = {}

        for app in self.config.applications:
            assert app.name not in applications, f"Duplicated application: '{app.name}'"
            assert app.address in self.multicasts, (
                f"Not found multicast address: '{app.address}'"
            )
            assert app.node in self.nodes, f"Not found node: '{app.node}'"
            assert app.start > self.config.start, f"Invalid start time '{app.start}'"
            assert app.stop < self.config.stop, f"Invalid stop time '{app.stop}'"

            applications[app.name] = app

        return applications

    # scenario 생성

    def generate(self):
        self._generate_scenario()

    def _generate_scenario(self):
        self.timeline = self._get_event_timeline()
        self.scenarios = []
        self.port_counter = 10888
        self.running_hosts: List[addict.Dict] = []
        self.running_sinks: List[addict.Dict] = []
        # relay node name, gateway, port, address
        self.running_tunnels: List[Tuple[str, addict.Dict, int, str]] = []

        for time in self.timeline:
            ic(time)

            self._run_timeline(time)

            ic(self.scenarios)
            ic(self.running_hosts)
            ic(self.running_sinks)
            ic(self.running_tunnels)
            ic(self.should_connect_sinks)
            ic(self.multicast_paths)
            ic("==============================")

    def _run_timeline(self, time):
        self.scenario = addict.Dict()
        self.should_connect_sinks: List[addict.Dict] = []
        self.scenario_actions: List[addict.Dict] = []

        self._schedule_scenario(time)
        self._create_multicast_routing()

    def _schedule_scenario(self, time):
        for app in self.applications.values():
            if app.start == time:
                if app.type == "PacketSink":
                    self.should_connect_sinks.append(app)
                    self.running_sinks.append(app)
                if app.type == "OnOff":
                    self.running_hosts.append(app)

            if app.stop == time:
                if app.type == "PacketSink":
                    self.running_sinks.remove(app)

                if app.type == "OnOff":
                    self.running_hosts.remove(app)

    def _create_multicast_routing(self):
        self.multicast_paths = defaultdict(list)
        for app in self.should_connect_sinks:
            multicast_graph = self._multicast_subgraph()

            target: str = app.node
            sources: List[addict.Dict] = []
            for host in self.running_hosts:
                if app.address == host.address:
                    sources.append(host)

            source: str = self._find_closest_node([s.node for s in sources], target)
            self._find_multicast_path(multicast_graph, source, target, app.address)

    def _find_multicast_path(self, multicast_graph, source, target, address):
        try:
            path = nx.shortest_path(multicast_graph, source, target)
            self.multicast_paths[address].append(path)
        except nx.NetworkXNoPath:
            for relay, gateway, _, group in self.running_tunnels:
                if address == group and nx.has_path(multicast_graph, gateway, target):
                    ic(
                        f"use running tunnel: target({target}), relay({relay}), gateway({gateway})"
                    )
                    return

            gateways = [
                g for g in self.gateways if nx.has_path(multicast_graph, g, target)
            ]
            gateway = self._find_closest_node(gateways, target)

            relays = [r for r in self.relays if nx.has_path(multicast_graph, r, source)]
            relay = self._find_closest_node(relays, gateway)

            self.running_tunnels.append((relay, gateway, self.port_counter, address))
            self.port_counter += 1

            relay_path = nx.shortest_path(multicast_graph, source, relay)
            gateway_path = nx.shortest_path(multicast_graph, gateway, target)

            self.multicast_paths[address].append(relay_path)
            self.multicast_paths[address].append(gateway_path)

            ic(gateways)
            ic(gateway)
            ic(relays)
            ic(relay)

    def _multicast_subgraph(self) -> nx.Graph:
        def is_multicast_enabled(u, v):
            return self.graph[u][v]["multicast"]

        return nx.subgraph_view(self.graph, filter_edge=is_multicast_enabled)

    def _get_event_timeline(self):
        timeline = set([self.config.start, self.config.stop])

        for app in self.applications.values():
            timeline.add(app.start)
            timeline.add(app.stop)

        return sorted(list(timeline))

    def _find_closest_node(self, nodes, target):
        best_node = None
        best_length = float("inf")

        for node in nodes:
            try:
                length = nx.shortest_path_length(self.graph, source=node, target=target)

                if best_length > length:
                    best_node = node
                    best_length = length

            except nx.NetworkXNoPath:
                continue

        return best_node


def main(meta, output):
    generator = ScenarioGenerator(meta)
    generated = generator.generate()
    ic(yaml.dump(generated, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("meta", help="meta TOML input file")
    parser.add_argument(
        "-o", "--out", help="output scenario YAML file name", default=None
    )

    args = parser.parse_args()

    main(args.meta, args.out)
