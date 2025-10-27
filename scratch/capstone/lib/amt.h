#ifndef AMT_H
#define AMT_H

#include <ns3/application.h>
#include <ns3/applications-module.h>
#include <ns3/core-module.h>
#include <ns3/ipv4-address.h>
#include <ns3/ipv4-header.h>
#include <ns3/socket.h>
#include <ns3/type-id.h>
#include <ns3/udp-header.h>

#include <cstdint>

namespace ns3
{
namespace cpt
{

class RelayApp : public ns3::Application
{
  public:
    static TypeId GetTypeId();

    RelayApp();
    ~RelayApp() override;

    void Setup(Ipv4Address gatewayAddress,
               uint16_t gatewayPort,
               Ipv4Address multicastGroup,
               uint16_t multicastPort);

  protected:
    void DoDispose() override;

  private:
    Ptr<Socket> m_recvSocket;
    Ptr<Socket> m_sendSocket;
    Ipv4Address m_gatewayAddress;
    uint16_t m_gatewayPort;
    Ipv4Address m_multicastGroup;
    uint16_t m_multicastPort;

    void StartApplication() override;
    void StopApplication() override;

    void HandleRead(Ptr<Socket> socket);
};

class GatewayApp : public ns3::Application
{
  public:
    static TypeId GetTypeId();

    GatewayApp();
    ~GatewayApp() override;

    void Setup(uint16_t unicastPort);
    void HandleRead(Ptr<Socket> socket);

  protected:
    void DoDispose() override;

  private:
    Ptr<Socket> m_recvSocket;
    Ptr<Socket> m_sendSocket;
    uint16_t m_unicastPort;

    void StartApplication() override;
    void StopApplication() override;
};

} // namespace cpt
} // namespace ns3

#endif
