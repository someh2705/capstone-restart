import argparse
import yaml
import re
from collections import defaultdict
import tomllib
import addict
import networkx as nx
from icecream import ic

# python scratch/capstone/scripts/generate.py scratch/capstone/scenarios/simple-amt.meta.toml


class ScenarioGenerator:
    def __init__(self, meta):
        with open(meta, "rb") as f:
            self.config = addict.Dict(tomllib.load(f))

        self.nodes = self._prase_nodes()
        self.multicasts = self._parse_multicasts()
        self.links = self._parse_link_paths()
        self.graph = self._build_graph()
        self.relay_nodes = self._parse_amt_relays()
        self.gateway_nodes = self._parse_amt_gateways()
        self.applications = self._parse_applications()

        ic(self.links)

    def _prase_nodes(self):
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

    def _parse_multicasts(self):
        multicasts = {}
        for multicast in self.config.multicasts:
            name = multicast.name

            assert name not in multicasts, f"Duplicated multicast: '{name}'"

            multicasts[name] = multicast

        return multicasts

    def _parse_link_paths(self):
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

                edges.append((u, v, d))
                i += 2
                counter += 1

        return edges

    def _build_graph(self):
        G = nx.Graph()
        G.add_nodes_from(self.nodes)
        G.add_edges_from(self.links)

        return G

    def _parse_amt_relays(self):
        relay_nodes = []
        for relay_node in self.config.amt.relays:
            assert relay_node not in relay_nodes, (
                f"Duplicated relay: '{relay_node}'"
            )
            relay_nodes.append(relay_node)

        return relay_nodes

    def _parse_amt_gateways(self):
        gateway_configs = []
        checked_nodes = []
        for gateway_node in self.config.amt.gateways:
            assert gateway_node.node not in checked_nodes, (
                f"Duplicated gateway: '{gateway_node}'"
            )
            gateway_configs.append(gateway_node)
            checked_nodes.append(gateway_node.node)

        return gateway_configs

    def _parse_applications(self):
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

    def generate(self):
        generated = addict.Dict()

        self._generate_nodes(generated)
        self._generate_links(generated)
        processor = ScenarioProcessor(
            self.config,
            self.nodes,
            self.graph,
            self.applications,
            self.multicasts,
            self.relay_apps,
            self.gateway_apps,
        )
        processor.generate_scenarios(generated)

        return generated.to_dict()

    def _generate_nodes(self, generated):
        generated.nodes = list(self.nodes)

    def _generate_links(self, generated):
        generated.link.mask = "255.255.255.0"
        generated.link.interfaces = [
            {"name": f"link({u}, {v})", "subnet": d["subnet"], "nodes": [u, v]}
            for u, v, d in self.links
        ]


    def _find_link(self, u, v):
        return self.graph[u][v]["subnet"]

class ScenarioProcessor:
    def __init__(
        self, config, nodes, graph, applications, multicasts, relay_apps, gateway_apps
    ):
        self.config = config
        self.nodes = nodes
        self.graph = graph
        self.applications = applications
        self.multicasts = multicasts
        self.relay_apps = relay_apps
        self.gateway_apps = gateway_apps

    def _build_multicast_graph(self):
        def is_multicast_enabled(u, v):
            return self.graph[u][v]["multicast"]

        return nx.subgraph_view(self.graph, filter_edge=is_multicast_enabled)

    def _get_event_timeline(self):
        events = set([self.config.start, self.config.stop])

        for app in self.applications.values():
            events.add(app.start)
            events.add(app.stop)

        return sorted(list(events))

    def generate_scenarios(self, generated):
        timeline = self._get_event_timeline()
        scenarios = []

        connected_port = 10888
        running_hosts = []
        running_sinks = []
        running_tunnel = []

        for time in timeline:
            scenario = addict.Dict()
            should_connect_sink = []
            actions = []

            for name, app in self.applications.items():
                if app.start == time:
                    if app.type == "PacketSink":
                        should_connect_sink.append((name, app))
                        running_sinks.append((name, app))
                    if app.type == "OnOff":
                        running_hosts.append((name, app))

                if app.stop == time:
                    if app.type == "PacketSink":
                        running_sinks.remove((name, app))

                    if app.type == "OnOff":
                        running_hosts.remove((name, app))

            multicast_paths = defaultdict(list)
            for name, app in should_connect_sink:
                multicast_graph = self._build_multicast_graph()

                target = app.node
                sources = []

                for name, host in running_hosts:
                    if host.address == app.address:
                        sources.append(host)
                else:
                    assert len(sources) != 0, (
                        f"Not found source application: '{target}'"
                    )

                source = self._find_closest_node([s.node for s in sources], target)

                try:
                    path = nx.shortest_path(
                        multicast_graph, source=source, target=target
                    )
                    multicast_paths[app.address].append(path)
                    ic(path)
                except nx.NetworkXNoPath:
                    # 만약 현재 실행중인 gateway로 multicast를 받을 수 있으면 검색 필요 없음.
                    for relay_app, gateway_app, _ in running_tunnel:
                        if target in gateway_app.sinks:
                            if app.address == relay_app.address:
                                continue

                    gateway = next(.node for node, _ in self.gateway_apps.items())
                    relay = self._find_closest_node(
                        [r.node for _, r in self.relays.items()], target
                    )

                    relay_path = nx.shortest_path(
                        multicast_graph, source=source, target=relay
                    )
                    gateway_path = nx.shortest_path(
                        multicast_graph, source=gateway, target=target
                    )

                    multicast_paths[app.address].append(relay_path)
                    multicast_paths[app.address].append(gateway_path)

                    relay_app = next(r for r in self.relays if r.node == relay)
                    gateway_app = next(g for g in self.gateways if g.node == gateway)

                    running_tunnel.append((relay, gateway, connected_port))
                    connected_port += 1

            scenarios.append(scenario.to_dict())

        ic(scenarios)

    def _find_closest_node(self, candidate_nodes, destination_node):
        best_node = None
        best_length = float("inf")

        for node in candidate_nodes:
            try:
                length = nx.shortest_path_length(
                    self.graph, source=node, target=destination_node
                )

                if best_length > length:
                    best_node = node
                    best_length = length

            except nx.NetworkXNoPath:
                continue

        return best_node


def main(meta, output):
    generator = ScenarioGenerator(meta)
    generated = generator.generate()
    convert = yaml.dump(generated, default_flow_style=False, sort_keys=False, indent=2)
    ic(convert)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("meta", help="meta TOML input file")
    parser.add_argument(
        "-o", "--out", help="output scenario YAML file name", default=None
    )

    args = parser.parse_args()

    main(args.meta, args.out)
