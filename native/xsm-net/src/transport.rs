//! One request/reply per TLS-authenticated QUIC bidirectional stream.
use crate::{Error, Result};
use iroh::{
    Endpoint, EndpointAddr, RelayMode, RelayUrl, SecretKey,
    endpoint::{BindError, BindOpts, RecvStream, SendStream, presets},
};
use serde_json::{Value, json};
use std::{
    net::{Ipv4Addr, Ipv6Addr, SocketAddr},
    time::Duration,
};

pub const ALPN: &[u8] = b"xsm/network/1";
pub const MAX_FRAME: usize = 8 * 1024 * 1024;
pub const MAX_TIMEOUT_MS: u64 = 120_000;

#[derive(Clone)]
pub struct Config {
    pub port: u16,
    pub relay: RelayMode,
    pub direct: Vec<SocketAddr>,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            port: 0,
            relay: RelayMode::Default,
            direct: Vec::new(),
        }
    }
}
impl Config {
    pub fn relay(value: Option<&str>) -> Result<RelayMode> {
        match value {
            None => Ok(RelayMode::Default),
            Some("off") => Ok(RelayMode::Disabled),
            Some(s) => {
                let url: RelayUrl = s.parse().map_err(|_| Error("invalid_relay"))?;
                // Match Python configure's literal loopback HTTP exception.
                // Inspect the original authority: URL parsing normalizes aliases
                // such as 127.1 and percent-encoded hosts that Python rejects.
                let authority = s
                    .split_once("://")
                    .map(|(_, tail)| tail.split(['/', '?', '#']).next().unwrap_or(""));
                let host = authority.and_then(|value| {
                    if value.starts_with('[') {
                        value.find(']').map(|end| &value[..=end])
                    } else {
                        value.split(':').next()
                    }
                });
                let loopback = host.is_some_and(|host| {
                    host.eq_ignore_ascii_case("localhost") || host == "127.0.0.1" || host == "[::1]"
                });
                let allowed_scheme =
                    url.scheme() == "https" || (url.scheme() == "http" && loopback);
                // Do not allow embedded credentials to leak through public address IPC.
                if authority.is_none()
                    || url.host_str().is_none()
                    || !allowed_scheme
                    || s.contains('@')
                    || s.contains('?')
                    || s.contains('#')
                {
                    return Err(Error("invalid_relay"));
                }
                Ok(RelayMode::custom([url]))
            }
        }
    }
}

pub struct Transport {
    pub endpoint: Endpoint,
    pub config: Config,
    pub port_fallback: bool,
}
impl Transport {
    pub async fn bind(secret: SecretKey, config: Config) -> Result<Self> {
        let first = bind_once(secret.clone(), &config, config.port).await;
        let (endpoint, port_fallback) = match first {
            Ok(endpoint) => (endpoint, false),
            Err(BindError::Sockets { source, .. })
                if config.port != 0 && source.kind() == std::io::ErrorKind::AddrInUse =>
            {
                (
                    bind_once(secret, &config, 0)
                        .await
                        .map_err(|_| Error("bind_failed"))?,
                    true,
                )
            }
            Err(_) => return Err(Error("bind_failed")),
        };
        let mut config = config;
        for direct in &mut config.direct {
            if direct.port() == 0 {
                let Some(bound) = endpoint
                    .bound_sockets()
                    .into_iter()
                    .find(|b| b.is_ipv4() == direct.is_ipv4())
                else {
                    endpoint.close().await;
                    return Err(Error("direct_address_unbound_family"));
                };
                direct.set_port(bound.port());
            }
        }
        Ok(Self {
            endpoint,
            config,
            port_fallback,
        })
    }
    pub fn address(&self) -> EndpointAddr {
        let mut address = self.endpoint.addr();
        // The ready deadline may expire before relay selection completes.
        // Retain explicit custom URLs as routing candidates so an invitation
        // can still bootstrap through the configured relay. This says nothing
        // about reachability; relay_online and actual path diagnostics do.
        let no_selected_relay = address.relay_urls().next().is_none();
        if no_selected_relay {
            if let RelayMode::Custom(relays) = &self.config.relay {
                for relay in relays.urls::<Vec<_>>() {
                    address = address.with_relay_url(relay);
                }
            }
        }
        for direct in &self.config.direct {
            address = address.with_ip_addr(*direct);
        }
        // A usable local address is available before iroh's initial interface scan.
        for bound in self.endpoint.bound_sockets() {
            let local = if bound.ip().is_unspecified() {
                SocketAddr::new(
                    if bound.is_ipv4() {
                        Ipv4Addr::LOCALHOST.into()
                    } else {
                        Ipv6Addr::LOCALHOST.into()
                    },
                    bound.port(),
                )
            } else {
                bound
            };
            address = address.with_ip_addr(local);
        }
        address
    }
    pub async fn request(
        &self,
        peer: EndpointAddr,
        body: Value,
        timeout_ms: u64,
    ) -> Result<(String, Value, Value)> {
        let payload = encode(&body)?;
        let request = async {
            let conn = self
                .endpoint
                .connect(peer, ALPN)
                .await
                .map_err(|_| Error("connect_failed"))?;
            let origin = conn.remote_id().to_string();
            let (mut send, mut recv) = conn.open_bi().await.map_err(|_| Error("stream_failed"))?;
            write_bytes(&mut send, &payload).await?;
            let body = read_frame(&mut recv).await?;
            Ok((origin, body, diagnostics(&conn)))
        };
        tokio::time::timeout(
            Duration::from_millis(timeout_ms.clamp(1, MAX_TIMEOUT_MS)),
            request,
        )
        .await
        .map_err(|_| Error("timeout"))?
    }
}
/// Snapshot of actual iroh paths after the handshake/reply, separate from configuration.
pub fn diagnostics(conn: &iroh::endpoint::Connection) -> Value {
    let paths = conn.paths();
    let selected = paths.iter().find(|p| p.is_selected());
    let path = selected
        .as_ref()
        .map(|p| {
            if p.is_ip() {
                "direct"
            } else if p.is_relay() {
                "relay"
            } else {
                "unknown"
            }
        })
        .unwrap_or("unknown");
    let mut result = json!({"path":path, "selected":path,
        "selection_reason":"iroh_path_selection", "fallback_reason": if path == "relay" { Some("direct_path_not_selected") } else { None },
        "paths":paths.iter().map(|p| json!({"kind":if p.is_ip() { "direct" } else if p.is_relay() { "relay" } else { "custom" },
            "selected":p.is_selected(), "remote":p.remote_addr().to_string()})).collect::<Vec<_>>()});
    if let Some(selected) = selected {
        match selected.remote_addr() {
            iroh::TransportAddr::Ip(addr) => {
                result["remote_address"] = json!(addr.to_string());
            }
            iroh::TransportAddr::Relay(url) => {
                result["relay_url"] = json!(url.to_string());
            }
            _ => (),
        }
    }
    result
}
async fn bind_once(
    secret: SecretKey,
    config: &Config,
    port: u16,
) -> std::result::Result<Endpoint, BindError> {
    Endpoint::builder(presets::Minimal)
        .secret_key(secret)
        .alpns(vec![ALPN.to_vec()])
        .proxy_from_env()
        .relay_mode(config.relay.clone())
        .clear_ip_transports()
        .bind_addr(SocketAddr::from((Ipv4Addr::UNSPECIFIED, port)))
        .expect("valid IPv4")
        .bind_addr_with_opts(
            SocketAddr::from((Ipv6Addr::UNSPECIFIED, port)),
            BindOpts::default().set_is_required(false),
        )
        .expect("valid IPv6")
        .bind()
        .await
}
pub fn encode(body: &Value) -> Result<Vec<u8>> {
    let bytes = serde_json::to_vec(body).map_err(|_| Error("invalid_json"))?;
    if bytes.len() > MAX_FRAME {
        return Err(Error("frame_too_large"));
    }
    Ok(bytes)
}
pub async fn write_frame(send: &mut SendStream, body: &Value) -> Result<()> {
    write_bytes(send, &encode(body)?).await
}
pub async fn write_bytes(send: &mut SendStream, bytes: &[u8]) -> Result<()> {
    if bytes.len() > MAX_FRAME {
        return Err(Error("frame_too_large"));
    }
    send.write_all(&(bytes.len() as u32).to_be_bytes())
        .await
        .map_err(|_| Error("stream_failed"))?;
    send.write_all(bytes)
        .await
        .map_err(|_| Error("stream_failed"))?;
    send.finish().map_err(|_| Error("stream_failed"))?;
    Ok(())
}
pub async fn read_frame(recv: &mut RecvStream) -> Result<Value> {
    let mut header = [0u8; 4];
    recv.read_exact(&mut header)
        .await
        .map_err(|_| Error("invalid_frame"))?;
    let len = u32::from_be_bytes(header) as usize;
    if len > MAX_FRAME {
        let _ = recv.stop(0x101u32.into());
        return Err(Error("frame_too_large"));
    }
    let mut bytes = vec![0; len];
    recv.read_exact(&mut bytes)
        .await
        .map_err(|_| Error("invalid_frame"))?;
    // FIN is part of the frame. A second frame or trailing bytes is invalid.
    if recv
        .read(&mut [0u8; 1])
        .await
        .map_err(|_| Error("invalid_frame"))?
        .is_some()
    {
        return Err(Error("invalid_frame"));
    }
    serde_json::from_slice(&bytes).map_err(|_| Error("invalid_json"))
}
