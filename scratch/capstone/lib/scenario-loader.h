#ifndef SCENARIO_LOADER_H
#define SCENARIO_LOADER_H

#include "scenario-spec.h"

#include <ns3/core-module.h>
#include <ns3/internet-module.h>

#include <atomic>
#include <string>
#include <unordered_map>

namespace ns3
{
namespace cpt
{

class ScenarioLoader
{
  public:
    ScenarioLoader(const ScenarioSpec& spec);

  private:
    NodeContainer m_nodes;
    std::unordered_map<std::string, Ptr<Node>> m_nodeMap;

    std::unordered_map<std::string, Ipv4InterfaceContainer> m_linkMap;

    void ApplyMulticastRoutes(const Scenario& scenario);
};
} // namespace cpt
} // namespace ns3

#endif
