import argparse
import yaml
import re
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
        self.relays = self._parse_amt_relays()
        self.gateways = self._parse_amt_gateways()
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
        relays = {}
        for relay in self.config.amt.relays:
            assert relay.name not in relays, f"Duplicated relay: '{relay.name}'"
            relays[relay.name] = relay

        return relays

    def _parse_amt_gateways(self):
        gateways = {}
        checked_sinks = set()
        for gateway in self.config.amt.gateways:
            assert gateway.name not in gateways, f"Duplicated gateway: '{gateway.name}'"
            gateways[gateway.name] = gateway

            for sink in gateway.sink:
                assert sink not in checked_sinks, f"Duplicated sink: '{sink}'"
                checked_sinks.add(sink)

        return gateways

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
        self._generate_scenarios(generated)

        return generated.to_dict()

    def _generate_nodes(self, generated):
        generated.nodes = list(self.nodes)

    def _generate_links(self, generated):
        generated.link.mask = "255.255.255.0"
        generated.link.interfaces = [
            {"name": f"link({u}, {v})", "subnet": d["subnet"], "nodes": [u, v]}
            for u, v, d in self.links
        ]

    def _generate_scenarios(self, generated):
        events = self._events()
        routing = self._routing(events)

        generated.scenarios = []

        for time in events:
            scenario = addict.Dict()
            scenario.time = time

            multicast_routes = []
            for multicast_route in multicast_routes:
                route = addict.Dict(multicast_route)

                multicast_routes.append(
                    {"group": route.group, "address": route.address}
                )

            actions = []
            for name, app in self.applications.items():
                if app.start == time:
                    actions.append({"start": app.to_dict()})
                if app.stop == time:
                    actions.append({"stop": app.to_dict()})

            scenario.multicast_routes = multicast_routes
            scenario.actions = actions
            generated.scenarios.append(scenario.to_dict())

    def _events(self):
        events = set([self.config.start, self.config.stop])

        for app in self.config.applications:
            events.add(app.start)
            events.add(app.stop)

        return sorted(events)

    def _scenario(self, generated):
        generated.scenarios = []
        events = self._events()

        for time in events:
            scenario = addict.Dict()
            running_apps = []
            for _, app in self.applications.items():
                if time >= app.start and time < app.stop:
                    running_apps.append(app)

            actions, multicast_routes = self._scenario_impl(time, running_apps)

            scenario.time = time
            scenario.actions = actions
            scenario.multicast_routes = multicast_routes

            generated.scenarios.append(scenario.to_dict())

    def _scenario_impl(self, time, running_apps):
        actions = []
        multicast_routes = []

        for name, app in self.applications.items():
            if app.start == time:
                actions.append({"start": app.to_dict()})
            if app.stop == time:
                actions.append({"stop": app.to_dict()})

        sources = {}
        targets = {}

        for app in running_apps:
            if app.type == "OnOff":
                sources[app.address] = app

            elif app.type == "PacketSink":
                targets[app.address] = app

            else:
                assert True, f"not support type '{app.type}'"

        for address, app in targets.items():
            multicast_address = self.multicasts[address].address
            multicast_graph = self._multicast_graph()
            target = app.node
            source = sources[address].node

            try:
                path = nx.shortest_path(multicast_graph, source=source, target=target)

                multicast_routes.append(
                    {"group": address, "address": multicast_address, "routes": [path]}
                )
            except nx.NetworkXNoPath:
                gateway = self._find_gateway_node(target)

                best_relay = None
                best_relay_length = float("inf")
                for name, relay in self.relays.items():
                    try:
                        length = nx.shortest_path_length(
                            self.graph, source=relay.node, target=gateway
                        )

                        if best_relay_length > length:
                            best_relay = relay.node
                            best_relay_length = length
                    except nx.NetworkXNoPath:
                        continue

                relay_path = nx.shortest_path(
                    multicast_graph, source=source, target=best_relay
                )

                gateway_path = nx.shortest_path(
                    multicast_graph, source=gateway, target=target
                )

                multicast_routes.append(
                    {
                        "group": address,
                        "address": multicast_address,
                        "routes": [relay_path, gateway_path],
                    }
                )

        return multicast_routes

    def _create_multicast_route_entry(self, multicast_routes):
        route_entry = []

        for multicast_route in multicast_routes:
            path = multicast_route["routes"]
            ic(path)
            for i in range(len(path) - 2):
                route_entry.append((path[i], path[i - 1]))
        ic(route_entry)

        return route_entry

    def _create_application_actions(self, time):
        pass

    def _find_link(self, u, v):
        return self.graph[u][v]["subnet"]

    def _multicast_graph(self):
        def is_multicast_enabled(u, v):
            return self.graph[u][v]["multicast"]

        return nx.subgraph_view(self.graph, filter_edge=is_multicast_enabled)

    def _find_gateway_node(self, target):
        for _, gateway in self.gateways.items():
            if target in gateway.sinks:
                return gateway.node

        assert True, f"Not found gateway: '{target}'"


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
