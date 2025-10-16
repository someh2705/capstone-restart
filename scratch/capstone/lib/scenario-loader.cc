#include "scenario-loader.h"

#include "lib/scenario-spec.h"

#include <ns3/core-module.h>
#include <ns3/csma-module.h>
#include <ns3/internet-module.h>
#include <ns3/network-module.h>

#include <string>
#include <unordered_map>

namespace ns3
{
namespace cpt
{
ScenarioLoader::ScenarioLoader(const ScenarioSpec& spec)
{
    for (const auto& name : spec.nodes)
    {
        auto node = CreateObject<Node>();

        m_nodes.Add(node);
        m_nodeMap[name] = node;
        Names::Add(name, node);
    }

    CsmaHelper csma;
    csma.SetChannelAttribute("DataRate", StringValue("100Mpbs"));
    csma.SetChannelAttribute("Delay", TimeValue(MilliSeconds(1)));

    InternetStackHelper internet;
    internet.Install(m_nodes);

    Ipv4AddressHelper ipv4;

    for (const auto& link : spec.links)
    {
        NodeContainer links;
        for (const auto& name : link.nodes)
        {
            links.Add(m_nodeMap[name]);
        }

        NetDeviceContainer devices = csma.Install(links);

        ipv4.SetBase(link.subnet.c_str(), link.mask.c_str());
        auto interface = ipv4.Assign(devices);

        m_linkMap[link.name] = interface;
    }

    for (const auto& [name, node] : m_nodeMap)
    {
        node->GetObject<Ipv4>()->SetAttribute("IpForward", BooleanValue(true));
    }

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    for (const auto& scenario : spec.scenarios)
    {
        Simulator::Schedule(Seconds(scenario.time),
                            &ScenarioLoader::ApplyMulticastRoutes,
                            scenario);
    }
}

void
ScenarioLoader::ApplyMulticastRoutes(const Scenario& scenario)
{
    for (const auto& multicastRoutes : scenario.multicastRoutes)
    {
        Ipv4Address multicastGroup(multicastRoutes.group.c_str());
        Ipv4StaticRoutingHelper multicast;
        auto source = m_nodeMap[multicastRoutes.source];
        Ipv4Address address;

        for (const auto& route : multicastRoutes.routes)
        {
            Ptr<Node> node = m_nodeMap[route.node];
            Ptr<Ipv4> ipv4 = node->GetObject<Ipv4>();
            Ptr<Ipv4StaticRouting> routing = node->GetObject<Ipv4StaticRouting>();

            if (route.in->empty())
            {
            }
            else if (route.node ==)
            {
                if (route.node == multicastRoutes.source)
                {
                    NS_ASSERT_MSG(route.outs->size() == 1,
                                  "Source node route must have an 'outs' link.");
                }
            }
            auto node = m_nodeMap[route.node];
            Ptr<Ipv4StaticRouting> routing = node->GetObject<Ipv4StaticRouting>();

            while (routing->GetNRoutes() > 0)
            {
                routing->RemoveRoute(0);
            }
        }
        multicast_routes.routes Ptr<Ipv4StaticRouting> routing;
    }
}

} // namespace cpt
} // namespace ns3
