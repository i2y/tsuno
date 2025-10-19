use pyo3::prelude::*;
use pyo3::types::PyBytes;
use tokio::sync::mpsc;

use crate::dedicated_thread_server::RequestChunk;

/// Python-accessible request receiver for streaming request bodies
#[pyclass]
pub struct RequestReceiver {
    rx: Option<mpsc::UnboundedReceiver<RequestChunk>>,
}

impl RequestReceiver {
    /// Create new RequestReceiver from channel
    pub fn new(rx: mpsc::UnboundedReceiver<RequestChunk>) -> Self {
        Self { rx: Some(rx) }
    }
}

#[pymethods]
impl RequestReceiver {
    /// Receive next chunk (blocking)
    /// Returns (data, more_body) tuple or None if stream ended
    pub fn receive_chunk(&mut self, py: Python<'_>) -> PyResult<Option<(Py<PyBytes>, bool)>> {
        if let Some(mut rx) = self.rx.take() {
            // Use blocking_recv to wait for next chunk
            let chunk = py.detach(|| {
                let rt = tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()
                    .expect("Failed to create runtime");

                rt.block_on(async { rx.recv().await })
            });

            self.rx = Some(rx);

            match chunk {
                Some(RequestChunk::Body { data, more_body }) => {
                    let py_bytes = PyBytes::new(py, &data);
                    Ok(Some((py_bytes.into(), more_body)))
                }
                Some(RequestChunk::Done) | None => Ok(None),
            }
        } else {
            Ok(None)
        }
    }

    pub fn is_closed(&self) -> bool {
        self.rx.is_none()
    }
}
