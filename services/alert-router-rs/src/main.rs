use alert_router_rs::{accept_event, consume_once, AcceptError, AppState, MAX_BODY_BYTES};
use axum::{
    body::Bytes,
    extract::{DefaultBodyLimit, State},
    http::{header::AUTHORIZATION, HeaderMap, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use redis::aio::ConnectionManager;
use serde_json::json;
use std::{env, net::SocketAddr};
use tower_http::trace::TraceLayer;
use tradesync_contracts::AlertEventV1;

fn required(name: &str) -> String {
    env::var(name).unwrap_or_else(|_| panic!("{name} is required"))
}

async fn health() -> impl IntoResponse {
    Json(json!({"status":"ok","authority":"notify_only","execution_authority":false}))
}

async fn ingest(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    let token = headers
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .unwrap_or("");
    if !state.authorized(token) {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error":"producer authorization required"})),
        )
            .into_response();
    }
    let event: AlertEventV1 = match serde_json::from_slice(&body) {
        Ok(value) => value,
        Err(_) => {
            return (
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({"error":"invalid alert_event_v1 JSON"})),
            )
                .into_response()
        }
    };
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|v| v.as_millis() as i64)
        .unwrap_or(i64::MAX);
    match accept_event(&state, &event, now_ms).await {
        Ok(receipt) => (StatusCode::ACCEPTED, Json(json!(receipt))).into_response(),
        Err(AcceptError::Contract(error)) => (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({"error":format!("contract refused: {error:?}")})),
        )
            .into_response(),
        Err(AcceptError::Store(error)) => {
            tracing::error!(error=?error, event_id=%event.event_id, "alert persistence failed");
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"error":"durable alert store unavailable"})),
            )
                .into_response()
        }
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "alert_router_rs=info".into()),
        )
        .init();
    let (database, connection) =
        tokio_postgres::connect(&required("PG_DSN"), tokio_postgres::NoTls)
            .await
            .expect("connect PostgreSQL");
    tokio::spawn(async move {
        if let Err(error) = connection.await {
            tracing::error!(?error, "PostgreSQL connection ended");
        }
    });
    let redis_client = redis::Client::open(required("REDIS_URL")).expect("parse REDIS_URL");
    let redis = ConnectionManager::new(redis_client)
        .await
        .expect("connect Redis");
    let state = AppState::new(database, redis, required("ALERT_ROUTER_PRODUCER_TOKEN"))
        .expect("validate producer token");
    let consumer_state = state.clone();
    let consumer_name = format!("router-{}", std::process::id());
    tokio::spawn(async move {
        loop {
            if let Err(error) = consume_once(&consumer_state, &consumer_name).await {
                tracing::warn!(?error, "Redis ingress consumer retrying");
                tokio::time::sleep(std::time::Duration::from_secs(2)).await;
            }
        }
    });
    let app = Router::new()
        .route("/healthz", get(health))
        .route("/v1/alerts", post(ingest))
        .layer(DefaultBodyLimit::max(MAX_BODY_BYTES))
        .layer(TraceLayer::new_for_http())
        .with_state(state);
    let address = SocketAddr::from(([0, 0, 0, 0], 8010));
    let listener = tokio::net::TcpListener::bind(address)
        .await
        .expect("bind alert router");
    tracing::info!(%address, "alert router listening");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await
        .expect("serve alert router");
}
