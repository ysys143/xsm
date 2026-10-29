//! Match Python's loopback HTTP dev-relay policy without changing HTTPS trust.
use iroh::RelayMode;
use std::{
    io::Write,
    os::unix::fs::PermissionsExt,
    process::{Command, Stdio},
};
use xsm_net::transport::Config;

#[tokio::test]
async fn configured_relay_candidate_survives_initial_offline_state() {
    let configured = "http://127.0.0.1:9";
    let config = Config {
        relay: Config::relay(Some(configured)).unwrap(),
        ..Config::default()
    };
    let transport = xsm_net::transport::Transport::bind(iroh::SecretKey::generate(), config)
        .await
        .unwrap();
    let address = transport.address();
    let preserved = address
        .relay_urls()
        .any(|url| url.as_str() == "http://127.0.0.1:9/");
    transport.endpoint.close().await;
    assert!(
        preserved,
        "explicit custom relay disappeared before online discovery"
    );
}

#[test]
fn loopback_http_urls_match_python_configuration() {
    for input in [
        "http://localhost:3340",
        "http://127.0.0.1:3340",
        "http://[::1]:3340",
        "http://localhost/relay",
        "HTTP://LOCALHOST:3340",
    ] {
        let mode =
            Config::relay(Some(input)).expect("literal loopback HTTP relay must be accepted");
        assert!(matches!(mode, RelayMode::Custom(_)));
        assert_eq!(mode.relay_map().urls::<Vec<_>>().len(), 1);
    }
}

#[test]
fn non_loopback_and_parser_aliases_remain_rejected() {
    // url::Url normalizes numeric/encoded aliases that Python's hostname
    // allowlist rejects. Accept only the same three literal loopback hosts.
    for input in [
        "http://relay.example.invalid",
        "http://192.168.0.11:3340",
        "http://100.123.30.11:3340",
        "http://0.0.0.0:3340",
        "http://127.0.0.2:3340",
        "http://127.1:3340",
        "http://2130706433:3340",
        "http://0x7f000001:3340",
        "http://0177.0.0.1:3340",
        "http://lo%63alhost:3340",
        "http://localhost.:3340",
        "http://localhost.example.invalid:3340",
        "http://[0:0:0:0:0:0:0:1]:3340",
        "http://[::ffff:127.0.0.1]:3340",
        "http://localhost@relay.example.invalid:3340",
        "http://name:secret@localhost:3340",
        "http://localhost:3340?secret=fixture",
        "http://localhost:3340#fixture",
        "ftp://localhost:3340",
        "http:localhost",
    ] {
        assert_eq!(
            Config::relay(Some(input)).unwrap_err().0,
            "invalid_relay",
            "{input}"
        );
    }
}

#[test]
fn https_and_default_modes_preserve_existing_policy() {
    assert_eq!(Config::relay(None).unwrap(), RelayMode::Default);
    assert_eq!(Config::relay(Some("off")).unwrap(), RelayMode::Disabled);
    assert!(matches!(
        Config::relay(Some("https://relay.example.invalid")).unwrap(),
        RelayMode::Custom(_)
    ));
    for input in [
        "https://name:secret@relay.example.invalid",
        "https://relay.example.invalid?secret=fixture",
        "https://relay.example.invalid#fixture",
    ] {
        assert_eq!(Config::relay(Some(input)).unwrap_err().0, "invalid_relay");
    }
}

#[test]
fn real_native_jsonl_accepts_loopback_http_without_tls_bypass() {
    let root = tempfile::Builder::new()
        .permissions(std::fs::Permissions::from_mode(0o700))
        .tempdir()
        .unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_xsm-net"))
        .args(["serve", "--state-dir"])
        .arg(root.path())
        .args(["--relay", "http://127.0.0.1:9"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(b"{\"op\":\"shutdown\"}\n");
    }
    let output = child.wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "native rejected permitted loopback HTTP relay"
    );
    let events: Vec<serde_json::Value> = output
        .stdout
        .split(|b| *b == b'\n')
        .filter(|line| !line.is_empty())
        .map(|line| serde_json::from_slice(line).unwrap())
        .collect();
    let ready = events
        .iter()
        .find(|event| event["event"] == "ready")
        .unwrap();
    assert_eq!(ready["relay_mode"], "custom");
}
