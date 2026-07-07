"""
Lucid Lineage — OpenTelemetry Instrumentation.

Provides native observability and tracing for the GraphRAG architecture.
Tracks tool invocations, database query latency, and overall system utilization.
Currently uses a ConsoleSpanExporter for local development, which can be
swapped out for an OTLP exporter (e.g., to Google Cloud Trace) in production.
"""

import logging
from functools import wraps
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

log = logging.getLogger("lucid_lineage.telemetry")

_is_initialized = False

def init_telemetry():
    """Initialize the OpenTelemetry provider and exporters."""
    global _is_initialized
    if _is_initialized:
        return

    resource = Resource(attributes={
        SERVICE_NAME: "lucid-lineage-agent"
    })

    provider = TracerProvider(resource=resource)
    
    # Export to console for PoC observability.
    # In production, this would be an OTLP/gRPC exporter to Vertex/GCP.
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    _is_initialized = True
    log.info("OpenTelemetry initialization complete.")

def get_tracer():
    """Get the application's named tracer."""
    if not _is_initialized:
        init_telemetry()
    return trace.get_tracer("lucid_lineage.tracer")

def trace_tool(name=None):
    """Decorator to trace tool execution, latency, and operational metrics."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            span_name = name or func.__name__
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("tool.name", func.__name__)
                span.set_attribute("tool.module", func.__module__)
                
                # Log non-sensitive arguments for auditability
                for k, v in kwargs.items():
                    if k not in ['password', 'secret', 'key']:
                        span.set_attribute(f"tool.args.{k}", str(v))
                
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("tool.status", "SUCCESS")
                    return result
                except Exception as e:
                    span.set_attribute("tool.status", "FAILED")
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator
