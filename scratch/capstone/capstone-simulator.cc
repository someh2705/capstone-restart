#include "lib/scenario-spec.h"

#include "ns3/core-module.h"
#include <ns3/command-line.h>

#include <fstream>
#include <string>
#include <yaml-cpp/node/node.h>
#include <yaml-cpp/node/parse.h>
#include <yaml-cpp/yaml.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("CapstoneSimulator");

int
main(int argc, char* argv[])
{
    std::string scenarioFile;
    CommandLine cmd;

    cmd.AddValue("scenarioFile", "Path to the scenario YAML file", scenarioFile);
    cmd.Parse(argc, argv);

    NS_LOG_INFO("simulate with scenarioFile(" << scenarioFile << ").");

    if (scenarioFile.empty())
    {
        NS_LOG_ERROR("Please provide a scenario file using --scenarioFile");
        return 1;
    }

    YAML::Node node = YAML::LoadFile(scenarioFile);
    auto spec = node.as<cpt::ScenarioSpec>();

    NS_LOG_INFO("success parse");

    return 0;
}
