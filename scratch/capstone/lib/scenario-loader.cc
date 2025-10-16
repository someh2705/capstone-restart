#include "scenario-loader.h"

#include "lib/scenario-spec.h"
#include "scenario-spec.h"

#include <ns3/application-container.h>
#include <ns3/assert.h>
#include <ns3/boolean.h>
#include <ns3/core-module.h>
#include <ns3/csma-helper.h>
#include <ns3/csma-module.h>
#include <ns3/data-output-interface.h>
#include <ns3/data-rate.h>
#include <ns3/fatal-error.h>
#include <ns3/inet-socket-address.h>
#include <ns3/internet-module.h>
#include <ns3/internet-stack-helper.h>
#include <ns3/ipv4-address-helper.h>
#include <ns3/ipv4-address.h>
#include <ns3/ipv4-global-routing-helper.h>
#include <ns3/ipv4-static-routing-helper.h>
#include <ns3/net-device-container.h>
#include <ns3/network-module.h>
#include <ns3/node-container.h>
#include <ns3/node.h>
#include <ns3/nstime.h>
#include <ns3/object.h>
#include <ns3/on-off-helper.h>
#include <ns3/packet-sink-helper.h>
#include <ns3/simulator.h>
#include <ns3/string.h>
#include <ns3/uinteger.h>

#include <cstdint>
#include <string>
#include <type_traits>
#include <unordered_map>

NS_LOG_COMPONENT_DEFINE("ScenarioLoader");

namespace ns3
{
namespace cpt
{
ScenarioLoader::ScenarioLoader(const ScenarioSpec& spec, const std::string& scenarioFile)
{
    SetupNodes(spec.nodes);
    SetupLinks(spec.links, scenarioFile);
    SetupRoutingTables();
    SetupMulticasts(spec.multicasts);
    SetupApplications(spec.applications);
    SetupScenarios(spec.scenarios);
}

NodeContainer
ScenarioLoader::GetNodes()
{
    return m_nodes;
}

Ptr<Node>
ScenarioLoader::GetNode(std::string name)
{
    return m_nodeMap[name];
}

void
ScenarioLoader::SetupNodes(const std::vector<std::string>& nodes)
{
    for (const auto& name : nodes)
    {
        auto node = CreateObject<Node>();

        m_nodes.Add(node);
        m_nodeMap[name] = node;
        Names::Add(name, node);
    }
}

void
ScenarioLoader::SetupLinks(const std::vector<Link>& links, const std::string& scenarioFile)
{
    CsmaHelper csma;
    csma.SetChannelAttribute("DataRate", StringValue("100Mbps"));
    csma.SetChannelAttribute("Delay", TimeValue(MilliSeconds(1)));

    InternetStackHelper internet;
    internet.Install(GetNodes());

    Ipv4AddressHelper ipv4;

    for (const auto& link : links)
    {
        NodeContainer links;
        for (const auto& name : link.nodes)
        {
            links.Add(GetNode(name));
        }

        NetDeviceContainer devices = csma.Install(links);

        m_linkMap[link.name] = devices;

        if (devices.GetN() > 0)
        {
            Names::Add(link.name, devices.Get(0)->GetChannel());
        }

        for (uint32_t i = 0; i < devices.GetN(); ++i)
        {
            std::string node = Names::FindName(links.Get(i));
            Names::Add(node + "-" + link.name, devices.Get(i));
        }

        ipv4.SetBase(link.subnet.c_str(), link.mask.c_str());
        ipv4.Assign(devices);
    }

    csma.EnablePcapAll(scenarioFile);
}

void
ScenarioLoader::SetupRoutingTables()
{
    for (const auto& [name, node] : m_nodeMap)
    {
        node->GetObject<Ipv4>()->SetAttribute("IpForward", BooleanValue(true));
    }

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();
}

void
ScenarioLoader::SetupMulticasts(const std::vector<Multicast>& multicasts)
{
    for (const auto& multicast : multicasts)
    {
        Ipv4Address address(multicast.address.c_str());
        m_multicastMap[multicast.name] = address;
    }
}

void
ScenarioLoader::SetupApplications(const std::vector<Application>& applications)
{
    for (const auto& application : applications)
    {
        std::visit(
            [this](auto&& app) {
                using T = std::decay_t<decltype(app)>;

                if constexpr (std::is_same_v<T, OnOffApplication>)
                {
                    auto group = m_multicastMap[app.address];
                    OnOffHelper onoff("ns3::UdpSocketFactory",
                                      Address(InetSocketAddress(group, 9000)));

                    onoff.SetConstantRate(DataRate("1KiB/s"));
                    onoff.SetAttribute("PacketSize", UintegerValue(1024));

                    m_installedApps.push_back(onoff.Install(GetNode(app.node)));
                    m_installedApps.back().Start(Seconds(app.start));
                    m_installedApps.back().Stop(Seconds(app.stop));
                }
                else if constexpr (std::is_same_v<T, PacketSinkApplication>)
                {
                    PacketSinkHelper sink("ns3::UdpSocketFactory",
                                          Address(InetSocketAddress(Ipv4Address::GetAny(), 9000)));

                    m_installedApps.push_back(sink.Install(GetNode(app.node)));
                    m_installedApps.back().Start(Seconds(app.start));
                    m_installedApps.back().Stop(Seconds(app.stop));
                }
            },
            application);
    }
}

void
ScenarioLoader::SetupScenarios(const std::vector<Scenario>& scenarios)
{
    for (const auto& scenario : scenarios)
    {
        Simulator::Schedule(Seconds(scenario.time),
                            [this, scenario]() { ApplyMulticastRoutes(scenario); });
    }
}

void
ScenarioLoader::ApplyMulticastRoutes(const Scenario& scenario)
{
    Ipv4StaticRoutingHelper multicast;

    for (const auto& multicastRoutes : scenario.multicastRoutes)
    {
        Ipv4Address group(multicastRoutes.group.c_str());
        Ptr<Node> source = GetNode(multicastRoutes.source);
        Ipv4Address address;

        bool sourceRouteInfoFound = false;
        for (const auto& route : multicastRoutes.routes)
        {
            if (route.node == multicastRoutes.source)
            {
                if (!route.outs || route.outs->empty())
                {
                    NS_FATAL_ERROR("Source node's route must have at least one 'outs' interface.");
                }

                uint32_t index = FindInterfaceIndex(source, route.outs->at(0));
                address = source->GetObject<Ipv4>()->GetAddress(index, 0).GetLocal();
                sourceRouteInfoFound = true;
                break;
            }
        }

        if (!multicastRoutes.routes.empty() && !sourceRouteInfoFound)
        {
            NS_FATAL_ERROR("Could not find route definition for source node "
                           << multicastRoutes.source);
        }

        for (const auto& route : multicastRoutes.routes)
        {
            Ptr<Node> node = GetNode(route.node);
            Ptr<Ipv4> ipv4 = node->GetObject<Ipv4>();
            Ptr<Ipv4StaticRouting> routing = multicast.GetStaticRouting(ipv4);

            if (!route.in && route.outs)
            {
                uint32_t outputInterface = FindInterfaceIndex(node, route.outs->at(0));
                routing->SetDefaultMulticastRoute(outputInterface);
            }

            if (route.in && route.outs)
            {
                uint32_t inputInterface = FindInterfaceIndex(node, *route.in);
                std::vector<uint32_t> outputInterfaces;
                for (const auto& link : *route.outs)
                {
                    outputInterfaces.push_back(FindInterfaceIndex(node, link));
                }

                routing->RemoveMulticastRoute(address, group, inputInterface);
                routing->AddMulticastRoute(address, group, inputInterface, outputInterfaces);
            }
        }
    }
}

uint32_t
ScenarioLoader::FindInterfaceIndex(Ptr<Node> node, const std::string& name)
{
    auto devices = m_linkMap[name];
    Ptr<Ipv4> ipv4 = node->GetObject<Ipv4>();

    for (uint32_t i = 0; i < devices.GetN(); ++i)
    {
        if (devices.Get(i)->GetNode() == node)
        {
            return ipv4->GetInterfaceForDevice(devices.Get(i));
        }
    }

    NS_FATAL_ERROR("FindInterfaceIndex: Node" << Names::FindName(node)
                                              << " not found on link: " << name);
    return -1;
}

} // namespace cpt
} // namespace ns3
