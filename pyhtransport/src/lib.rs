use pyo3::prelude::*;
use std::sync::Once;

mod dedicated_thread_server;
mod request_receiver;
mod response_chunk;
mod response_sender;

static INIT_TRACING: Once = Once::new();

/// Initialize tracing subscriber
///
/// This function sets up logging based on environment variables:
/// - LOG_LEVEL: Controls log level (DEBUG, INFO, WARNING, ERROR) - unified for Rust and Python
/// - LOG_FORMAT: Controls output format ("json" or "text", defaults to "text")
fn init_tracing() {
    INIT_TRACING.call_once(|| {
        use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

        // Get log level from LOG_LEVEL environment variable (default: INFO)
        let log_level = std::env::var("LOG_LEVEL")
            .unwrap_or_else(|_| "INFO".to_string())
            .to_lowercase();

        // Map Python-style log levels to Rust log levels
        let rust_level = match log_level.as_str() {
            "debug" => "debug",
            "info" => "info",
            "warning" | "warn" => "warn",
            "error" => "error",
            _ => "info", // Default to info for unknown values
        };

        // Get log format from environment (default: text)
        let log_format = std::env::var("LOG_FORMAT")
            .unwrap_or_else(|_| "text".to_string())
            .to_lowercase();

        // Create env filter with the determined level
        let env_filter = EnvFilter::new(rust_level);

        let registry = tracing_subscriber::registry().with(env_filter);

        match log_format.as_str() {
            "json" => {
                // JSON format for production/log aggregation
                if let Err(e) = registry
                    .with(fmt::layer().json().flatten_event(true))
                    .try_init()
                {
                    eprintln!("tracing already initialized elsewhere: {e}");
                }
            }
            _ => {
                // Text format for development (default)
                if let Err(e) = registry
                    .with(fmt::layer().with_target(false).with_thread_ids(true))
                    .try_init()
                {
                    eprintln!("tracing already initialized elsewhere: {e}");
                }
            }
        }
    });
}

#[pymodule(gil_used = false)]
fn pyhtransport(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Initialize tracing on module load
    init_tracing();

    m.add_class::<dedicated_thread_server::DedicatedThreadServer>()?;
    m.add_class::<response_sender::ResponseSender>()?;
    m.add_class::<request_receiver::RequestReceiver>()?;
    Ok(())
}
