use crate::{
    Error, Result,
    identity::Identity,
    transport::{MAX_TIMEOUT_MS, Transport, diagnostics, encode, read_frame, write_frame},
};
use iroh::{EndpointAddr, RelayMode};
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
    time::Duration,
};
use tokio::{
    io::{AsyncBufRead, AsyncBufReadExt, AsyncWrite, AsyncWriteExt, BufReader},
    sync::{Semaphore, mpsc, oneshot},
    task::JoinSet,
};

// JSONL has an independent finite bound allowing body plus IPC metadata/base64.
pub const MAX_IPC_LINE: usize = 12 * 1024 * 1024;
type Pending = Arc<Mutex<HashMap<String, oneshot::Sender<Value>>>>;
struct PeerLimits {
    connections: Arc<Semaphore>,
    streams: Arc<Semaphore>,
}
struct PendingRequest {
    pending: Pending,
    key: String,
}
impl Drop for PendingRequest {
    fn drop(&mut self) {
        self.pending.lock().unwrap().remove(&self.key);
    }
}

pub async fn serve<R, W>(
    identity: Identity,
    transport: Transport,
    input: R,
    mut output: W,
) -> Result<()>
where
    R: tokio::io::AsyncRead + Unpin + Send,
    W: AsyncWrite + Unpin + Send + 'static,
{
    let transport = Arc::new(transport);
    let (events, mut receiver) = mpsc::channel::<Value>(32);
    let writer = tokio::spawn(async move {
        while let Some(event) = receiver.recv().await {
            let bytes = serde_json::to_vec(&event).map_err(|_| Error("ipc_write"))?;
            tokio::time::timeout(Duration::from_secs(5), async {
                output
                    .write_all(&bytes)
                    .await
                    .map_err(|_| Error("ipc_write"))?;
                output
                    .write_all(b"\n")
                    .await
                    .map_err(|_| Error("ipc_write"))?;
                output.flush().await.map_err(|_| Error("ipc_write"))
            })
            .await
            .map_err(|_| Error("ipc_write_timeout"))??;
        }
        Ok::<_, Error>(())
    });
    let relay_mode = match transport.config.relay {
        RelayMode::Disabled => "off",
        RelayMode::Custom(_) => "custom",
        _ => "public",
    };
    let relay_online = if relay_mode != "off" {
        tokio::time::timeout(Duration::from_secs(3), transport.endpoint.online())
            .await
            .is_ok()
    } else {
        false
    };
    events.send(json!({"event":"ready", "endpoint_id":identity.id().to_string(), "address":transport.address(),
        "requested_port":transport.config.port, "bound_addresses":transport.endpoint.bound_sockets().iter().map(ToString::to_string).collect::<Vec<_>>(),
        "port_fallback":transport.port_fallback, "relay_mode":relay_mode, "relay_online":relay_online})).await.map_err(|_| Error("ipc_write"))?;
    let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
    let streams = Arc::new(Semaphore::new(32));
    let inbound = tokio::spawn(accept(
        transport.clone(),
        events.clone(),
        pending.clone(),
        Arc::new(Semaphore::new(32)),
    ));
    let mut tasks = JoinSet::new();
    let mut input = BufReader::new(input);
    let result = loop {
        let line = tokio::select! {
            _ = writer_finished(&writer) => break Err(Error("ipc_write")),
            line = read_line(&mut input) => line,
        };
        while tasks.try_join_next().is_some() {}
        let bytes = match line {
            Ok(Some(bytes)) => bytes,
            Ok(None) => break Ok(()),
            Err(e) if e.0 == "ipc_too_large" => {
                let _ = events.send(error(Value::Null, e)).await;
                continue;
            }
            Err(e) => break Err(e),
        };
        let cmd: Value = match serde_json::from_slice(&bytes) {
            Ok(c) => c,
            Err(_) => {
                let _ = events.send(error(Value::Null, Error("invalid_json"))).await;
                continue;
            }
        };
        let id = cmd.get("id").cloned().unwrap_or(Value::Null);
        let response = match cmd.get("op").and_then(Value::as_str) {
            Some("shutdown") => break Ok(()),
            Some("address") => {
                Ok(json!({"event":"result", "id":id, "address":transport.address()}))
            }
            Some("sign") => field(&cmd, "data")
                .and_then(|data| identity.sign(data))
                .map(|sig| json!({"event":"result", "id":id, "signature":sig})),
            Some("verify") => (|| {
                Identity::verify(
                    field(&cmd, "endpoint_id")?,
                    field(&cmd, "data")?,
                    field(&cmd, "signature")?,
                )
            })()
            .map(|valid| json!({"event":"result", "id":id, "valid":valid})),
            Some("respond") => {
                if encode(cmd.get("body").unwrap_or(&Value::Null)).is_err() {
                    Err(Error("frame_too_large"))
                } else if let Some(key) = id.as_str() {
                    match pending.lock().unwrap().remove(key) {
                        Some(tx) => {
                            if tx
                                .send(cmd.get("body").cloned().unwrap_or(Value::Null))
                                .is_err()
                            {
                                Err(Error("unknown_request"))
                            } else {
                                continue;
                            }
                        }
                        None => Err(Error("unknown_request")),
                    }
                } else {
                    Err(Error("invalid_command"))
                }
            }
            Some("request") => {
                let peer: std::result::Result<EndpointAddr, _> =
                    serde_json::from_value(cmd.get("peer").cloned().unwrap_or(Value::Null));
                match (peer, streams.clone().try_acquire_owned()) {
                    (Ok(peer), Ok(permit)) => {
                        let net = transport.clone();
                        let events = events.clone();
                        let body = cmd.get("body").cloned().unwrap_or(Value::Null);
                        let timeout = cmd
                            .get("timeout_ms")
                            .and_then(Value::as_u64)
                            .unwrap_or(30_000);
                        tasks.spawn(async move {
                            let _permit = permit;
                            let event = match net.request(peer, body, timeout).await {
                                Ok((origin, body, route)) => with_route(json!({"event":"response", "id":id, "origin":origin, "body":body}), route),
                                Err(e) => error(id, e),
                            };
                            let _ = events.send(event).await;
                        });
                        continue;
                    }
                    (Err(_), _) => Err(Error("invalid_peer")),
                    (_, Err(_)) => Err(Error("busy")),
                }
            }
            _ => Err(Error("invalid_command")),
        };
        if events
            .send(response.unwrap_or_else(|e| error(id, e)))
            .await
            .is_err()
        {
            break Err(Error("ipc_write"));
        }
    };
    inbound.abort();
    let _ = inbound.await;
    tasks.abort_all();
    while tasks.join_next().await.is_some() {}
    pending.lock().unwrap().clear();
    transport.endpoint.close().await;
    drop(events);
    let mut writer = writer;
    if tokio::time::timeout(Duration::from_secs(2), &mut writer)
        .await
        .is_err()
    {
        writer.abort();
        let _ = writer.await;
    }
    result
}

async fn writer_finished(writer: &tokio::task::JoinHandle<Result<()>>) {
    // No busy loop; stdin may stay open after a controller closes stdout.
    while !writer.is_finished() {
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
}
fn field<'a>(cmd: &'a Value, key: &str) -> Result<&'a str> {
    cmd.get(key)
        .and_then(Value::as_str)
        .ok_or(Error("invalid_command"))
}
fn error(id: Value, e: Error) -> Value {
    json!({"event":"error", "id":id, "code":e.0})
}
fn with_route(mut event: Value, route: Value) -> Value {
    for field in ["path", "remote_address", "relay_url"] {
        if let Some(value) = route.get(field) {
            event[field] = value.clone();
        }
    }
    event["transport"] = route;
    event
}

async fn accept(
    net: Arc<Transport>,
    events: mpsc::Sender<Value>,
    pending: Pending,
    streams: Arc<Semaphore>,
) {
    let counter = Arc::new(AtomicU64::new(1));
    let connections = Arc::new(Semaphore::new(64));
    let peers = Arc::new(Mutex::new(
        HashMap::<String, std::sync::Weak<PeerLimits>>::new(),
    ));
    let mut tasks = JoinSet::new();
    loop {
        tokio::select! {
            incoming = net.endpoint.accept() => {
                let Some(incoming) = incoming else { break; };
                let Ok(permit) = connections.clone().try_acquire_owned() else { incoming.refuse(); continue; };
                let events = events.clone(); let pending = pending.clone(); let streams = streams.clone(); let counter = counter.clone();
                let peers = peers.clone();
                tasks.spawn(async move {
                    let _permit = permit;
                    let Ok(Ok(conn)) = tokio::time::timeout(Duration::from_secs(10), incoming).await else { return; };
                    let origin = conn.remote_id().to_string();
                    let peer = {
                        let mut peers = peers.lock().unwrap();
                        peers.retain(|_, peer| peer.strong_count() != 0);
                        if let Some(peer) = peers.get(&origin).and_then(std::sync::Weak::upgrade) { peer }
                        else {
                            let peer = Arc::new(PeerLimits { connections: Arc::new(Semaphore::new(4)), streams: Arc::new(Semaphore::new(4)) });
                            peers.insert(origin.clone(), Arc::downgrade(&peer)); peer
                        }
                    };
                    let Ok(_peer_connection) = peer.connections.clone().try_acquire_owned() else { conn.close(0x102u32.into(), b"busy"); return; };
                    let mut requests = JoinSet::new();
                    loop {
                        tokio::select! {
                            pair = tokio::time::timeout(Duration::from_secs(if requests.is_empty() { 15 } else { 120 }), conn.accept_bi()) => {
                                let Ok(Ok((mut send, mut recv))) = pair else { break; };
                                let Ok(permit) = streams.clone().try_acquire_owned() else { let _ = send.reset(0x102u32.into()); let _ = recv.stop(0x102u32.into()); continue; };
                                let Ok(peer_permit) = peer.streams.clone().try_acquire_owned() else { let _ = send.reset(0x102u32.into()); let _ = recv.stop(0x102u32.into()); continue; };
                                let events = events.clone(); let pending = pending.clone(); let origin = origin.clone();
                                let connection = conn.clone();
                                let key = format!("in-{}", counter.fetch_add(1, Ordering::Relaxed));
                                requests.spawn(async move {
                                    let _permit = permit;
                                    let _peer_permit = peer_permit;
                                    let request = async {
                                        let body = read_frame(&mut recv).await?;
                                        let route = diagnostics(&connection);
                                        let (tx, rx) = oneshot::channel();
                                        pending.lock().unwrap().insert(key.clone(), tx);
                                        let _pending = PendingRequest { pending: pending.clone(), key: key.clone() };
                                        events.send(with_route(json!({"event":"request", "request_id":key, "origin":origin, "body":body}), route)).await.map_err(|_| Error("ipc_write"))?;
                                        let body = rx.await.map_err(|_| Error("unknown_request"))?;
                                        write_frame(&mut send, &body).await?;
                                        let route = diagnostics(&connection);
                                        events.send(with_route(json!({"event":"path", "direction":"incoming", "request_id":key,
                                            "origin":origin, "phase":"response_written"}), route)).await.map_err(|_| Error("ipc_write"))?;
                                        if send.stopped().await.map_err(|_| Error("stream_failed"))?.is_some() {
                                            let route = diagnostics(&connection);
                                            events.send(with_route(json!({"event":"path", "direction":"incoming", "request_id":key,
                                                "origin":origin, "phase":"response_stopped", "code":"peer_stopped"}), route)).await.map_err(|_| Error("ipc_write"))?;
                                            return Err(Error("peer_stopped"));
                                        }
                                        Ok::<_, Error>(())
                                    };
                                    if !matches!(tokio::time::timeout(Duration::from_millis(MAX_TIMEOUT_MS), request).await, Ok(Ok(()))) {
                                        let _ = send.reset(0x101u32.into()); let _ = recv.stop(0x101u32.into());
                                    }
                                    pending.lock().unwrap().remove(&key);
                                });
                            }
                            Some(_) = requests.join_next(), if !requests.is_empty() => (),
                        }
                    }
                    requests.abort_all(); while requests.join_next().await.is_some() {}
                });
            }
            Some(_) = tasks.join_next(), if !tasks.is_empty() => (),
        }
    }
}

/// Drain an overlong line without allocating it; the following line remains usable.
pub async fn read_line<R: AsyncBufRead + Unpin>(input: &mut R) -> Result<Option<Vec<u8>>> {
    let mut bytes = Vec::new();
    let mut oversized = false;
    loop {
        let available = input.fill_buf().await.map_err(|_| Error("ipc_read"))?;
        if available.is_empty() {
            return if oversized {
                Err(Error("ipc_too_large"))
            } else if bytes.is_empty() {
                Ok(None)
            } else {
                Ok(Some(bytes))
            };
        }
        let end = available.iter().position(|&c| c == b'\n').map(|n| n + 1);
        let n = end.unwrap_or(available.len());
        if bytes.len() + n > MAX_IPC_LINE {
            oversized = true;
        }
        if !oversized {
            bytes.extend_from_slice(&available[..n]);
        }
        input.consume(n);
        if end.is_some() {
            return if oversized {
                Err(Error("ipc_too_large"))
            } else {
                Ok(Some(bytes))
            };
        }
    }
}
