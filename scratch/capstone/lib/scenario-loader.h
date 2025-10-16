#ifndef SCENARIO_LOADER_H
#define SCENARIO_LOADER_H

#include "scenario-spec.h"

namespace ns3
{
namespace cpt
{

class ScenarioLoader
{
  public:
    ScenarioLoader(const ScenarioSpec& spec);
};
} // namespace cpt
} // namespace ns3

#endif
