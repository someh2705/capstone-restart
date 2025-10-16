import yaml
import networkx as nx
from collections import defaultdict
import itertools
import argparse


def find_multicast_tree(graph, source, sinks, firewalls, amt_sink_map):
    """
    :param graph: 전체 네트워크 토폴로지
    :param source: 멀티캐스트 소스 노드 이름
    :param sinks: 현재 활성화된 sink 노드 집합
    :param firewalls: 멀티캐스트가 차단된 노드 이름 집합
    :param amt_sink_map: sink와 gateway, 사용 가능한 relay 목록
    :return {시작점: {엣지 집합}}
    """

    rooted_tree_edges = defaultdict(set)
    multicast_enabled_graph = graph.copy()
    multicast_enabled_graph.remove_nodes_from(firewalls)

    for sink in sinks:
        try:
            path = nx.shortest_path(multicast_enabled_graph, source=source, target=sink)
            for i in range(len(path) - 1):
                rooted_tree_edges[source].add(tuple(sorted((path[i], path[i + 1]))))

        except nx.NetworkXNoPath:
            if sink not in amt_sink_map:
                continue

            gateway, available_relays = amt_sink_map[sink]

            best_relay = None
            shortest_path_len = float('inf')

            for relay in available_relays:
                try:
                    path_len = nx.shortest_path_length(graph, relay, target=gateway)

                    if path_len < shortest_path_len:
                        shortest_path_len = path_len
                        best_relay = relay

                except nx.NetworkXNoPath:
                    continue

            if not best_relay:
                raise nx.NetworkXAlgorithmError(f"Warning: No path from source '{source}' to any available relays for sink '{sink}'.")


            path_to_relay = nx.shortest_path(
                multicast_enabled_graph, source=source, target=best_relay
            )

            for i in range(len(path_to_relay) - 1):
                rooted_tree_edges[source].add( tuple(sorted((path_to_relay[i], path_to_relay[i + 1]))))

            path_from_gateway = nx.shortest_path(
                multicast_enabled_graph, source=gateway, target=sink
            )
            for i in range(len(path_from_gateway) - 1):
                rooted_tree_edges[gateway].add(
                    tuple(sorted((path_from_gateway[i], path_from_gateway[i + 1])))
                )

    return rooted_tree_edges


def convert_edges_to_routes(root, tree_edges, links):
    if not tree_edges:
        return []

    adj = defaultdict(list)
    for u, v in tree_edges:
        adj[u].append(v)
        adj[v].append(u)

    routes = []
    queue = [(root, None)]
    visited = {root}

    head = 0
    while head < len(queue):
        current, parent = queue[head]
        head += 1

        route_entry = {"node": current}

        if parent:
            route_entry["in"] = links[(parent, current)][0]

        out_link_names = set()
        for neighbor in adj[current]:
            if neighbor != parent:
                out_link_names.add(links[(current, neighbor)][0])
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, current))

        if out_link_names:
            route_entry["outs"] = sorted(list(out_link_names))

        if "in" in route_entry or "outs" in route_entry:
            routes.append(route_entry)

    return routes


def make_link(nodes, subnet):
    sorted_nodes = sorted(nodes)

    return f"link({subnet})-" + "-".join(sorted_nodes)


class ScenarioGenerator:
    def __init__(self, meta_config):
        self.meta = self._assert(meta_config)
        self.nodes = self._expand_nodes()
        self.firewalls = self._get_firewalls()
        self.graph = self._build_graph()
        self.links = self._link_nodes()
        self.mc_groups = self._get_multicast_groups()
        self.amt_config = self._parse_amt_config()

    def _assert(self, meta_config):
        assert meta_config["nodes"]
        assert meta_config["multicasts"]
        assert meta_config["links"]
        assert meta_config["applications"]

        return meta_config

    def _expand_nodes(self):
        nodes = set(self.meta["nodes"].get("explicits", []))
        for pattern in self.meta["nodes"].get("patterns", []):
            for i in range(1, pattern["count"] + 1):
                nodes.add(f"{pattern['prefix']}{i}")
        return sorted(list(nodes))

    def _get_firewalls(self):
        return {
            firewall["node"]
            for firewall in self.meta.get("firewalls", [])
            if firewall.get("multicast") is False
        }

    def _build_graph(self):
        G = nx.Graph()
        G.add_nodes_from(self.nodes)
        for link in self.meta.get("links", []):
            nodes = link["nodes"]

            for node in nodes:
                assert node in self.nodes, f"{node} is not defined"

            if link.get("strategy") == "backbone":
                for i in range(len(nodes) - 1):
                    G.add_edge(nodes[i], nodes[i + 1])

            else:
                for u, v in itertools.combinations(nodes, 2):
                    G.add_edge(u, v)

        return G

    def _link_nodes(self):
        links = dict()
        subnet_counter = 0
        for link_info in self.meta.get("links", []):
            nodes_in_link = link_info["nodes"]

            if link_info.get("strategy") == "backbone":
                edges = [
                    (nodes_in_link[j], nodes_in_link[j + 1])
                    for j in range(len(nodes_in_link) - 1)
                ]
                for u, v in edges:
                    subnet = f"10.0.{subnet_counter}.0"
                    link_name = make_link([u, v], subnet)
                    links[(u, v)] = (link_name, subnet)
                    links[(v, u)] = (link_name, subnet)
                    subnet_counter += 1
            else:
                subnet = f"10.0.{subnet_counter}.0"
                link_name = make_link(nodes_in_link, subnet)
                edges = itertools.combinations(nodes_in_link, 2)
                for u, v in edges:
                    links[(u, v)] = (link_name, subnet)
                    links[(v, u)] = (link_name, subnet)
                subnet_counter += 1

        return links

    def _get_multicast_groups(self):
        return {
            group["name"]: group["address"] for group in self.meta.get("multicasts", [])
        }

    def _parse_amt_config(self):
        config = {"relay": [], "sink_map": {}}
        if "amt" not in self.meta:
            return config

        config["relays"] = [r["node"] for r in self.meta["amt"].get("relays", [])]

        for gw_info in self.meta["amt"].get("gateways", []):
            group_name = gw_info["address"]
            gateway_node = gw_info["node"]

            if group_name not in config["sink_map"]:
                config["sink_map"][group_name] = {}

            for sink_node in gw_info["sinks"]:
                config["sink_map"][group_name][sink_node] = (
                    gateway_node,
                    config["relays"],
                )

        return config

    def generate(self):
        output = {"nodes": [name for name in self.nodes]}

        links = []
        processed_link_names = set()
        for u, v in self.graph.edges:
            link_name, subnet = self.links[(u, v)]
            if link_name in processed_link_names:
                continue
            nodes_on_this_link = []
            is_lan = False
            for link_info in self.meta.get("links", []):
                if not link_info.get("strategy") == "backbone":
                    temp_name = make_link(link_info["nodes"], subnet)
                    if temp_name == link_name:
                        nodes_on_this_link = link_info["nodes"]
                        is_lan = True
                        break

            if not is_lan:
                nodes_on_this_link = sorted([u, v])

            link_spec = {
                "name": link_name,
                "subnet": subnet,
                "mask": "255.255.255.0",
                "nodes": nodes_on_this_link,
            }
            links.append(link_spec)
            processed_link_names.add(link_name)

        output["links"] = sorted(links, key=lambda x: x["name"])
        output["multicasts"] = self.meta.get("multicasts", [])
        apps, scenario = self._generate_apps_and_scenario()
        output["applications"] = apps
        output["scenarios"] = scenario
        return output

    def _generate_apps_and_scenario(self):
        base_apps = []
        events = defaultdict(list)

        for app in self.meta["applications"].get("explicits", []):
            base_apps.append(app)
            if app.get("type") == "PacketSink":
                group_name = app["address"]
                events[app["start"]].append(("join", app["node"], group_name))
                events[app["stop"]].append(("leave", app["node"], group_name))

        if "amt" in self.meta:
            for relay_node in self.amt_config["relays"]:
                base_apps.append({"type": "AmtRelay", "node": relay_node})

            for gw_info in self.meta["amt"].get("gateways", []):
                base_apps.append(
                    {
                        "type": "AmtGateway",
                        "node": gw_info["node"],
                        "address": gw_info["address"],
                    }
                )

        scenario_steps = []
        sorted_times = sorted(events.keys())
        active_sinks = defaultdict(set)
        sources = {
            app["address"]: app["node"]
            for app in self.meta["applications"].get("explicits", [])
            if app.get("type") == "OnOff"
        }

        for time in sorted_times:
            for event_type, node, group in events[time]:
                if event_type == "join":
                    active_sinks[group].add(node)
                else:
                    active_sinks[group].discard(node)

            all_routes_for_this_time = []
            for group, sinks in active_sinks.items():
                if not sinks:
                    continue
                source_node = sources.get(group)
                if not source_node:
                    continue

                rooted_tree_edges = find_multicast_tree(
                    self.graph,
                    source_node,
                    sinks,
                    self.firewalls,
                    self.amt_config.get("sink_map", {}).get(group, {}),
                )

                combined_routes = {}
                for root, edges in rooted_tree_edges.items():
                    routes = convert_edges_to_routes(root, edges, self.links)
                    for r in routes:
                        node_name = r["node"]
                        if node_name not in combined_routes:
                            combined_routes[node_name] = r
                        else:
                            new_outs = r.get("outs", [])
                            if new_outs:
                                existing_route = combined_routes[node_name]
                                existing_outs = existing_route.get("outs", [])
                                for out_link in new_outs:
                                    if out_link not in existing_outs:
                                        existing_outs.append(out_link)
                                existing_route["outs"] = sorted(existing_outs)

                if combined_routes:
                    final_routes = sorted(
                        combined_routes.values(), key=lambda x: x["node"]
                    )
                    all_routes_for_this_time.append(
                        {
                            "group": self.mc_groups[group],
                            "source": source_node,
                            "routes": final_routes,
                        }
                    )

            scenario_steps.append(
                {"time": time, "multicast_routes": all_routes_for_this_time}
            )

        return base_apps, scenario_steps


def main(meta_file, out_file):
    with open(meta_file, "r") as f:
        meta_config = yaml.safe_load(f)

    generator = ScenarioGenerator(meta_config)
    scenario_yaml = generator.generate()

    if not out_file:
        out_file = meta_file.replace(".meta.yaml", ".scenario.yaml")

    with open(out_file, "w") as f:
        yaml.dump(scenario_yaml, f, default_flow_style=False, sort_keys=False, indent=2)

    print(f"성공적으로 '{out_file}' 파일을 생성했습니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("meta", help="meta YAML input file")
    parser.add_argument(
        "-o", "--out", help="output scenario YAML file name", default=None
    )
    args = parser.parse_args()

    main(args.meta, args.out)
