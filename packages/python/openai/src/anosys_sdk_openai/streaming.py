"""
Streaming response utilities for OpenAI.

Provides utilities for handling and aggregating streaming responses.
"""

from typing import Any, Iterator, List


class StreamingAggregator:
    """
    Aggregates streaming response chunks into a complete response.
    
    Can be used to collect streaming output for logging purposes.
    """
    
    def __init__(self):
        self.chunks: List[Any] = []
        self.content_parts: List[str] = []
    
    def add_chunk(self, chunk: Any) -> None:
        """Add a chunk to the aggregator."""
        self.chunks.append(chunk)
        
        # Try to extract content from the chunk
        try:
            if hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    self.content_parts.append(delta.content)
        except (AttributeError, IndexError):
            pass
    
    def get_content(self) -> str:
        """Get the aggregated content as a string."""
        return "".join(self.content_parts)
    
    def get_chunks(self) -> List[Any]:
        """Get all collected chunks."""
        return self.chunks


def aggregate_stream(stream: Iterator[Any]) -> tuple:
    """
    Iterate through a stream, collecting chunks and yielding them.
    
    Args:
        stream: Iterator of stream chunks
        
    Yields:
        Each chunk from the stream
        
    Returns:
        Tuple of (aggregated_content, chunk_list)
    """
    aggregator = StreamingAggregator()
    
    for chunk in stream:
        aggregator.add_chunk(chunk)
        yield chunk
    
    return aggregator.get_content(), aggregator.get_chunks()
