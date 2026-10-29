//! Real subprocess IPC and encrypted iroh streams; no Python broker or TCP surrogate.
use base64::{Engine, engine::general_purpose::STANDARD};
use iroh::{Endpoint, EndpointAddr, RelayMode, endpoint::presets};
use serde_json::{Value, json};
use std::{
    net::{Ipv4Addr, SocketAddr, UdpSocket},
    os::unix::fs::{PermissionsExt, symlink},
    path::Path,
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
};
use xsm_net::{
    identity::Identity,
    transport::{ALPN, Config, MAX_FRAME, read_frame},
};

struct Node {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    ready: Value,
    stderr: tokio::task::JoinHandle<Vec<u8>>,
    paths: Vec<Value>,
}
impl Node {
    async fn start(root: &Path, args: &[&str]) -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_xsm-net"))
            .arg("serve")
            .arg("--state-dir")
            .arg(root)
            .args(args)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .unwrap();
        let input = child.stdin.take().unwrap();
        let output = BufReader::new(child.stdout.take().unwrap());
        let mut err = child.stderr.take().unwrap();
        let stderr = tokio::spawn(async move {
            let mut bytes = Vec::new();
            err.read_to_end(&mut bytes).await.unwrap();
            bytes
        });
        let mut node = Self {
            child,
            input,
            output,
            ready: Value::Null,
            stderr,
            paths: Vec::new(),
        };
        node.ready = node.recv().await;
        assert_eq!(node.ready["event"], "ready");
        node
    }
    async fn send(&mut self, cmd: Value) {
        self.input
            .write_all(&serde_json::to_vec(&cmd).unwrap())
            .await
            .unwrap();
        self.input.write_all(b"\n").await.unwrap();
        self.input.flush().await.unwrap();
    }
    async fn recv(&mut self) -> Value {
        loop {
            let event = self.raw_recv().await;
            if event["event"] == "path" {
                self.paths.push(event);
            } else {
                return event;
            }
        }
    }
    async fn path(&mut self) -> Value {
        if let Some(event) = self.paths.pop() {
            return event;
        }
        let event = self.raw_recv().await;
        assert_eq!(event["event"], "path");
        event
    }
    async fn raw_recv(&mut self) -> Value {
        let mut line = String::new();
        let n = tokio::time::timeout(Duration::from_secs(15), self.output.read_line(&mut line))
            .await
            .expect("IPC timeout")
            .unwrap();
        assert!(n > 0, "sidecar closed stdout");
        serde_json::from_str(&line).expect("stdout is JSONL only")
    }
    fn address(&self) -> Value {
        self.ready["address"].clone()
    }
    async fn stop(mut self) {
        self.send(json!({"op":"shutdown"})).await;
        let status = tokio::time::timeout(Duration::from_secs(8), self.child.wait())
            .await
            .unwrap()
            .unwrap();
        assert!(status.success());
        assert!(
            self.stderr.await.unwrap().is_empty(),
            "normal operation must not log data"
        );
    }
}
fn temporary() -> tempfile::TempDir {
    tempfile::Builder::new()
        .permissions(std::fs::Permissions::from_mode(0o700))
        .tempdir()
        .unwrap()
}
async fn raw_endpoint() -> Endpoint {
    Endpoint::builder(presets::Minimal)
        .relay_mode(RelayMode::Disabled)
        .alpns(vec![ALPN.to_vec()])
        .bind()
        .await
        .unwrap()
}
fn local_address(endpoint: &Endpoint) -> EndpointAddr {
    let port = endpoint
        .bound_sockets()
        .into_iter()
        .find(SocketAddr::is_ipv4)
        .unwrap()
        .port();
    EndpointAddr::new(endpoint.id()).with_ip_addr(SocketAddr::from((Ipv4Addr::LOCALHOST, port)))
}

#[tokio::test]
async fn two_endpoints_actual_stream_request_reply_tls_origin_and_reverse() {
    let a_dir = temporary();
    let b_dir = temporary();
    let mut a = Node::start(a_dir.path(), &["--relay", "off"]).await;
    let mut b = Node::start(b_dir.path(), &["--relay", "off"]).await;
    a.send(json!({"id":"ab", "op":"request", "peer":b.address(), "body":{"origin":"forged", "question":"안녕"}})).await;
    let request = b.recv().await;
    assert_eq!(request["event"], "request");
    assert_eq!(request["origin"], a.ready["endpoint_id"]);
    assert_ne!(request["origin"], request["body"]["origin"]);
    b.send(json!({"op":"respond", "id":request["request_id"], "body":{"origin":"forged-reply", "answer":"네"}})).await;
    let reply = a.recv().await;
    assert_eq!(reply["event"], "response");
    assert_eq!(reply["id"], "ab");
    assert_eq!(reply["origin"], b.ready["endpoint_id"]);
    assert_eq!(reply["body"]["answer"], "네");
    assert_eq!(reply["transport"]["selected"], "direct");
    assert_eq!(request["transport"]["selected"], "direct");
    assert_eq!(reply["path"], "direct");
    assert!(reply.get("relay_url").is_none());
    assert!(
        reply["remote_address"]
            .as_str()
            .unwrap()
            .parse::<SocketAddr>()
            .is_ok()
    );
    let received_path = b.path().await;
    assert_eq!(received_path["path"], "direct");
    assert_eq!(received_path["request_id"], request["request_id"]);
    b.send(json!({"id":7, "op":"request", "peer":a.address(), "body":[1,2,3]}))
        .await;
    let request = a.recv().await;
    assert_eq!(request["origin"], b.ready["endpoint_id"]);
    a.send(json!({"op":"respond", "id":request["request_id"], "body":true}))
        .await;
    let reply = b.recv().await;
    assert_eq!(reply["body"], true);
    assert_eq!(reply["id"], 7);
    assert_eq!(reply["origin"], a.ready["endpoint_id"]);
    a.stop().await;
    b.stop().await;
}

#[tokio::test]
async fn sign_verify_rejects_forgery_and_restart_keeps_private_key() {
    let root = temporary();
    let other = temporary();
    let mut a = Node::start(root.path(), &["--relay", "off"]).await;
    let mut b = Node::start(other.path(), &["--relay", "off"]).await;
    let id = a.ready["endpoint_id"].clone();
    let data = STANDARD.encode(b"network membership");
    a.send(json!({"op":"sign", "id":1, "data":data})).await;
    let sig = a.recv().await["signature"].clone();
    for (key, content, signature, expected) in [
        (id.clone(), data.clone(), sig.clone(), true),
        (id.clone(), STANDARD.encode(b"tampered"), sig.clone(), false),
        (
            b.ready["endpoint_id"].clone(),
            data.clone(),
            sig.clone(),
            false,
        ),
        (id.clone(), data.clone(), json!("00".repeat(64)), false),
        (id.clone(), data.clone(), json!("not-hex"), false),
    ] {
        b.send(json!({"op":"verify", "id":2, "endpoint_id":key, "data":content, "signature":signature})).await;
        assert_eq!(b.recv().await["valid"], expected);
    }
    assert_eq!(
        std::fs::metadata(root.path().join("node.secret"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o600
    );
    a.stop().await;
    let mut restarted = Node::start(root.path(), &["--relay", "off"]).await;
    assert_eq!(restarted.ready["endpoint_id"], id);
    restarted
        .send(json!({"op":"sign", "id":3, "data":data}))
        .await;
    assert_eq!(restarted.recv().await["signature"], sig);
    restarted.stop().await;
    b.stop().await;
}

#[tokio::test]
async fn occupied_udp_port_falls_back_and_actual_bound_port_works() {
    let held = UdpSocket::bind("0.0.0.0:0").unwrap();
    let requested = held.local_addr().unwrap().port().to_string();
    let root = temporary();
    let peer_root = temporary();
    let mut node = Node::start(
        root.path(),
        &[
            "--relay",
            "off",
            "--port",
            &requested,
            "--direct-address",
            "100.64.0.7:0",
        ],
    )
    .await;
    assert_eq!(
        node.ready["requested_port"],
        requested.parse::<u16>().unwrap()
    );
    assert_eq!(node.ready["port_fallback"], true);
    for address in node.ready["bound_addresses"].as_array().unwrap() {
        assert_ne!(
            address
                .as_str()
                .unwrap()
                .parse::<SocketAddr>()
                .unwrap()
                .port(),
            held.local_addr().unwrap().port()
        );
    }
    let fallback: EndpointAddr = serde_json::from_value(node.address()).unwrap();
    let extra = fallback
        .ip_addrs()
        .find(|a| a.ip().to_string() == "100.64.0.7")
        .unwrap();
    assert_ne!(extra.port(), 0);
    assert!(
        node.ready["bound_addresses"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| a.as_str().unwrap().parse::<SocketAddr>().unwrap())
            .any(|bound| bound.is_ipv4() && bound.port() == extra.port())
    );
    let mut peer = Node::start(peer_root.path(), &["--relay", "off"]).await;
    peer.send(json!({"op":"request", "id":"fallback", "peer":node.address(), "body":"ping"}))
        .await;
    let req = node.recv().await;
    node.send(json!({"op":"respond", "id":req["request_id"], "body":"pong"}))
        .await;
    assert_eq!(peer.recv().await["body"], "pong");
    node.stop().await;
    peer.stop().await;
}

#[tokio::test]
async fn direct_address_and_relay_modes_use_real_configuration() {
    assert_eq!(Config::relay(None).unwrap(), RelayMode::Default);
    assert_eq!(Config::relay(Some("off")).unwrap(), RelayMode::Disabled);
    let relay = Config::relay(Some("https://relay.example.invalid")).unwrap();
    assert!(matches!(relay, RelayMode::Custom(_)));
    assert_eq!(relay.relay_map().urls::<Vec<_>>().len(), 1);
    for invalid in [
        "garbage",
        "http://relay.example.invalid",
        "https://name:secret@relay.example.invalid",
        "https://relay.example.invalid?secret=foo",
    ] {
        assert!(Config::relay(Some(invalid)).is_err());
    }
    let root = temporary();
    let mut node = Node::start(
        root.path(),
        &["--relay", "off", "--direct-address", "100.64.0.7:0"],
    )
    .await;
    assert_eq!(node.ready["relay_mode"], "off");
    let address: EndpointAddr = serde_json::from_value(node.address()).unwrap();
    let bound = node.ready["bound_addresses"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap().parse::<SocketAddr>().unwrap())
        .find(SocketAddr::is_ipv4)
        .unwrap();
    let expected = SocketAddr::new("100.64.0.7".parse().unwrap(), bound.port());
    assert!(address.ip_addrs().any(|a| *a == expected));
    assert_eq!(address.relay_urls().count(), 0);
    node.send(json!({"op":"address", "id":"address"})).await;
    let live: EndpointAddr = serde_json::from_value(node.recv().await["address"].clone()).unwrap();
    assert_eq!(live.id, address.id);
    assert!(live.ip_addrs().any(|a| *a == expected));
    node.stop().await;
}

#[tokio::test]
async fn oversized_remote_frame_is_rejected_before_payload_and_service_survives() {
    let root = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    let attacker = raw_endpoint().await;
    let conn = attacker
        .connect(
            serde_json::from_value::<EndpointAddr>(node.address()).unwrap(),
            ALPN,
        )
        .await
        .unwrap();
    let (mut send, mut recv) = conn.open_bi().await.unwrap();
    send.write_all(&((MAX_FRAME + 1) as u32).to_be_bytes())
        .await
        .unwrap();
    // Deliberately do not send the body or FIN: reject from the declared size.
    let rejected = tokio::time::timeout(Duration::from_secs(3), recv.read_to_end(64))
        .await
        .unwrap();
    assert!(rejected.is_err());
    node.send(json!({"id":"alive", "op":"address"})).await;
    assert_eq!(node.recv().await["id"], "alive");
    attacker.close().await;
    node.stop().await;
}

#[tokio::test]
async fn oversized_local_request_returns_stable_error_without_connecting() {
    let root = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    node.send(
        json!({"id":"large", "op":"request", "peer":node.address(), "body":"x".repeat(MAX_FRAME)}),
    )
    .await;
    let error = node.recv().await;
    assert_eq!(error["event"], "error");
    assert_eq!(error["code"], "frame_too_large");
    node.stop().await;
}

#[tokio::test]
async fn exact_eight_mib_frame_roundtrip() {
    let root = temporary();
    let other = temporary();
    let mut a = Node::start(root.path(), &["--relay", "off"]).await;
    let mut b = Node::start(other.path(), &["--relay", "off"]).await;
    let body = Value::String("a".repeat(MAX_FRAME - 2)); // two JSON quotes
    a.send(json!({"id":"boundary", "op":"request", "peer":b.address(), "body":body}))
        .await;
    let request = b.recv().await;
    assert_eq!(request["body"], body);
    b.send(json!({"op":"respond", "id":request["request_id"], "body":body}))
        .await;
    let reply = a.recv().await;
    assert_eq!(reply["body"], body);
    a.stop().await;
    b.stop().await;
}

#[tokio::test]
async fn partial_jsonl_survives_concurrent_request_completion() {
    let root = temporary();
    let other = temporary();
    let mut a = Node::start(root.path(), &["--relay", "off"]).await;
    let mut b = Node::start(other.path(), &["--relay", "off"]).await;
    a.send(json!({"op":"request", "id":"one", "peer":b.address(), "body":"request"}))
        .await;
    let request = b.recv().await;
    a.input
        .write_all(b"{\"op\":\"sign\",\"id\":\"split\",")
        .await
        .unwrap();
    a.input.flush().await.unwrap();
    b.send(json!({"op":"respond", "id":request["request_id"], "body":"done"}))
        .await;
    assert_eq!(a.recv().await["id"], "one");
    tokio::time::sleep(Duration::from_millis(75)).await;
    a.input.write_all(b"\"data\":\"YWJj\"}\n").await.unwrap();
    a.input.flush().await.unwrap();
    let signed = a.recv().await;
    assert_eq!(signed["id"], "split");
    assert!(signed["signature"].is_string());
    a.stop().await;
    b.stop().await;
}

#[tokio::test]
async fn request_timeout_and_unknown_response_are_explicit() {
    let root = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    let unresponsive = raw_endpoint().await;
    node.send(json!({"op":"request", "id":"timeout", "peer":local_address(&unresponsive), "body":null, "timeout_ms":100})).await;
    let error = node.recv().await;
    assert_eq!(error["code"], "timeout");
    node.send(json!({"op":"respond", "id":"missing", "body":"ignored"}))
        .await;
    assert_eq!(node.recv().await["code"], "unknown_request");
    node.send(json!({"op":"sign", "id":"bad", "data":"%%%"}))
        .await;
    assert_eq!(node.recv().await["code"], "invalid_base64");
    node.send(json!({"op":"request", "id":10, "peer":{}, "body":null}))
        .await;
    assert_eq!(node.recv().await["code"], "invalid_peer");
    unresponsive.close().await;
    node.stop().await;
}

#[test]
fn key_storage_refuses_lock_symlink_loose_permissions_and_corruption() {
    let root = temporary();
    let identity = Identity::load(root.path()).unwrap();
    assert_eq!(Identity::load(root.path()).err().unwrap().0, "state_locked");
    let id = identity.id();
    drop(identity);
    assert_eq!(Identity::load(root.path()).unwrap().id(), id);
    let path = root.path().join("node.secret");
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap();
    assert_eq!(
        Identity::load(root.path()).err().unwrap().0,
        "state_permissions"
    );
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
    std::fs::write(&path, b"truncated").unwrap();
    assert_eq!(
        Identity::load(root.path()).err().unwrap().0,
        "invalid_secret"
    );
    let other = temporary();
    symlink(&path, other.path().join("node.secret")).unwrap();
    assert!(Identity::load(other.path()).is_err());
}

#[tokio::test]
async fn malformed_frame_and_trailing_data_never_reach_ipc() {
    let root = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    let attacker = raw_endpoint().await;
    let conn = attacker
        .connect(
            serde_json::from_value::<EndpointAddr>(node.address()).unwrap(),
            ALPN,
        )
        .await
        .unwrap();
    for bytes in [
        vec![0, 0, 0, 1, b'{'],
        vec![0, 0, 0, 2, b'{', b'}', b'x'],
        vec![0, 0, 0, 5, b'{'],
    ] {
        let (mut send, mut recv) = conn.open_bi().await.unwrap();
        send.write_all(&bytes).await.unwrap();
        send.finish().unwrap();
        assert!(
            tokio::time::timeout(Duration::from_secs(3), recv.read_to_end(64))
                .await
                .unwrap()
                .is_err()
        );
    }
    node.send(json!({"op":"address", "id":"alive"})).await;
    assert_eq!(node.recv().await["id"], "alive");
    attacker.close().await;
    node.stop().await;
}

#[tokio::test]
async fn expected_endpoint_key_is_required_with_live_server_control() {
    let server = raw_endpoint().await;
    let client = raw_endpoint().await;
    let serving = server.clone();
    let accepted = tokio::spawn(async move {
        let mut tasks = tokio::task::JoinSet::new();
        while let Some(incoming) = serving.accept().await {
            tasks.spawn(async move {
                if let Ok(conn) = incoming.await {
                    conn.closed().await;
                }
            });
        }
    });
    let valid = tokio::time::timeout(
        Duration::from_secs(3),
        client.connect(local_address(&server), ALPN),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!(valid.remote_id(), server.id());
    let mut wrong = local_address(&server);
    wrong.id = iroh::SecretKey::generate().public();
    let result =
        tokio::time::timeout(Duration::from_millis(500), client.connect(wrong, ALPN)).await;
    assert!(!matches!(result, Ok(Ok(_))));
    client.close().await;
    server.close().await;
    accepted.abort();
    let _ = accepted.await;
}

#[tokio::test]
async fn oversized_remote_response_is_rejected() {
    let root = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    let peer = raw_endpoint().await;
    node.send(json!({"op":"request", "id":"bad-reply", "peer":local_address(&peer), "body":"hi"}))
        .await;
    let conn = peer.accept().await.unwrap().await.unwrap();
    let (mut send, mut recv) = conn.accept_bi().await.unwrap();
    assert_eq!(read_frame(&mut recv).await.unwrap(), "hi");
    send.write_all(&((MAX_FRAME + 1) as u32).to_be_bytes())
        .await
        .unwrap();
    send.finish().unwrap();
    assert_eq!(node.recv().await["code"], "frame_too_large");
    peer.close().await;
    node.stop().await;
}

#[tokio::test]
async fn ipc_overlong_line_is_drained_then_valid_line_works() {
    let data = [
        vec![b'x'; xsm_net::ipc::MAX_IPC_LINE + 1],
        b"\n{}\n".to_vec(),
    ]
    .concat();
    let mut reader = BufReader::new(data.as_slice());
    assert_eq!(
        xsm_net::ipc::read_line(&mut reader).await.err().unwrap().0,
        "ipc_too_large"
    );
    assert_eq!(
        xsm_net::ipc::read_line(&mut reader).await.unwrap().unwrap(),
        b"{}\n"
    );
}

#[tokio::test]
async fn unread_stdout_does_not_prevent_shutdown() {
    let root = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    // The large id fills the OS pipe; leave stdout unread after ready.
    node.send(json!({"op":"address", "id":"x".repeat(128*1024)}))
        .await;
    node.send(json!({"op":"shutdown"})).await;
    let status = tokio::time::timeout(Duration::from_secs(7), node.child.wait())
        .await
        .expect("shutdown must not wait on blocked stdout")
        .unwrap();
    assert!(status.success());
    assert!(node.stderr.await.unwrap().is_empty());
}

#[tokio::test]
async fn inbound_stalled_streams_do_not_consume_outbound_budget() {
    let root = temporary();
    let other = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    let mut peer = Node::start(other.path(), &["--relay", "off"]).await;
    let attacker = raw_endpoint().await;
    let conn = attacker
        .connect(
            serde_json::from_value::<EndpointAddr>(node.address()).unwrap(),
            ALPN,
        )
        .await
        .unwrap();
    let mut streams = Vec::new();
    for _ in 0..32 {
        let (mut send, recv) = conn.open_bi().await.unwrap();
        let _ = send.write_all(&[0, 0]).await; // incomplete frame header
        streams.push((send, recv));
    }
    node.send(json!({"op":"request", "id":"outbound", "peer":peer.address(), "body":"healthy"}))
        .await;
    let request = peer.recv().await;
    peer.send(json!({"op":"respond", "id":request["request_id"], "body":"yes"}))
        .await;
    assert_eq!(node.recv().await["body"], "yes");
    attacker.close().await;
    node.stop().await;
    peer.stop().await;
}

#[tokio::test]
async fn per_device_stream_limit_is_shared_across_connections() {
    let root = temporary();
    let mut node = Node::start(root.path(), &["--relay", "off"]).await;
    let attacker = raw_endpoint().await;
    let address: EndpointAddr = serde_json::from_value(node.address()).unwrap();
    let first = attacker.connect(address.clone(), ALPN).await.unwrap();
    let mut stalled = Vec::new();
    for _ in 0..4 {
        let (mut send, recv) = first.open_bi().await.unwrap();
        send.write_all(&[0, 0]).await.unwrap();
        stalled.push((send, recv));
    }
    tokio::time::sleep(Duration::from_millis(75)).await;
    let second = attacker.connect(address, ALPN).await.unwrap();
    let (mut send, mut recv) = second.open_bi().await.unwrap();
    send.write_all(&[0, 0]).await.unwrap();
    assert!(
        tokio::time::timeout(Duration::from_secs(3), recv.read_to_end(64))
            .await
            .expect("same-device fifth stream must be rejected")
            .is_err()
    );
    node.send(json!({"op":"address", "id":"alive"})).await;
    assert_eq!(node.recv().await["id"], "alive");
    attacker.close().await;
    node.stop().await;
}

/// Explicit internet probe: a relay-only endpoint removes direct UDP as an option.
#[tokio::test]
#[ignore = "requires public relay connectivity; run explicitly with --ignored"]
async fn live_public_and_custom_relay_encrypted_streams() {
    for args in [
        vec![],
        vec!["--relay", "https://aps1-1.relay.n0.iroh.link."],
    ] {
        let root = temporary();
        let mut node = Node::start(root.path(), &args).await;
        let expected = if args.is_empty() { "public" } else { "custom" };
        assert_eq!(node.ready["relay_mode"], expected);
        // ready is deliberately bounded even when relay startup needs longer.
        let mut advertised: EndpointAddr = serde_json::from_value(node.address()).unwrap();
        for attempt in 0..40 {
            if advertised.relay_urls().next().is_some() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
            node.send(json!({"op":"address", "id":attempt})).await;
            advertised = serde_json::from_value(node.recv().await["address"].clone()).unwrap();
        }
        assert!(
            advertised.relay_urls().next().is_some(),
            "no home relay after startup deadline"
        );
        let relay = if args.is_empty() {
            RelayMode::Default
        } else {
            Config::relay(Some(args[1])).unwrap()
        };
        let peer = Endpoint::builder(presets::Minimal)
            .clear_ip_transports()
            .proxy_from_env()
            .relay_mode(relay)
            .alpns(vec![ALPN.to_vec()])
            .bind()
            .await
            .unwrap();
        tokio::time::timeout(Duration::from_secs(15), peer.online())
            .await
            .expect("public relay online");
        let mut address = advertised;
        address.addrs.retain(|a| a.is_relay());
        assert!(!address.addrs.is_empty());
        let conn = tokio::time::timeout(Duration::from_secs(15), peer.connect(address, ALPN))
            .await
            .unwrap()
            .unwrap();
        let (mut send, mut recv) = conn.open_bi().await.unwrap();
        xsm_net::transport::write_frame(&mut send, &json!({"probe":expected}))
            .await
            .unwrap();
        let request = node.recv().await;
        assert_eq!(request["origin"], peer.id().to_string());
        assert_eq!(request["transport"]["selected"], "relay");
        assert_eq!(request["path"], "relay");
        assert!(request.get("remote_address").is_none());
        assert!(
            request["relay_url"]
                .as_str()
                .unwrap()
                .starts_with("https://")
        );
        node.send(json!({"op":"respond", "id":request["request_id"], "body":{"reply":expected}}))
            .await;
        assert_eq!(read_frame(&mut recv).await.unwrap()["reply"], expected);
        assert_eq!(xsm_net::transport::diagnostics(&conn)["selected"], "relay");
        println!("{expected}: authenticated QUIC stream request/reply selected relay");
        peer.close().await;
        node.stop().await;
    }
}
