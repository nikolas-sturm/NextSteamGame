FROM rust:1.89-bookworm AS builder
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY bindings ./bindings
COPY crates ./crates
COPY services ./services
RUN cargo build --locked --release -p api
RUN find target/release/build -path '*/out/zvec-prebuilt/libzvec_c_api.so' -exec cp {} /tmp/libzvec_c_api.so \; \
    && test -f /tmp/libzvec_c_api.so

FROM debian:bookworm-slim
RUN useradd --create-home --uid 10001 nextsteam
COPY --from=builder /src/target/release/api /usr/local/bin/nextsteam-api
COPY --from=builder /tmp/libzvec_c_api.so /usr/local/lib/libzvec_c_api.so
RUN ldconfig
USER nextsteam
ENV API_BIND=0.0.0.0:8080
EXPOSE 8080
ENTRYPOINT ["nextsteam-api"]
