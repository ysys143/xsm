//! Signed Python JSON must survive the engine without changing float values.
#[test]
fn signature_timestamps_keep_the_exact_binary_value() {
    let input = r#"{"issued_at":1793689766.9242175,"expires_at":1793689776.9242175}"#;
    let value: serde_json::Value = serde_json::from_str(input).unwrap();
    assert_eq!(value["issued_at"].as_f64(), Some(1793689766.9242175_f64));
    let output = serde_json::to_string(&value).unwrap();
    let reread: serde_json::Value = serde_json::from_str(&output).unwrap();
    assert_eq!(reread["issued_at"].as_f64(), Some(1793689766.9242175_f64));
    assert_eq!(value, reread);
}
