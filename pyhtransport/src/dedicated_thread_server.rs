use anyhow::Result;
use bytes::Bytes;
use http::{HeaderName, HeaderValue};
use http_body_util::{combinators::BoxBody, BodyExt, Full, StreamBody};
use hyper::body::{Frame, Incoming};
use hyper::service::Service;
use hyper::{HeaderMap, Request, Response, StatusCode};
use hyper_util::rt::TokioExecutor;
use hyper_util::rt::TokioIo;
use hyper_util::server::conn::auto::Builder;
use pyo3::prelude::*;
use std::convert::Infallible;
use std::future::Future;
#[cfg(unix)]
use std::os::unix::io::{FromRawFd, RawFd};
use std::pin::Pin;
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::{mpsc, Semaphore};
use tokio_stream::wrappers::UnboundedReceiverStream;
use tokio_stream::StreamExt;
use tracing::{debug, error, info};

use crate::response_chunk::ResponseChunk;

// Global memory allocator configuration for better performance
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

// Request chunk for streaming request body
#[derive(Debug, Clone)]
pub enum RequestChunk {
    /// Body chunk with more_body flag
    Body { data: Bytes, more_body: bool },
    /// Request completed
    Done,
}

// Request/Response types for channel communication
struct RequestData {
    method: String,
    path: String,
    headers: Vec<(String, String)>,
    body: Bytes, // Changed from Vec<u8> to Bytes for zero-copy
    // For full-duplex: stream request chunks (optional)
    request_chunks_rx: Option<mpsc::UnboundedReceiver<RequestChunk>>,
    // Streaming response channel
    response_tx: ResponseSender,
}

// Streaming response sender
struct ResponseSender(mpsc::UnboundedSender<crate::response_chunk::ResponseChunk>);

#[pyclass]
pub struct DedicatedThreadServer {
    blocking_threads: usize,
    keepalive_timeout: u64,           // Keep-alive timeout in seconds
    limit_concurrency: Option<usize>, // Maximum concurrent connections (None = unlimited)
}

#[pymethods]
impl DedicatedThreadServer {
    #[new]
    #[pyo3(signature = (blocking_threads=None, keepalive=None, limit_concurrency=None))]
    pub fn new(
        blocking_threads: Option<usize>,
        keepalive: Option<u64>,
        limit_concurrency: Option<usize>,
    ) -> Self {
        Self {
            blocking_threads: blocking_threads.unwrap_or(4),
            keepalive_timeout: keepalive.unwrap_or(5), // Default 5 seconds
            limit_concurrency,                         // None = unlimited
        }
    }

    #[cfg(unix)]
    pub fn serve_fd(&self, py: Python<'_>, fd: i32, py_handler: Py<PyAny>) -> PyResult<()> {
        // Dual runtime architecture (same configuration as serve() method)

        // Store configuration
        let keepalive_timeout = self.keepalive_timeout;
        let limit_concurrency = self.limit_concurrency;

        // IO worker threads: optimized for network I/O
        // Default: Single thread for optimal HTTP/1.1 performance
        // For HTTP/2 workloads, set TOKIO_WORKER_THREADS=3 or use serve() tokio_threads parameter
        let default_workers = 1; // Single thread optimal for HTTP/1.1

        // Environment variable priority:
        // 1. TOKIO_WORKER_THREADS (highest priority)
        // 2. IO_WORKER_THREADS (alternative naming)
        // 3. Default value
        let worker_threads = std::env::var("TOKIO_WORKER_THREADS")
            .ok()
            .and_then(|s| s.parse::<usize>().ok())
            .or_else(|| {
                std::env::var("IO_WORKER_THREADS")
                    .ok()
                    .and_then(|s| s.parse::<usize>().ok())
            })
            .unwrap_or(default_workers);

        let runtime = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(worker_threads)
            .max_blocking_threads(1)
            .thread_keep_alive(std::time::Duration::from_secs(120)) // Longer keep-alive
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{:?}", e)))?;

        let handler_clone = py_handler.clone_ref(py);
        let fd = fd as RawFd;
        let blocking_threads = self.blocking_threads;

        py.detach(move || {
            runtime.block_on(async move {
                self.serve_fd_async(
                    fd,
                    handler_clone,
                    blocking_threads,
                    keepalive_timeout,
                    limit_concurrency,
                )
                .await
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{:?}", e)))
            })
        })
    }

    #[cfg(not(unix))]
    pub fn serve_fd(&self, _py: Python<'_>, _fd: i32, _py_handler: Py<PyAny>) -> PyResult<()> {
        Err(pyo3::exceptions::PyRuntimeError::new_err(
            "serve_fd is only supported on Unix systems",
        ))
    }

    #[cfg(unix)]
    pub fn serve_uds(
        &self,
        py: Python<'_>,
        socket_path: &str,
        py_handler: Py<PyAny>,
    ) -> PyResult<()> {
        // Dual runtime architecture (same configuration as serve() method)

        // IO worker threads: optimized for network I/O
        let default_workers = 1; // Single thread optimal for HTTP/1.1

        // Environment variable priority:
        // 1. TOKIO_WORKER_THREADS (highest priority)
        // 2. IO_WORKER_THREADS (alternative naming)
        // 3. Default value
        let worker_threads = std::env::var("TOKIO_WORKER_THREADS")
            .ok()
            .and_then(|s| s.parse::<usize>().ok())
            .or_else(|| {
                std::env::var("IO_WORKER_THREADS")
                    .ok()
                    .and_then(|s| s.parse::<usize>().ok())
            })
            .unwrap_or(default_workers);

        let runtime = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(worker_threads)
            .max_blocking_threads(1)
            .thread_keep_alive(std::time::Duration::from_secs(120))
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{:?}", e)))?;

        let socket_path = socket_path.to_string();
        let handler_clone = py_handler.clone_ref(py);
        let blocking_threads = self.blocking_threads;
        let keepalive_timeout = self.keepalive_timeout;
        let limit_concurrency = self.limit_concurrency;

        py.detach(move || {
            runtime.block_on(async move {
                self.serve_uds_async(
                    &socket_path,
                    handler_clone,
                    blocking_threads,
                    keepalive_timeout,
                    limit_concurrency,
                )
                .await
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{:?}", e)))
            })
        })
    }

    #[cfg(not(unix))]
    pub fn serve_uds(
        &self,
        _py: Python<'_>,
        _socket_path: &str,
        _py_handler: Py<PyAny>,
    ) -> PyResult<()> {
        Err(pyo3::exceptions::PyRuntimeError::new_err(
            "serve_uds is only supported on Unix systems",
        ))
    }
}

impl DedicatedThreadServer {
    #[cfg(unix)]
    async fn serve_fd_async(
        &self,
        fd: RawFd,
        py_handler: Py<PyAny>,
        blocking_threads: usize,
        keepalive_timeout: u64,
        limit_concurrency: Option<usize>,
    ) -> Result<()> {
        // Create std TcpListener from raw FD
        let std_listener = unsafe { std::net::TcpListener::from_raw_fd(fd) };
        std_listener.set_nonblocking(true)?;
        let listener = TcpListener::from_std(std_listener)?;

        info!(
            fd = fd,
            blocking_threads = blocking_threads,
            "Server listening on inherited FD"
        );

        // Create Semaphore for connection limiting (configurable via limit_concurrency)
        let max_concurrent_connections = limit_concurrency.unwrap_or(2000); // Default: 2000 connections
        let semaphore = Arc::new(Semaphore::new(max_concurrent_connections));

        if let Some(limit) = limit_concurrency {
            info!("Connection limit: {} concurrent connections", limit);
        } else {
            info!(
                "Connection limit: {} concurrent connections (default)",
                max_concurrent_connections
            );
        }

        // Create channel for communication with blocking threads
        // Further optimized buffer size for maximum throughput
        let (request_tx, request_rx) = mpsc::channel::<RequestData>(4096); // Doubled buffer size
        let request_rx = Arc::new(tokio::sync::Mutex::new(request_rx));

        // Wrap handler in Arc for sharing across threads (Py<PyAny> is Send + Sync)
        let handler_arc = Arc::new(py_handler);

        // Spawn dedicated blocking threads
        for thread_id in 0..blocking_threads {
            let handler = Arc::clone(&handler_arc);
            let rx = Arc::clone(&request_rx);

            std::thread::Builder::new()
                .name(format!("blocking-{}", thread_id))
                .spawn(move || {
                    // Thread started without CPU affinity (let OS scheduler handle it)

                    blocking_thread_worker(thread_id, handler, rx);
                })
                .expect("Failed to spawn blocking thread");
        }

        // Main accept loop with signal handling
        #[cfg(unix)]
        {
            let mut sigterm =
                tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
            let mut sigint =
                tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())?;

            loop {
                let accept_result = tokio::select! {
                    result = listener.accept() => result,
                    _ = sigterm.recv() => {
                        info!("Received SIGTERM, shutting down gracefully");
                        break;
                    }
                    _ = sigint.recv() => {
                        info!("Received SIGINT (Ctrl+C), shutting down gracefully");
                        break;
                    }
                };

                let (tcp_stream, _addr) = match accept_result {
                    Ok(result) => result,
                    Err(_) => continue,
                };

                // Acquire permit from semaphore for backpressure
                let permit = semaphore.clone().acquire_owned().await?;

                // Enable TCP_NODELAY to reduce latency
                tcp_stream.set_nodelay(true)?;

                // Aggressive TCP optimizations for maximum throughput
                let socket = socket2::Socket::from(tcp_stream.into_std()?);
                socket.set_send_buffer_size(1024 * 1024)?; // 1MB send buffer
                socket.set_recv_buffer_size(1024 * 1024)?; // 1MB receive buffer
                                                           // Linux-specific TCP optimizations
                #[cfg(target_os = "linux")]
                {
                    socket.set_keepalive(true)?;
                    let ka_idle = std::time::Duration::from_secs(60);
                    socket.set_tcp_keepalive(&socket2::TcpKeepalive::new().with_time(ka_idle))?;
                }
                let tcp_stream = tokio::net::TcpStream::from_std(socket.into())?;

                let stream = TokioIo::new(tcp_stream);
                let request_tx = request_tx.clone();
                let keepalive = keepalive_timeout; // Clone for async move block

                tokio::spawn(async move {
                    let service = DedicatedThreadService { request_tx };

                    // Optimized Hyper builder with HTTP/2 enhancements
                    let mut builder = Builder::new(TokioExecutor::new());

                    // HTTP/1.1 Keep-Alive configuration
                    builder
                        .http1()
                        .keep_alive(true)
                        .timer(hyper_util::rt::TokioTimer::new());

                    // HTTP/2 optimization parameters
                    builder
                        .http2()
                        // Timer for HTTP/2 (required for keep-alive)
                        .timer(hyper_util::rt::TokioTimer::new())
                        // Keep-alive for HTTP/2
                        .keep_alive_interval(Some(std::time::Duration::from_secs(keepalive)))
                        .keep_alive_timeout(std::time::Duration::from_secs(keepalive * 2))
                        // Increase initial window size for better throughput (default: 65KB)
                        .initial_stream_window_size(1024 * 1024) // 1MB per stream
                        .initial_connection_window_size(4 * 1024 * 1024) // 4MB total
                        // Increase max concurrent streams (default: 100)
                        .max_concurrent_streams(1000)
                        // Adaptive window for flow control
                        .adaptive_window(true)
                        // Increase max frame size (default: 16KB)
                        .max_frame_size(64 * 1024) // 64KB
                        // Increase header table size
                        .max_header_list_size(16 * 1024); // 16KB

                    if let Err(_e) = builder.serve_connection(stream, service).await {
                        // Connection error, ignore
                    }

                    // Release permit when connection closes
                    drop(permit);
                });
            }
        }

        #[cfg(not(unix))]
        {
            loop {
                let (tcp_stream, _addr) = listener.accept().await?;

                // Acquire permit from semaphore for backpressure
                let permit = semaphore.clone().acquire_owned().await?;

                // Enable TCP_NODELAY to reduce latency
                tcp_stream.set_nodelay(true)?;

                // Aggressive TCP optimizations for maximum throughput
                let socket = socket2::Socket::from(tcp_stream.into_std()?);
                socket.set_send_buffer_size(1024 * 1024)?; // 1MB send buffer
                socket.set_recv_buffer_size(1024 * 1024)?; // 1MB receive buffer
                                                           // Linux-specific TCP optimizations
                #[cfg(target_os = "linux")]
                {
                    socket.set_keepalive(true)?;
                    let ka_idle = std::time::Duration::from_secs(60);
                    socket.set_tcp_keepalive(&socket2::TcpKeepalive::new().with_time(ka_idle))?;
                }
                let tcp_stream = tokio::net::TcpStream::from_std(socket.into())?;

                let stream = TokioIo::new(tcp_stream);
                let request_tx = request_tx.clone();
                let keepalive = keepalive_timeout; // Clone for async move block

                tokio::spawn(async move {
                    let service = DedicatedThreadService { request_tx };

                    // Optimized Hyper builder with HTTP/2 enhancements
                    let mut builder = Builder::new(TokioExecutor::new());

                    // HTTP/1.1 Keep-Alive configuration
                    builder
                        .http1()
                        .keep_alive(true)
                        .timer(hyper_util::rt::TokioTimer::new());

                    // HTTP/2 optimization parameters
                    builder
                        .http2()
                        // Timer for HTTP/2 (required for keep-alive)
                        .timer(hyper_util::rt::TokioTimer::new())
                        // Keep-alive for HTTP/2
                        .keep_alive_interval(Some(std::time::Duration::from_secs(keepalive)))
                        .keep_alive_timeout(std::time::Duration::from_secs(keepalive * 2))
                        // Increase initial window size for better throughput (default: 65KB)
                        .initial_stream_window_size(1024 * 1024) // 1MB per stream
                        .initial_connection_window_size(4 * 1024 * 1024) // 4MB total
                        // Increase max concurrent streams (default: 100)
                        .max_concurrent_streams(1000)
                        // Adaptive window for flow control
                        .adaptive_window(true)
                        // Increase max frame size (default: 16KB)
                        .max_frame_size(64 * 1024) // 64KB
                        // Increase header table size
                        .max_header_list_size(16 * 1024); // 16KB

                    if let Err(_e) = builder.serve_connection(stream, service).await {
                        // Connection error, ignore
                    }

                    // Release permit when connection closes
                    drop(permit);
                });
            }
        }

        Ok(())
    }

    #[cfg(unix)]
    async fn serve_uds_async(
        &self,
        socket_path: &str,
        py_handler: Py<PyAny>,
        blocking_threads: usize,
        keepalive_timeout: u64,
        limit_concurrency: Option<usize>,
    ) -> Result<()> {
        use tokio::net::UnixListener;

        // Remove existing socket file if it exists
        if std::path::Path::new(socket_path).exists() {
            std::fs::remove_file(socket_path)?;
        }

        // Bind to Unix domain socket
        let listener = UnixListener::bind(socket_path)?;

        info!(
            socket_path = socket_path,
            blocking_threads = blocking_threads,
            "Server listening on Unix domain socket"
        );

        // Create Semaphore for connection limiting (configurable via limit_concurrency)
        let max_concurrent_connections = limit_concurrency.unwrap_or(2000); // Default: 2000 connections
        let semaphore = Arc::new(Semaphore::new(max_concurrent_connections));

        if let Some(limit) = limit_concurrency {
            info!("Connection limit: {} concurrent connections", limit);
        } else {
            info!(
                "Connection limit: {} concurrent connections (default)",
                max_concurrent_connections
            );
        }

        // Create channel for communication with blocking threads
        // Further optimized buffer size for maximum throughput
        let (request_tx, request_rx) = mpsc::channel::<RequestData>(4096); // Doubled buffer size
        let request_rx = Arc::new(tokio::sync::Mutex::new(request_rx));

        // Wrap handler in Arc for sharing across threads (Py<PyAny> is Send + Sync)
        let handler_arc = Arc::new(py_handler);

        // Spawn dedicated blocking threads
        for thread_id in 0..blocking_threads {
            let handler = Arc::clone(&handler_arc);
            let rx = Arc::clone(&request_rx);

            std::thread::Builder::new()
                .name(format!("blocking-{}", thread_id))
                .spawn(move || {
                    blocking_thread_worker(thread_id, handler, rx);
                })
                .expect("Failed to spawn blocking thread");
        }

        // Main accept loop with signal handling
        let mut sigterm =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
        let mut sigint = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())?;

        loop {
            let accept_result = tokio::select! {
                result = listener.accept() => result,
                _ = sigterm.recv() => {
                    info!("Received SIGTERM, shutting down gracefully");
                    break;
                }
                _ = sigint.recv() => {
                    info!("Received SIGINT (Ctrl+C), shutting down gracefully");
                    break;
                }
            };

            let (unix_stream, _addr) = match accept_result {
                Ok(result) => result,
                Err(_) => continue,
            };

            // Acquire permit from semaphore for backpressure
            let permit = semaphore.clone().acquire_owned().await?;

            let stream = TokioIo::new(unix_stream);
            let request_tx = request_tx.clone();
            let keepalive = keepalive_timeout; // Clone for async move block

            tokio::spawn(async move {
                let service = DedicatedThreadService { request_tx };

                // Optimized Hyper builder with HTTP/2 enhancements
                let mut builder = Builder::new(TokioExecutor::new());

                // HTTP/1.1 Keep-Alive configuration
                builder
                    .http1()
                    .keep_alive(true)
                    .timer(hyper_util::rt::TokioTimer::new());

                // HTTP/2 optimization parameters
                builder
                    .http2()
                    // Timer for HTTP/2 (required for keep-alive)
                    .timer(hyper_util::rt::TokioTimer::new())
                    // Keep-alive for HTTP/2
                    .keep_alive_interval(Some(std::time::Duration::from_secs(keepalive)))
                    .keep_alive_timeout(std::time::Duration::from_secs(keepalive * 2))
                    .initial_stream_window_size(1024 * 1024) // 1MB per stream
                    .initial_connection_window_size(4 * 1024 * 1024) // 4MB total
                    .max_concurrent_streams(1000)
                    .adaptive_window(true)
                    .max_frame_size(64 * 1024) // 64KB
                    .max_header_list_size(16 * 1024); // 16KB

                if let Err(_e) = builder.serve_connection(stream, service).await {
                    // Connection error, ignore
                }

                // Release permit when connection closes
                drop(permit);
            });
        }

        // Cleanup: Remove socket file on shutdown
        let _ = std::fs::remove_file(socket_path);

        Ok(())
    }
}

// Worker function for blocking threads with persistent GIL
fn blocking_thread_worker(
    thread_id: usize,
    py_handler: Arc<Py<PyAny>>,
    request_rx: Arc<tokio::sync::Mutex<mpsc::Receiver<RequestData>>>,
) {
    debug!(thread_id = thread_id, "Blocking thread started");

    // Create a Tokio runtime for this thread (needed for async channel operations)
    // Optimize runtime configuration for better performance
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .max_blocking_threads(1) // Minimize blocking thread overhead
        .thread_keep_alive(std::time::Duration::from_secs(120)) // Longer keep-alive
        .build()
        .expect("Failed to create runtime");

    // Initialize Python for this thread
    Python::initialize();

    rt.block_on(async move {
        // Optimized batch processing for maximum throughput
        const BATCH_SIZE: usize = 20; // Optimal balance between throughput and latency
        const BATCH_TIMEOUT: std::time::Duration = std::time::Duration::from_micros(50); // Balanced for responsiveness

        loop {
            // Collect batch of requests
            let mut batch = Vec::with_capacity(BATCH_SIZE);

            // Get first request (blocking)
            let first_request = {
                let mut rx = request_rx.lock().await;
                rx.recv().await
            };

            let Some(first_request) = first_request else {
                // Channel closed, exit thread
                break;
            };

            batch.push(first_request);

            // Try to get more requests quickly (with timeout)
            let deadline = tokio::time::Instant::now() + BATCH_TIMEOUT;
            while batch.len() < BATCH_SIZE {
                let timeout_result = tokio::time::timeout_at(deadline, async {
                    let mut rx = request_rx.lock().await;
                    rx.recv().await
                })
                .await;

                match timeout_result {
                    Ok(Some(request)) => batch.push(request),
                    _ => break, // Timeout or channel closed
                }
            }

            // Process batch in single GIL acquisition (streaming mode - no response waiting!)
            Python::attach(|py| {
                for mut request in batch.into_iter() {
                    // Create ResponseSender wrapping the streaming channel
                    let sender = crate::response_sender::ResponseSender::new_streaming(
                        request.response_tx.0.clone(),
                    );

                    let py_sender = Py::new(py, sender).expect("Failed to create ResponseSender");

                    // Convert body to PyBytes
                    let py_body = pyo3::types::PyBytes::new(py, request.body.as_ref());

                    // Create RequestReceiver if we have streaming chunks
                    let py_request_receiver =
                        if let Some(chunks_rx) = request.request_chunks_rx.take() {
                            let receiver = crate::request_receiver::RequestReceiver::new(chunks_rx);
                            Some(Py::new(py, receiver).expect("Failed to create RequestReceiver"))
                        } else {
                            None
                        };

                    // Call the Python handler with optional RequestReceiver
                    let args = (
                        py_sender,
                        request.method.clone(),
                        request.path.clone(),
                        request.headers.clone(),
                        py_body,
                        py_request_receiver, // New 6th argument (Optional)
                    );

                    if let Err(e) = py_handler.call1(py, args) {
                        error!(error = ?e, "Error calling Python handler");
                    }
                }

                // Allow Python to process other threads
                py.check_signals().ok();
            });
            // No response waiting - responses stream directly via mpsc channels!
        }
    });

    debug!(thread_id = thread_id, "Blocking thread exiting");
}

// Service implementation using dedicated threads
#[derive(Clone)]
struct DedicatedThreadService {
    request_tx: mpsc::Sender<RequestData>,
}

type ResponseBody = BoxBody<Bytes, Infallible>;

impl Service<Request<Incoming>> for DedicatedThreadService {
    type Response = Response<ResponseBody>;
    type Error = hyper::Error;
    type Future = Pin<Box<dyn Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn call(&self, req: Request<Incoming>) -> Self::Future {
        let request_tx = self.request_tx.clone();
        let method = req.method().to_string();
        let path = req.uri().path().to_string();

        // Collect headers
        let mut headers = Vec::new();
        for (key, value) in req.headers().iter() {
            headers.push((key.to_string(), value.to_str().unwrap_or("").to_string()));
        }

        Box::pin(async move {
            // Detect streaming request ONLY by explicit Transfer-Encoding: chunked header
            // Don't use missing Content-Length as indicator (GET requests have no body!)
            let is_streaming_request = headers
                .iter()
                .any(|(k, v)| k.to_lowercase() == "transfer-encoding" && v.contains("chunked"));

            // Create streaming response channel
            let (chunk_tx, chunk_rx) = mpsc::unbounded_channel::<ResponseChunk>();

            let (body_bytes, request_chunks_rx) = if is_streaming_request {
                // Full-duplex mode: stream request body chunks
                let (req_chunks_tx, req_chunks_rx) = mpsc::unbounded_channel::<RequestChunk>();
                let mut body_stream = req.into_body();

                // Spawn task to stream body chunks
                let req_chunks_tx_clone = req_chunks_tx.clone();
                tokio::spawn(async move {
                    use http_body_util::BodyExt;
                    loop {
                        match body_stream.frame().await {
                            Some(Ok(frame)) => {
                                if let Ok(data) = frame.into_data() {
                                    if !data.is_empty() {
                                        let _ = req_chunks_tx_clone.send(RequestChunk::Body {
                                            data: data.clone(),
                                            more_body: true,
                                        });
                                    }
                                }
                            }
                            None => {
                                // End of stream - send final chunk with more_body=false
                                let _ = req_chunks_tx_clone.send(RequestChunk::Body {
                                    data: Bytes::new(),
                                    more_body: false,
                                });
                                let _ = req_chunks_tx_clone.send(RequestChunk::Done);
                                break;
                            }
                            Some(Err(_)) => {
                                // Error reading body
                                let _ = req_chunks_tx_clone.send(RequestChunk::Done);
                                break;
                            }
                        }
                    }
                });

                // Return empty body for backward compatibility, with streaming channel
                (Bytes::new(), Some(req_chunks_rx))
            } else {
                // Half-duplex mode: collect entire body (existing behavior)
                let body_result = req.into_body().collect().await;
                let body_bytes = body_result?.to_bytes();
                (body_bytes, None)
            };

            // Send request to blocking thread with streaming response sender
            let request_data = RequestData {
                method,
                path,
                headers,
                body: body_bytes,
                request_chunks_rx,
                response_tx: ResponseSender(chunk_tx),
            };

            // Send to channel (will be picked up by a blocking thread)
            if request_tx.send(request_data).await.is_err() {
                return Ok(Response::builder()
                    .status(StatusCode::SERVICE_UNAVAILABLE)
                    .body(Full::new(Bytes::from_static(b"Service unavailable")).boxed())
                    .unwrap());
            }

            // Build streaming response by consuming chunks
            // First chunk should be ResponseChunk::Start with status and headers
            let mut chunk_stream = UnboundedReceiverStream::new(chunk_rx);

            // Wait for the Start chunk
            let first_chunk = chunk_stream.next().await;
            let (status, response_headers) = match first_chunk {
                Some(ResponseChunk::Start { status, headers }) => (status, headers),
                _ => {
                    // Error: first chunk must be Start
                    return Ok(Response::builder()
                        .status(StatusCode::INTERNAL_SERVER_ERROR)
                        .body(
                            Full::new(Bytes::from_static(b"Protocol error: expected Start chunk"))
                                .boxed(),
                        )
                        .unwrap());
                }
            };

            // Build HTTP response with streaming body
            let mut resp_builder = Response::builder()
                .status(StatusCode::from_u16(status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR));

            // Add response headers
            if let Some(headers_mut) = resp_builder.headers_mut() {
                for (key, value) in response_headers.iter() {
                    if let Ok(value) = HeaderValue::from_str(value) {
                        if let Ok(key) = key.parse::<http::header::HeaderName>() {
                            headers_mut.append(key, value);
                        }
                    }
                }
            }

            // Create streaming body from remaining chunks
            let body_stream = chunk_stream.map(|chunk| match chunk {
                ResponseChunk::Body { data, .. } => Ok(Frame::data(Bytes::from(data))),
                ResponseChunk::Trailers { trailers } => {
                    // Convert trailers to HeaderMap
                    let mut trailer_map = HeaderMap::new();
                    for (key, value) in trailers {
                        if let Ok(name) = HeaderName::from_bytes(key.as_bytes()) {
                            if let Ok(val) = HeaderValue::from_str(&value) {
                                trailer_map.insert(name, val);
                            }
                        }
                    }
                    Ok(Frame::trailers(trailer_map))
                }
                _ => Ok(Frame::data(Bytes::new())), // Unexpected chunk type, ignore
            });

            let streaming_body = StreamBody::new(body_stream).boxed();

            Ok(resp_builder.body(streaming_body).unwrap())
        })
    }
}
