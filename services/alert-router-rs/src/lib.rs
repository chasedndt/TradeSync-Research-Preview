//! Durable policy and persistence seam for TradeSync alerts.
//!
//! The router validates `alert_event_v1`, records every accepted or suppressed
//! event, and fans notification-safe rows into the existing mobile outbox. It
//! never scores, approves, signs, or executes a trade.

use redis::{
    aio::ConnectionManager, streams::StreamReadOptions, streams::StreamReadReply, AsyncCommands,
};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::sync::Arc;
use subtle::ConstantTimeEq;
use tokio::sync::Mutex;
use tokio_postgres::Client;
use tradesync_contracts::{AlertEventV1, ContractError, DataClassification};

pub const INGRESS_STREAM: &str = "alerts:ingress";
pub const ROUTED_STREAM: &str = "alerts:routed";
pub const DEAD_LETTER_STREAM: &str = "alerts:dead-letter";
pub const CONSUMER_GROUP: &str = "alert-router-rs";
pub const MAX_BODY_BYTES: usize = 32 * 1024;

#[derive(Clone)]
pub struct AppState {
    pub database: Arc<Mutex<Client>>,
    pub redis: ConnectionManager,
    producer_token: Arc<[u8]>,
}

impl AppState {
    pub fn new(
        database: Client,
        redis: ConnectionManager,
        producer_token: String,
    ) -> Result<Self, &'static str> {
        if producer_token.len() < 32 {
            return Err("ALERT_ROUTER_PRODUCER_TOKEN must contain at least 32 characters");
        }
        Ok(Self {
            database: Arc::new(Mutex::new(database)),
            redis,
            producer_token: Arc::from(producer_token.into_bytes()),
        })
    }

    pub fn authorized(&self, presented: &str) -> bool {
        let presented = presented.as_bytes();
        presented.len() == self.producer_token.len()
            && bool::from(presented.ct_eq(self.producer_token.as_ref()))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouteDecision {
    pub status: &'static str,
    pub reason: &'static str,
    pub deliver: bool,
}

pub fn route_decision(event: &AlertEventV1, now_ms: i64) -> RouteDecision {
    if event.expires_at_ms.is_some_and(|expiry| expiry <= now_ms) {
        return RouteDecision {
            status: "expired",
            reason: "event expired before routing",
            deliver: false,
        };
    }
    if event.data_classification == DataClassification::Restricted {
        return RouteDecision {
            status: "suppressed",
            reason: "restricted payloads are not permitted on the configured mobile transports",
            deliver: false,
        };
    }
    RouteDecision {
        status: "queued",
        reason: "eligible enabled devices are queued",
        deliver: true,
    }
}

#[derive(Debug, Serialize)]
pub struct RouteReceipt {
    pub event_id: String,
    pub outcome: &'static str,
    pub route_status: String,
    pub devices_queued: u64,
    pub stream_published: bool,
}

#[derive(Debug)]
pub enum StoreError {
    Database(tokio_postgres::Error),
    Serialization(serde_json::Error),
}

impl From<tokio_postgres::Error> for StoreError {
    fn from(value: tokio_postgres::Error) -> Self {
        Self::Database(value)
    }
}

impl From<serde_json::Error> for StoreError {
    fn from(value: serde_json::Error) -> Self {
        Self::Serialization(value)
    }
}

fn sha256_hex(value: &[u8]) -> String {
    hex::encode(Sha256::digest(value))
}

pub async fn persist_and_route(
    state: &AppState,
    event: &AlertEventV1,
    now_ms: i64,
) -> Result<RouteReceipt, StoreError> {
    let encoded = serde_json::to_vec(event)?;
    let digest = sha256_hex(&encoded);
    let decision = route_decision(event, now_ms);
    let mut client = state.database.lock().await;
    let transaction = client.transaction().await?;

    let inserted = transaction
        .query_opt(
            "insert into data_event_registry(event_id,event_kind) values($1,'alert_event_v1') \
         on conflict(event_id) do nothing returning event_id",
            &[&event.event_id],
        )
        .await?;
    if inserted.is_none() {
        transaction.rollback().await?;
        return Ok(RouteReceipt {
            event_id: event.event_id.clone(),
            outcome: "duplicate",
            route_status: "duplicate".into(),
            devices_queued: 0,
            stream_published: false,
        });
    }

    let created_seconds = event.created_at_ms as f64 / 1000.0;
    let expiry_seconds = event.expires_at_ms.map(|value| value as f64 / 1000.0);
    let severity = serde_json::to_value(event.severity)?
        .as_str()
        .unwrap_or("info")
        .to_owned();
    let environment = serde_json::to_value(event.environment)?
        .as_str()
        .unwrap_or("system")
        .to_owned();
    let classification = serde_json::to_value(event.data_classification)?
        .as_str()
        .unwrap_or("internal")
        .to_owned();
    let evidence = serde_json::to_value(&event.evidence_refs)?;
    let attributes = serde_json::to_value(&event.attributes)?;
    transaction.execute(
        "insert into alert_events_v1(event_id,project,source,category,severity,environment,title,body,created_at,expires_at,\
         dedupe_key,data_classification,requires_ack,symbol,timeframe,evidence_refs,deep_link,correlation_id,causation_id,attributes,\
         payload_hash,route_status,route_reason) values($1,$2,$3,$4,$5,$6,$7,$8,to_timestamp($9),\
         case when $10::double precision is null then null else to_timestamp($10) end,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)",
        &[&event.event_id, &event.project, &event.source, &event.category, &severity, &environment,
          &event.title, &event.body, &created_seconds, &expiry_seconds, &event.dedupe_key, &classification,
          &event.requires_ack, &event.symbol, &event.timeframe, &evidence, &event.deep_link,
          &event.correlation_id, &event.causation_id, &attributes, &digest, &decision.status, &decision.reason],
    ).await?;

    let devices_queued = if decision.deliver {
        let expiry = expiry_seconds.unwrap_or(created_seconds + 600.0);
        transaction.execute(
            "insert into mobile_alert_outbox(id,device_id,dedupe_key,kind,expires_at,alert_event_id) \
             select gen_random_uuid(),id,$1,'attention',to_timestamp($2),$3 from mobile_alert_devices \
             where enabled and operator_confirmed_at is not null \
             on conflict(device_id,dedupe_key) do nothing",
            &[&format!("{}:{}", event.project, event.dedupe_key), &expiry, &event.event_id],
        ).await?
    } else {
        0
    };
    transaction.commit().await?;
    drop(client);

    let mut redis = state.redis.clone();
    let stream_published = redis::cmd("XADD")
        .arg(ROUTED_STREAM)
        .arg("MAXLEN")
        .arg("~")
        .arg(10_000)
        .arg("*")
        .arg("event_id")
        .arg(&event.event_id)
        .arg("route_status")
        .arg(decision.status)
        .arg("devices_queued")
        .arg(devices_queued)
        .query_async::<_, String>(&mut redis)
        .await
        .is_ok();

    Ok(RouteReceipt {
        event_id: event.event_id.clone(),
        outcome: "recorded",
        route_status: decision.status.into(),
        devices_queued,
        stream_published,
    })
}

/// Validate the contract and persist it. Expiry is a routing state, not data
/// loss: an otherwise valid expired event is recorded with `route_status=expired`.
pub async fn accept_event(
    state: &AppState,
    event: &AlertEventV1,
    now_ms: i64,
) -> Result<RouteReceipt, AcceptError> {
    match event.validate(now_ms) {
        Ok(()) | Err(ContractError::AlreadyExpired) => persist_and_route(state, event, now_ms)
            .await
            .map_err(AcceptError::Store),
        Err(error) => Err(AcceptError::Contract(error)),
    }
}

#[derive(Debug)]
pub enum AcceptError {
    Contract(ContractError),
    Store(StoreError),
}

async fn dead_letter(
    redis: &mut ConnectionManager,
    stream_id: &str,
    reason: &str,
) -> redis::RedisResult<String> {
    redis::cmd("XADD")
        .arg(DEAD_LETTER_STREAM)
        .arg("MAXLEN")
        .arg("~")
        .arg(10_000)
        .arg("*")
        .arg("ingress_id")
        .arg(stream_id)
        .arg("reason")
        .arg(reason)
        .query_async(redis)
        .await
}

/// Consume one Redis batch. A message is acknowledged only after durable
/// PostgreSQL storage, or after a malformed/refused payload is itself written
/// to the dead-letter stream. Transient database failures remain pending.
pub async fn consume_once(state: &AppState, consumer: &str) -> redis::RedisResult<usize> {
    let mut redis = state.redis.clone();
    let _: redis::RedisResult<String> = redis::cmd("XGROUP")
        .arg("CREATE")
        .arg(INGRESS_STREAM)
        .arg(CONSUMER_GROUP)
        .arg("0")
        .arg("MKSTREAM")
        .query_async(&mut redis)
        .await;
    let options = StreamReadOptions::default()
        .group(CONSUMER_GROUP, consumer)
        .count(25)
        .block(5_000);
    let reply: StreamReadReply = redis
        .xread_options(&[INGRESS_STREAM], &[">"], &options)
        .await?;
    let mut acknowledged = 0;
    for key in reply.keys {
        for id in key.ids {
            let payload: Option<String> = id.get("payload");
            let event = payload
                .as_deref()
                .and_then(|value| serde_json::from_str::<AlertEventV1>(value).ok());
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|value| value.as_millis() as i64)
                .unwrap_or(i64::MAX);
            let may_ack = match event {
                Some(event) => match accept_event(state, &event, now_ms).await {
                    Ok(_) => true,
                    Err(AcceptError::Contract(error)) => {
                        dead_letter(&mut redis, &id.id, &format!("contract refused: {error:?}"))
                            .await
                            .is_ok()
                    }
                    Err(AcceptError::Store(error)) => {
                        tracing::warn!(?error, ingress_id=%id.id, "alert remains pending after store failure");
                        false
                    }
                },
                None => dead_letter(
                    &mut redis,
                    &id.id,
                    "invalid or missing alert_event_v1 payload",
                )
                .await
                .is_ok(),
            };
            if may_ack {
                let count: i64 = redis
                    .xack(INGRESS_STREAM, CONSUMER_GROUP, &[&id.id])
                    .await?;
                acknowledged += count as usize;
            }
        }
    }
    Ok(acknowledged)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    use tradesync_contracts::{AlertEnvironment, AlertSeverity};

    fn event(classification: DataClassification, expiry: Option<i64>) -> AlertEventV1 {
        AlertEventV1 {
            schema_version: "alert_event_v1".into(),
            event_id: "evt-1".into(),
            project: "tradesync".into(),
            source: "paper-risk".into(),
            category: "paper.limit".into(),
            severity: AlertSeverity::Warning,
            environment: AlertEnvironment::Paper,
            title: "Paper limit".into(),
            body: "Open the dashboard.".into(),
            created_at_ms: 1000,
            dedupe_key: "paper-limit".into(),
            data_classification: classification,
            symbol: Some("BTC".into()),
            timeframe: Some("1h".into()),
            expires_at_ms: expiry,
            requires_ack: true,
            evidence_refs: vec![],
            deep_link: Some("/execution".into()),
            correlation_id: None,
            causation_id: None,
            attributes: BTreeMap::new(),
        }
    }

    #[test]
    fn ordinary_alerts_route() {
        assert_eq!(
            route_decision(&event(DataClassification::Internal, Some(2000)), 1500),
            RouteDecision {
                status: "queued",
                reason: "eligible enabled devices are queued",
                deliver: true
            }
        );
    }

    #[test]
    fn restricted_payloads_are_recorded_but_not_sent() {
        let decision = route_decision(&event(DataClassification::Restricted, Some(2000)), 1500);
        assert_eq!(decision.status, "suppressed");
        assert!(!decision.deliver);
    }

    #[test]
    fn expiry_wins_before_classification() {
        let decision = route_decision(&event(DataClassification::Restricted, Some(1499)), 1500);
        assert_eq!(decision.status, "expired");
        assert!(!decision.deliver);
    }
}
