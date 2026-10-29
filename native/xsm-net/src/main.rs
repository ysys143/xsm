use std::path::PathBuf;
use xsm_net::{Error, Result, identity::Identity, transport::Config};

fn main() {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .expect("runtime");
    let result = runtime.block_on(run());
    // Tokio's stdio worker can be stuck in a pipe write if the controller
    // stops reading. Do not wait forever for an uncancellable OS write.
    runtime.shutdown_timeout(std::time::Duration::from_secs(1));
    if let Err(e) = result {
        eprintln!("xsm-net: {}", e.0);
        std::process::exit(1);
    }
}
async fn run() -> Result<()> {
    let mut args = std::env::args().skip(1);
    if args.next().as_deref() != Some("serve") {
        return Err(Error("usage"));
    }
    let mut state: Option<PathBuf> = None;
    let mut config = Config::default();
    while let Some(arg) = args.next() {
        let value = args.next().ok_or(Error("usage"))?;
        match arg.as_str() {
            "--state-dir" if state.is_none() => state = Some(value.into()),
            "--port" => config.port = value.parse().map_err(|_| Error("invalid_port"))?,
            "--relay" => config.relay = Config::relay(Some(&value))?,
            "--direct-address" => config
                .direct
                .push(value.parse().map_err(|_| Error("invalid_address"))?),
            _ => return Err(Error("usage")),
        }
    }
    let identity = Identity::load(&state.ok_or(Error("usage"))?)?;
    let transport = identity.bind(config).await?;
    xsm_net::ipc::serve(identity, transport, tokio::io::stdin(), tokio::io::stdout()).await
}
