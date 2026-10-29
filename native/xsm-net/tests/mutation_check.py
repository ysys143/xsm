"""Temporarily reintroduce defects; all checks run the actual Rust tests.

Run from native/xsm-net: python3 tests/mutation_check.py
No xsm/Python broker imports, user state, or external relay services are involved.
Original source bytes are restored after each check, including failure.
"""
from pathlib import Path
import subprocess

CASES = [
    ("TLS origin", "src/ipc.rs", 'let origin = conn.remote_id().to_string();',
     'let origin = "forged".to_owned();', "two_endpoints_actual_stream_request_reply_tls_origin_and_reverse"),
    ("frame bound", "src/transport.rs", "if len > MAX_FRAME {", "if len > MAX_FRAME * 2 {",
     "oversized_remote_frame_is_rejected_before_payload_and_service_survives"),
    ("restart key", "src/identity.rs", "SecretKey::from_bytes(&bytes)", "SecretKey::generate()",
     "sign_verify_rejects_forgery_and_restart_keeps_private_key"),
    ("signature verification", "src/identity.rs", "Some(key.verify(&bytes, &sig).is_ok())", "Some(true)",
     "sign_verify_rejects_forgery_and_restart_keeps_private_key"),
    ("port fallback", "src/transport.rs", "config.port != 0 && source.kind()", "config.port == 0 && source.kind()",
     "occupied_udp_port_falls_back_and_actual_bound_port_works"),
    ("JSONL cancellation", "src/ipc.rs", "line = read_line(&mut input) => line,",
     "line = read_line(&mut input) => line,\nSome(_) = tasks.join_next(), if !tasks.is_empty() => continue,",
     "partial_jsonl_survives_concurrent_request_completion"),
    ("direct port substitution", "src/transport.rs", "direct.set_port(bound.port());", "direct.set_port(0);",
     "direct_address_and_relay_modes_use_real_configuration"),
    ("expected key negative control", "tests/sidecar.rs", "wrong.id = iroh::SecretKey::generate().public();",
     "wrong.id = server.id();", "expected_endpoint_key_is_required_with_live_server_control"),
    ("per-device stream isolation", "src/ipc.rs", "peer.streams.clone().try_acquire_owned()",
     "Arc::new(Semaphore::new(4)).try_acquire_owned()", "per_device_stream_limit_is_shared_across_connections"),
]

def main():
    if not Path("Cargo.toml").is_file():
        raise SystemExit("run from native/xsm-net")
    for label, filename, before, after, test in CASES:
        path = Path(filename)
        original = path.read_bytes()
        text = original.decode()
        if text.count(before) != 1:
            raise SystemExit(f"mutation target changed: {label}")
        try:
            path.write_text(text.replace(before, after, 1))
            result = subprocess.run(
                ["cargo", "test", "--locked", "--test", "sidecar", test, "--", "--exact"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 or "test result: FAILED" not in result.stdout:
                print(result.stdout[-1500:])
                print(result.stderr[-1500:])
                raise SystemExit(f"mutation did not produce the expected test failure: {label}")
            print(f"DETECTED: {label}: {test}", flush=True)
        finally:
            path.write_bytes(original)
    print(f"{len(CASES)}/{len(CASES)} defects detected; original sources restored")

if __name__ == "__main__":
    main()
