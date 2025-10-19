use pyo3::prelude::*;
use tokio::sync::mpsc;

use crate::response_chunk::ResponseChunk;

/// ResponseSender for streaming HTTP responses
#[pyclass]
pub struct ResponseSender {
    // Streaming mode: mpsc sender
    streaming_tx: mpsc::UnboundedSender<ResponseChunk>,

    // Track response state
    started: bool,
}

impl ResponseSender {
    /// Create ResponseSender in streaming mode
    pub fn new_streaming(tx: mpsc::UnboundedSender<ResponseChunk>) -> Self {
        Self {
            streaming_tx: tx,
            started: false,
        }
    }
}

#[pymethods]
impl ResponseSender {
    /// Send complete response at once (convenience method)
    /// Internally uses streaming protocol (send_start + send_chunk + optional send_trailers)
    pub fn send_response(
        &mut self,
        _py: Python<'_>,
        status: i32,
        headers: Vec<(String, String)>,
        body: &[u8],
        trailers: Option<Vec<(String, String)>>,
    ) -> PyResult<()> {
        // In streaming mode, send_response sends everything as single chunk
        self.send_start(status, headers)?;
        self.send_chunk(body, false)?;
        if let Some(t) = trailers {
            self.send_trailers(t)?;
        }
        Ok(())
    }

    /// Streaming method: Start the response with status and headers
    pub fn send_start(&mut self, status: i32, headers: Vec<(String, String)>) -> PyResult<()> {
        if self.started {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Response already started",
            ));
        }

        self.streaming_tx
            .send(ResponseChunk::Start {
                status: status as u16,
                headers,
            })
            .map_err(|_| {
                pyo3::exceptions::PyRuntimeError::new_err("Failed to send response start")
            })?;
        self.started = true;
        Ok(())
    }

    /// Streaming method: Send a body chunk
    pub fn send_chunk(&mut self, data: &[u8], more_body: bool) -> PyResult<()> {
        if !self.started {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Response not started. Call send_start() first",
            ));
        }

        self.streaming_tx
            .send(ResponseChunk::Body {
                data: data.to_vec(),
                more_body,
            })
            .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("Failed to send body chunk"))?;

        // If this was the last chunk, mark sender as consumed
        if !more_body {
            // Channel will be dropped, preventing further sends
        }

        Ok(())
    }

    /// Streaming method: Send trailers (HTTP/2 or chunked HTTP/1.1)
    pub fn send_trailers(&mut self, trailers: Vec<(String, String)>) -> PyResult<()> {
        self.streaming_tx
            .send(ResponseChunk::Trailers { trailers })
            .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("Failed to send trailers"))?;
        Ok(())
    }

    /// Check if this sender is in streaming mode
    pub fn is_streaming(&self) -> bool {
        true // Always streaming now
    }

    /// Check if response has been started
    pub fn is_started(&self) -> bool {
        self.started
    }
}
