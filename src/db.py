"""
Lucid Lineage — Singleton Neo4j Connection Manager.

All modules import `get_driver()` from here instead of creating their own
driver instances. This ensures a single connection pool, proper lifecycle
management, and centralized health checking.
"""

import os
import logging
from threading import Lock
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("lucid_lineage.db")

_driver = None
_lock = Lock()


def get_driver():
    """Return the shared Neo4j driver, creating it lazily on first call.
    
    Thread-safe via double-checked locking. The driver is configured with
    a bounded connection pool and acquisition timeout to prevent resource
    exhaustion in multi-user Streamlit deployments.
    """
    global _driver
    if _driver is not None:
        return _driver

    with _lock:
        # Double-check after acquiring lock
        if _driver is not None:
            return _driver

        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")

        if not uri or not password:
            raise RuntimeError(
                "NEO4J_URI and NEO4J_PASSWORD must be set in the environment. "
                "Check your .env file."
            )

        _driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=10,
            connection_acquisition_timeout=30,
        )
        log.info("Neo4j driver initialized → %s", uri)
        return _driver


def verify_connectivity():
    """Verify the Neo4j connection is alive. Raises on failure."""
    driver = get_driver()
    driver.verify_connectivity()
    log.info("Neo4j connectivity verified.")


def close_driver():
    """Gracefully close the driver. Safe to call multiple times."""
    global _driver
    with _lock:
        if _driver is not None:
            _driver.close()
            _driver = None
            log.info("Neo4j driver closed.")
