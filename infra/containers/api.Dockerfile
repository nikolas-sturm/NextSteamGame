FROM rust:1.89-bookworm AS builder
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
COPY services ./services
RUN cargo build --locked --release -p api

FROM debian:bookworm-slim
RUN useradd --create-home --uid 10001 nextsteam
COPY --from=builder /src/target/release/api /usr/local/bin/nextsteam-api
USER nextsteam
ENV API_BIND=0.0.0.0:8080
EXPOSE 8080
ENTRYPOINT ["nextsteam-api"]
