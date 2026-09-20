# Cargo.lock currently resolves Edition 2024 crates and ICU 2.3, whose declared
# minimum supported Rust version is 1.88. Keep the container pin aligned with
# the workspace lockfile rather than relying on a newer host toolchain.
FROM rust:1.88-bookworm AS builder
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY libs/tradesync-contracts-rs libs/tradesync-contracts-rs
COPY services/alert-router-rs services/alert-router-rs
RUN cargo build --release --package alert-router-rs

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /build/target/release/alert-router-rs /usr/local/bin/alert-router-rs
EXPOSE 8010
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/alert-router-rs"]
