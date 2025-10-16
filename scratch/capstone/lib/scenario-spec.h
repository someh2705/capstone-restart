#ifndef SCENARIO_SPEC_H
#define SCENARIO_SPEC_H

#include "yaml-cpp/yaml.h"

#include <ns3/fatal-error.h>
#include <ns3/valgrind.h>

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <variant>
#include <vector>
#include <yaml-cpp/node/node.h>

namespace ns3
{

namespace cpt
{

struct Link
{
    std::string name;
    std::string subnet;
    std::string mask;
    std::vector<std::string> nodes;
};

struct Multicast
{
    std::string name;
    std::string address;
};

struct OnOffApplication
{
    std::string node;
    std::string address;

    std::string type;
    double start;
    double stop;
};

struct PacketSinkApplication
{
    std::string node;
    std::string address;
    std::optional<std::string> gateway;

    std::string type;
    double start;
    double stop;
};

struct AmtRelayApplication
{
    std::string type;
    std::string node;
};

struct AmtGatewayApplication
{
    std::string type;
    std::string node;
    std::string address;
};

struct Route
{
    std::string node;
    std::optional<std::string> in;
    std::optional<std::vector<std::string>> outs;
};

struct MulticastRoute
{
    std::string group;
    std::string source;
    std::vector<Route> routes;
};

struct Scenario
{
    double time;
    std::vector<MulticastRoute> multicastRoutes;
};

using Application = std::
    variant<OnOffApplication, PacketSinkApplication, AmtRelayApplication, AmtGatewayApplication>;

struct ScenarioSpec

{
    std::vector<std::string> nodes;
    std::vector<Link> links;
    std::vector<Multicast> multicasts;
    std::vector<Application> applications;
    std::vector<Scenario> scenarios;
};

template <typename T>
std::unique_ptr<T>
make_parsed_unique(const YAML::Node& node)
{
    auto app = std::make_unique<T>();
    if (!YAML::convert<T>::decode(node, *app))
    {
        std::stringstream ss;
        ss << "YAML node decoding failed for type. Node content: " << node;
        NS_FATAL_ERROR(ss.str());
    }

    return app;
}

inline Application
create_application(const YAML::Node& node)
{
    auto type = node["type"].as<std::string>();

    if (type == "OnOff")
    {
        return node.as<OnOffApplication>();
    }
    else if (type == "PacketSink")
    {
        return node.as<PacketSinkApplication>();
    }
    else if (type == "AmtRelay")
    {
        return node.as<AmtRelayApplication>();
    }
    else if (type == "AmtGateway")
    {
        return node.as<AmtGatewayApplication>();
    }
    else
    {
        NS_FATAL_ERROR("Unknown application type: " << type << ". Node content: " << node);
    }
}

} // namespace cpt
} // namespace ns3

namespace YAML
{

template <>
struct convert<ns3::cpt::OnOffApplication>
{
    static bool decode(const Node& node, ns3::cpt::OnOffApplication& rhs)
    {
        if (!node["start"] || !node["stop"] || !node["node"] || !node["address"])
        {
            return false;
        }

        rhs.type = "OnOff";
        rhs.start = node["start"].as<double>();
        rhs.stop = node["stop"].as<double>();
        rhs.node = node["node"].as<std::string>();
        rhs.address = node["address"].as<std::string>();

        return true;
    }
};

template <>
struct convert<ns3::cpt::PacketSinkApplication>

{
    static bool decode(const Node& node, ns3::cpt::PacketSinkApplication& rhs)
    {
        if (!node["start"] || !node["stop"] || !node["node"] || !node["address"])
        {
            return false;
        }

        rhs.type = "PacketSink";
        rhs.start = node["start"].as<double>();
        rhs.stop = node["stop"].as<double>();
        rhs.node = node["node"].as<std::string>();
        rhs.address = node["address"].as<std::string>();

        if (node["gateway"].IsDefined() && !node["gateway"].IsNull())
        {
            rhs.gateway = node["gateway"].as<std::string>();
        }

        return true;
    }
};

template <>
struct convert<ns3::cpt::AmtRelayApplication>
{
    static bool decode(const Node& node, ns3::cpt::AmtRelayApplication& rhs)
    {
        if (!node["node"])
        {
            return false;
        }

        rhs.type = "AmtRelay";
        rhs.node = node["node"].as<std::string>();

        return true;
    }
};

template <>
struct convert<ns3::cpt::AmtGatewayApplication>
{
    static bool decode(const Node& node, ns3::cpt::AmtGatewayApplication& rhs)
    {
        if (!node["node"] || !node["address"])
        {
            return false;
        }

        rhs.type = "AmtGateway";
        rhs.node = node["node"].as<std::string>();
        rhs.address = node["address"].as<std::string>();

        return true;
    }
};

template <>
struct convert<ns3::cpt::Link>
{
    static bool decode(const Node& node, ns3::cpt::Link& rhs)
    {
        if (!node["name"] || !node["subnet"] || !node["mask"] || !node["nodes"].IsSequence())
        {
            return false;
        }

        rhs.name = node["name"].as<std::string>();
        rhs.subnet = node["subnet"].as<std::string>();
        rhs.mask = node["mask"].as<std::string>();
        rhs.nodes = node["nodes"].as<std::vector<std::string>>();

        return true;
    }
};

template <>
struct convert<ns3::cpt::Multicast>
{
    static bool decode(const Node& node, ns3::cpt::Multicast& rhs)
    {
        if (!node["name"] || !node["address"])
        {
            return false;
        }

        rhs.name = node["name"].as<std::string>();
        rhs.address = node["address"].as<std::string>();

        return true;
    }
};

template <>
struct convert<ns3::cpt::Route>
{
    static bool decode(const Node& node, ns3::cpt::Route& rhs)
    {
        if (!node["node"])
        {
            return false;
        }

        if (!node["in"] && !node["outs"].IsSequence())
        {
            return false;
        }

        rhs.node = node["node"].as<std::string>();

        if (node["in"])
        {
            rhs.in = node["in"].as<std::string>();
        }

        if (node["outs"])
        {
            rhs.outs = node["outs"].as<std::vector<std::string>>();
        }

        return true;
    }
};

template <>
struct convert<ns3::cpt::MulticastRoute>
{
    static bool decode(const Node& node, ns3::cpt::MulticastRoute& rhs)
    {
        if (!node["group"] || !node["source"] || !node["routes"].IsSequence())
        {
            return false;
        }

        rhs.group = node["group"].as<std::string>();
        rhs.source = node["source"].as<std::string>();
        rhs.routes = node["routes"].as<std::vector<ns3::cpt::Route>>();

        return true;
    }
};

template <>
struct convert<ns3::cpt::Scenario>
{
    static bool decode(const Node& node, ns3::cpt::Scenario& rhs)
    {
        if (!node["time"] || !node["multicast_routes"].IsSequence())
        {
            return false;
        }

        rhs.time = node["time"].as<double>();
        rhs.multicastRoutes = node["multicast_routes"].as<std::vector<ns3::cpt::MulticastRoute>>();

        return true;
    }
};

template <>
struct convert<ns3::cpt::ScenarioSpec>
{
    static bool decode(const Node& node, ns3::cpt::ScenarioSpec& rhs)
    {
        if (!node["nodes"].IsSequence())
        {
            return false;
        }
        rhs.nodes = node["nodes"].as<std::vector<std::string>>();

        if (!node["links"].IsSequence())
        {
            return false;
        }
        rhs.links = node["links"].as<std::vector<ns3::cpt::Link>>();

        if (!node["multicasts"].IsSequence())
        {
            return false;
        }
        rhs.multicasts = node["multicasts"].as<std::vector<ns3::cpt::Multicast>>();

        if (!node["applications"].IsSequence())
        {
            return false;
        }

        for (const auto& app_node : node["applications"])
        {
            rhs.applications.push_back(ns3::cpt::create_application(app_node));
        }

        if (!node["scenarios"].IsSequence())
        {
            return false;
        }
        rhs.scenarios = node["scenarios"].as<std::vector<ns3::cpt::Scenario>>();

        return true;
    }
};

} // namespace YAML

#endif
