/// Response chunk types for streaming support
#[derive(Debug, Clone)]
pub enum ResponseChunk {
    /// Start the response with status and headers
    Start {
        status: u16,
        headers: Vec<(String, String)>,
    },
    /// Send a body chunk
    Body { data: Vec<u8>, more_body: bool },
    /// Send trailers (HTTP/2 or chunked HTTP/1.1)
    Trailers { trailers: Vec<(String, String)> },
}
