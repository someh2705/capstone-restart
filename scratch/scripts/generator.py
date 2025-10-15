import yaml
import networkx as nx
from collections import defaultdict
import itertools
import argparse

def find_multicast_tree(graph, source, sinks, firewalls, tunnels, current):
    """
    :param graph: 전체 네트워크 토폴로지
    :param source: 멀티캐스트 소스 노드 이름
    :param sinks: 현재 활성화된 sink 노드 집합
    :param firewalls: 멀티캐스트가 차단된 노드 이름 집합
    :param tunnels: sink와 amt 맵핑 정보
    :return (S, G) 라우팅을 위한 모든 edge 집합
    """

    tree_edges = set()

    multicast_enabled_graph = graph.copy()
    multicast_enabled_graph.remove_nodes_from(firewalls)


    for sink in sinks:
        path = []

        # 일반 멀티캐스트 경로 탐색
        try:
            path = nx.shortest_path(
                multicast_enabled_graph, source=source, target=sink
            )

            for i in range(len(path) - 1):
                tree_edges.add(tuple(sorted((path[i], path[i + 1]))))

        except nx.NetworkXNoPath:
            gateway, start, end = tunnels[sink]
            if current < start or current > end:
                continue

            path = nx.shortest_path(
                multicast_enabled_graph, source=gateway, target=sink
            )

            for i in range(len(path) - 1):
                tree_edges.add(tuple(sorted((path[i], path[i + 1]))))

    return tree_edges

def convert_edges_to_routes(source, tree_edges, links):

    if not tree_edges:
        return []

    adj = defaultdict(list)
    all_nodes = set()
    for u, v in tree_edges:
        adj[u].append(v)
        adj[v].append(u)
        all_nodes.add(u)
        all_nodes.add(v)

    routes = []
    visited = {source}

    for start_node in all_nodes:
        if start_node in visited:
            continue

        queue = [(start_node, None)]
        visited.add(start_node)

        while queue:
            # BFS
            current, previous = queue.pop(0)

            route_entry = {"node": current}
            in_link = links[(previous, current)][0] if previous else None
            out_links = []

            for neighbor in adj[current]:
                if neighbor != previous:
                    link, _ = links[(current, neighbor)]
                    out_links.append(link)
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, current))

            if in_link:
                route_entry["in"] = in_link

            if out_links:
                route_entry["out"] = out_links

            if "in" in route_entry or "out" in route_entry:
                routes.append(route_entry)

    return sorted(routes, key=lambda x: x["node"])

def make_link(node1, node2, subnet):
    start = node1 if node1 <= node2 else node2
    end = node2 if node1 <= node2 else node1

    return f"link({subnet})-{start}-{end}"

class ScenarioGenerator:
    def __init__(self, meta_config):
        self.meta = self._assert(meta_config)
        self.nodes = self._expand_nodes()
        self.firewalls = self._get_firewalls()
        self.graph = self._build_graph()
        self.links = self._link_nodes()
        self.mc_groups = self._get_multicast_groups()

    def _assert(self, meta_config):
        assert meta_config["nodes"]
        assert meta_config["multicast"]
        assert meta_config["links"]
        assert meta_config["applications"]

        return meta_config

    def _expand_nodes(self):
        nodes = set(self.meta["nodes"].get("explicit", []))
        for pattern in self.meta["nodes"].get("patterns", []):
            for i in range(1, pattern["count"] + 1):
                nodes.add(f"{pattern['prefix']}{i}")
        return sorted(list(nodes))

    def _get_firewalls(self):
        return {
            firewall["node"]
            for firewall in self.meta.get("firewall", [])
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

    def _get_multicast_groups(self):
        return {
            group["name"]: group["address"]
            for group in self.meta.get("multicast", [])
        }

    def _link_nodes(self):
        links = dict()
        for i, (u, v) in enumerate(self.graph.edges):
            subnet = f"10.0.{i}.0"
            link = make_link(u, v, subnet)
            links[(u, v)] = (link, subnet)
            links[(v, u)] = (link, subnet)

        return links

    def generate(self):
        output = { "nodes": [{"name": name} for name in self.nodes]}

        links = []
        for i, (u, v) in enumerate(self.graph.edges):
            link, subnet = self.links[(u, v)]
            link_spec = {
                "name": link,
                "subnet": subnet,
                "mask": "255.255.255.0",
                "nodes": [u, v]
            }

            links.append(link_spec)
        output["links"] = sorted(links, key=lambda x: x["name"])

        output["multicast"] = self.meta.get("multicast", [])

        apps, scenario = self._generate_apps_and_scenario()
        output["applications"] = apps
        output["scenario"] = scenario

        return output

    def _generate_apps_and_scenario(self):
        base_apps = []
        events = defaultdict(list)
        tunnel_port = 9000

        tunnels_by_group = defaultdict(dict)

        for app in self.meta["applications"].get("explicit", []):
            app_type = app.get("type")

            if app_type == "Tunnel":
                group_name = app["address"]
                app["port"] = tunnel_port
                events[app["start"]].append(("join", app["relay"], group_name))
                events[app["stop"]].append(("leave", app["relay"], group_name))

                tunnel_port += 1
                base_apps.append(app)

            elif app_type == "PacketSink":
                group_name = app["address"]
                events[app["start"]].append(("join", app["node"], group_name))
                events[app["stop"]].append(("leave", app["node"], group_name))

                if app.get("gateway"):
                    for tunnel_app in self.meta["applications"].get("explicit", []):
                        if tunnel_app.get("type") == "Tunnel" and tunnel_app.get("gateway") == app["gateway"]:
                            tunnels_by_group[group_name][app["node"]]= (tunnel_app["gateway"], tunnel_app.get("start"), tunnel_app.get("stop"))
                            break

                base_apps.append(app)

            elif app_type == "OnOff":
                group_name = app["address"]
                # events[app["start"]].append(("join", app["node"], group_name))
                # events[app["stop"]].append(("leave", app["node"], group_name))

                base_apps.append(app)

        scenario_steps = []
        sorted_times = sorted(events.keys())
        active_sinks = defaultdict(set)

        sources = {}
        for app in self.meta["applications"].get("explicit", []):
            if app.get("type") == "OnOff":
                sources[app["address"]] = app["node"]

        for time in sorted_times:
            for event_type, node, group in events[time]:
                if event_type == "join":
                    active_sinks[group].add(node)
                elif event_type == "leave":
                    active_sinks[group].discard(node)

            all_routes_for_this_time = []

            for group, sinks in active_sinks.items():
                if not sinks:
                    continue

                source_node = sources.get(group)
                if not source_node:
                    continue

                tree_edges = find_multicast_tree(
                    self.graph,
                    source_node,
                    sinks,
                    self.firewalls,
                    tunnels_by_group.get(group, {}),
                    time
                )

                routes = convert_edges_to_routes(source_node, tree_edges, self.links)
                all_routes_for_this_time.append(
                    {
                        "group": self.mc_groups[group],
                        "source": source_node,
                        "routes": routes
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
    parser.add_argument("-o", "--out", help="output scenario YAML file name", default = None)
    args = parser.parse_args()

    main(args.meta, args.out)
