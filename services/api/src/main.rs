use std::{env, net::SocketAddr};

use api::{AppState, router};
use artifact_store::ArtifactStore;
use tokio::net::TcpListener;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("api=info,tower_http=info")),
        )
        .init();

    let artifact_dir = env::var("ARTIFACT_DIR").map_err(|_| "ARTIFACT_DIR is required")?;
    let store = ArtifactStore::load(artifact_dir)?;
    let fixture_build = store
        .manifest
        .acquisition_windows
        .get("kind")
        .and_then(|value| value.as_str())
        == Some("test_fixture");
    let fixtures_allowed = env::var("ALLOW_FIXTURE_ARTIFACTS").as_deref() == Ok("1");
    if fixture_build && !fixtures_allowed {
        return Err(
            "fixture artifact rejected; set ALLOW_FIXTURE_ARTIFACTS=1 only for local or CI use"
                .into(),
        );
    }
    let cors_origins = env::var("CORS_ORIGINS")
        .unwrap_or_default()
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let address: SocketAddr = env::var("API_BIND")
        .unwrap_or_else(|_| "127.0.0.1:8080".into())
        .parse()?;
    let app = router(AppState::from_artifacts(store), &cors_origins)?;
    let listener = TcpListener::bind(address).await?;
    tracing::info!(%address, "API listening");
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("install Ctrl-C handler")
    };
    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("install SIGTERM handler")
            .recv()
            .await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();
    tokio::select! { () = ctrl_c => {}, () = terminate => {} }
}
