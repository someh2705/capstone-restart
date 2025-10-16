#ifndef SCENARIO_LOADER_H
#define SCENARIO_LOADER_H

#include "scenario-spec.h"

#include <ns3/applications-module.h>
#include <ns3/core-module.h>
#include <ns3/internet-module.h>
#include <ns3/net-device-container.h>
#include <ns3/node-container.h>

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>

namespace ns3
{
namespace cpt
{

class ScenarioLoader
{
  public:
    ScenarioLoader(const ScenarioSpec& spec, const std::string& scenarioFile);

    NodeContainer GetNodes();
    Ptr<Node> GetNode(std::string name);

  private:
    NodeContainer m_nodes;
    std::unordered_map<std::string, Ptr<Node>> m_nodeMap;
    std::unordered_map<std::string, NetDeviceContainer> m_linkMap;
    std::unordered_map<std::string, Ipv4Address> m_multicastMap;
    std::vector<ApplicationContainer> m_installedApps;

    void SetupNodes(const std::vector<std::string>& nodes);
    void SetupLinks(const std::vector<Link>& links, const std::string& scenarioFile);
    void SetupRoutingTables();
    void SetupMulticasts(const std::vector<Multicast>& multicasts);
    void SetupApplications(const std::vector<Application>& applications);
    void SetupScenarios(const std::vector<Scenario>& scenarios);

    void ApplyMulticastRoutes(const Scenario& scenario);
    uint32_t FindInterfaceIndex(Ptr<Node> node, const std::string& name);
};
} // namespace cpt
} // namespace ns3

#endif
