#include <ns3/command-line.h>
#include <ns3/fatal-error.h>
#include <ns3/icmpv6-header.h>
#include <ns3/internet-stack-helper.h>
#include <ns3/ipv4-address-helper.h>
#include <ns3/ipv4-global-routing-helper.h>
#include <ns3/ipv4-interface-container.h>
#include <ns3/log.h>
#include <ns3/names.h>
#include <ns3/net-device-container.h>
#include <ns3/node-container.h>
#include <ns3/node.h>
#include <ns3/object.h>
#include <ns3/point-to-point-module.h>
#include <ns3/ptr.h>
#include <ns3/string.h>

#include <map>
#include <string>
#include <vector>
using namespace ns3;

int
main(int argc, char* argv[])
{
    bool is_multihop;
    CommandLine cmd;

    cmd.AddValue("is_multihop", "", is_multihop);
    cmd.Parse(argc, argv);

    std::vector<std::string> nodeNames = {// Seoul
                                          "seoul1",
                                          "seoul2",
                                          "seoul3",
                                          "seoul4",
                                          "seoul5",
                                          "seoul6",
                                          "seoul7",
                                          "sink3",
                                          "sink4",
                                          "gateway3",
                                          "relay5",
                                          // Busan
                                          "busan1",
                                          "busan2",
                                          "busan3",
                                          "busan4",
                                          "busan5",
                                          "relay4",
                                          // Jeju
                                          "jeju1",
                                          "jeju2",
                                          "jeju3",
                                          "jeju4",
                                          "jeju5",
                                          "sink5",
                                          "gateway4",
                                          // Osaka
                                          "osaka1",
                                          "osaka2",
                                          "osaka3",
                                          "osaka4",
                                          "osaka5",
                                          "osaka6",
                                          "host1",
                                          "sink1",
                                          "gateway1",
                                          "relay1",
                                          "relay2",
                                          // Fukuoka
                                          "fukuoka1",
                                          "fukuoka2",
                                          "fukuoka3",
                                          "fukuoka4",
                                          "sink2",
                                          "gateway2",
                                          "relay3",
                                          // Sea (해저 케이블 노드)
                                          "sea1",
                                          "sea2",
                                          "sea3",
                                          "sea4",
                                          "sea5",
                                          "sea6",
                                          "sea7",
                                          "sea8",
                                          "sea9"};

    std::map<std::string, Ptr<Node>> nodes;
    NodeContainer allNodes;

    for (const auto& name : nodeNames)
    {
        Ptr<Node> node = CreateObject<Node>();
        nodes[name] = node;
        allNodes.Add(node);
        Names::Add(name, node);
    }

    InternetStackHelper stack;
    stack.Install(allNodes);

    PointToPointHelper p2p;
    p2p.SetChannelAttribute("DataRate", StringValue("1Gbps"));
    p2p.SetChannelAttribute("Delay", StringValue("10ms"));

    Ipv4AddressHelper address;
    address.SetBase("10.1.0.0", "255.255.255.0");

    std::vector<std::pair<std::string, std::string>> linkDefs = {// Seoul
                                                                 {"seoul1", "seoul2"},
                                                                 {"seoul2", "seoul3"},
                                                                 {"seoul3", "seoul4"},
                                                                 {"seoul4", "seoul5"},
                                                                 {"seoul5", "seoul6"},
                                                                 {"seoul6", "seoul7"},
                                                                 {"seoul2", "sink3"},
                                                                 {"seoul1", "sink4"},
                                                                 {"seoul4", "gateway3"},
                                                                 {"seoul7", "relay5"},
                                                                 // Busan
                                                                 {"busan1", "busan2"},
                                                                 {"busan2", "busan3"},
                                                                 {"busan3", "busan4"},
                                                                 {"busan4", "busan5"},
                                                                 {"busan1", "relay4"},
                                                                 // Jeju
                                                                 {"jeju1", "jeju2"},
                                                                 {"jeju2", "jeju3"},
                                                                 {"jeju3", "jeju4"},
                                                                 {"jeju4", "jeju5"},
                                                                 {"jeju2", "sink5"},
                                                                 {"jeju5", "gateway4"},
                                                                 // Osaka
                                                                 {"osaka1", "osaka2"},
                                                                 {"osaka2", "osaka3"},
                                                                 {"osaka3", "osaka4"},
                                                                 {"osaka4", "osaka5"},
                                                                 {"osaka5", "osaka6"},
                                                                 {"osaka6", "host1"},
                                                                 {"osaka3", "sink1"},
                                                                 {"osaka3", "gateway1"},
                                                                 {"osaka5", "relay1"},
                                                                 {"osaka4", "relay2"},
                                                                 // Fukuoka
                                                                 {"fukuoka1", "fukuoka2"},
                                                                 {"fukuoka2", "fukuoka3"},
                                                                 {"fukuoka3", "fukuoka4"},
                                                                 {"fukuoka3", "sink2"},
                                                                 {"fukuoka2", "gateway2"},
                                                                 {"fukuoka4", "relay3"},
                                                                 // Other
                                                                 {"busan3", "sea1"},
                                                                 {"sea1", "sea2"},
                                                                 {"sea2", "sea3"},
                                                                 {"sea3", "jeju4"},
                                                                 {"busan4", "sea4"},
                                                                 {"sea4", "sea5"},
                                                                 {"sea5", "sea6"},
                                                                 {"sea6", "sea7"},
                                                                 {"sea7", "sea8"},
                                                                 {"sea8", "osaka1"},
                                                                 {"osaka1", "sea9"},
                                                                 {"sea9", "fukuoka1"},
                                                                 {"seoul6", "busan5"}};

    for (const auto& link : linkDefs)
    {
        Ptr<Node> nodeA = nodes[link.first];
        Ptr<Node> nodeB = nodes[link.second];

        if (!nodeA || !nodeB)
        {
            NS_FATAL_ERROR("Node not found" << link.first << " or " << link.second);
        }

        NodeContainer linkNodes(nodeA, nodeB);

        NetDeviceContainer devices = p2p.Install(linkNodes);

        Ipv4InterfaceContainer interfaces = address.Assign(devices);
        address.NewNetwork();
    }

    NS_LOG_INFO("Populating routing tables...");
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();
    NS_LOG_INFO("Routing tables populated.");
}
