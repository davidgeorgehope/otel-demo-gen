"""
Database metrics generator following OTel database semantic conventions.
Generates connection pool, query performance, and replication metrics.

Reference: https://opentelemetry.io/docs/specs/semconv/database/database-metrics/
"""
import secrets
import random
import time
import uuid
from typing import Dict, List, Any, Optional

from config_schema import ScenarioConfig, Database
from correlation_manager import CorrelationManager
from base_infra_generator import BaseInfrastructureGenerator


class DatabaseMetricsGenerator(BaseInfrastructureGenerator):
    """
    Generates database metrics following OTel db.client.* conventions.
    Supports PostgreSQL, MySQL, MongoDB, Redis, and other database types.
    """

    # Database type configurations
    DB_CONFIGS = {
        "postgresql": {
            "port": 5432,
            "max_connections": 100,
            "typical_query_time_ms": (1, 50),
            "supports_replication": True,
        },
        "postgres": {
            "port": 5432,
            "max_connections": 100,
            "typical_query_time_ms": (1, 50),
            "supports_replication": True,
        },
        "mysql": {
            "port": 3306,
            "max_connections": 150,
            "typical_query_time_ms": (1, 40),
            "supports_replication": True,
        },
        "mongodb": {
            "port": 27017,
            "max_connections": 200,
            "typical_query_time_ms": (1, 30),
            "supports_replication": True,
        },
        "redis": {
            "port": 6379,
            "max_connections": 1000,
            "typical_query_time_ms": (0.1, 2),
            "supports_replication": True,
        },
        "elasticsearch": {
            "port": 9200,
            "max_connections": 100,
            "typical_query_time_ms": (5, 100),
            "supports_replication": True,
        },
        "cassandra": {
            "port": 9042,
            "max_connections": 500,
            "typical_query_time_ms": (2, 30),
            "supports_replication": True,
        },
        "dynamodb": {
            "port": 443,
            "max_connections": 50,
            "typical_query_time_ms": (5, 50),
            "supports_replication": False,
        },
        "sqlserver": {
            "port": 1433,
            "max_connections": 100,
            "typical_query_time_ms": (2, 60),
            "supports_replication": True,
        },
    }

    def __init__(self, config: ScenarioConfig, correlation_manager: Optional[CorrelationManager] = None):
        super().__init__(config, correlation_manager)

        # Get databases from config
        self.databases: List[Database] = config.databases or []

        self._db_data = self._initialize_db_data()
        self._counters = self._initialize_counters()

    def _initialize_db_data(self) -> Dict[str, Dict[str, Any]]:
        """Initialize static database data."""
        db_data = {}

        for db in self.databases:
            db_type = db.type.lower()
            config = self.DB_CONFIGS.get(db_type, self.DB_CONFIGS["postgresql"])

            db_data[db.name] = {
                "db_id": str(uuid.uuid4()),
                "db_type": db_type,
                "port": config["port"],
                "max_connections": config["max_connections"],
                "typical_query_time_ms": config["typical_query_time_ms"],
                "supports_replication": config["supports_replication"],
                "ip_address": f"10.{random.randint(100, 200)}.{random.randint(1, 254)}.{random.randint(1, 254)}",
                "version": self._get_db_version(db_type),
                "is_primary": random.random() > 0.3,  # 70% chance of being primary
            }

        return db_data

    def _get_db_version(self, db_type: str) -> str:
        """Get a realistic version string for the database type."""
        versions = {
            "postgresql": ["14.9", "15.4", "16.1"],
            "postgres": ["14.9", "15.4", "16.1"],
            "mysql": ["8.0.35", "8.1.0", "8.2.0"],
            "mongodb": ["6.0.12", "7.0.4"],
            "redis": ["7.0.14", "7.2.3"],
            "elasticsearch": ["8.11.1", "8.12.0"],
            "cassandra": ["4.0.11", "4.1.3"],
            "dynamodb": ["2023"],
            "sqlserver": ["2019", "2022"],
        }
        return random.choice(versions.get(db_type, ["1.0.0"]))

    def _initialize_counters(self) -> Dict[str, Dict[str, Any]]:
        """Initialize counters for databases."""
        counters = {}

        for db in self.databases:
            db_info = self._db_data.get(db.name, {})
            max_conn = db_info.get("max_connections", 100)

            counters[db.name] = {
                "query_count": random.randint(1_000_000, 100_000_000),
                "query_time_sum_ms": random.randint(10_000_000, 1_000_000_000),
                "rows_affected": random.randint(10_000_000, 1_000_000_000),
                "connection_count_used": random.randint(10, int(max_conn * 0.6)),
                "connection_count_idle": random.randint(5, int(max_conn * 0.2)),
                "connection_timeouts": random.randint(0, 100),
                "errors": random.randint(0, 1000),
                "slow_queries": random.randint(0, 500),
            }

        return counters

    def generate_db_resource_attributes(self, db: Database) -> Dict[str, Any]:
        """Generate OTel resource attributes for a database."""
        db_info = self._db_data.get(db.name, {})

        attrs = {
            "service.name": db.name,
            "service.type": "database",
            "service.instance.id": db_info.get("db_id", ""),

            # Database semantic conventions
            "db.system": db.type.lower(),
            "db.name": db.name,
            "db.connection_string": f"{db.type.lower()}://{db_info.get('ip_address')}:{db_info.get('port')}/{db.name}",

            # Server attributes
            "server.address": db_info.get("ip_address", ""),
            "server.port": db_info.get("port", 5432),

            # Additional context
            "db.version": db_info.get("version", ""),
            "db.is_primary": db_info.get("is_primary", True),

            "data_stream.type": "metrics",
            "data_stream.dataset": f"database.{db.type.lower()}",
            "data_stream.namespace": "default",
        }

        # Add correlation attributes if affected
        if self.correlation_manager:
            correlation_attrs = self.correlation_manager.get_attributes_for_component(db.name)
            attrs.update(correlation_attrs)

        return attrs

    def generate_database_metrics_payload(self) -> Dict[str, List[Any]]:
        """Generate OTLP metrics payload for all databases."""
        if not self.databases:
            return {"resourceMetrics": []}

        resource_metrics = []
        current_time_ns = str(time.time_ns())

        for db in self.databases:
            db_info = self._db_data.get(db.name, {})
            db_counters = self._counters.get(db.name, {})

            # Check for incident effects
            effect = None
            if self.correlation_manager:
                effect = self.correlation_manager.get_effect_for_component(db.name)

            # Generate database metrics
            metrics = self._generate_db_metrics(
                current_time_ns, db, db_info, db_counters, effect
            )

            resource_attrs = self._format_attributes(self.generate_db_resource_attributes(db))

            resource_metrics.append({
                "resource": {
                    "attributes": resource_attrs,
                    "schemaUrl": self.SCHEMA_URL,
                },
                "scopeMetrics": [{
                    "scope": {
                        "name": "otel-demo-gen/database-metrics-receiver",
                        "version": "1.0.0",
                    },
                    "metrics": metrics,
                }],
            })

        return {"resourceMetrics": resource_metrics}

    def generate_metrics_payload(self) -> Dict[str, Any]:
        """Implementation of abstract method from BaseInfrastructureGenerator."""
        return self.generate_database_metrics_payload()

    def _generate_db_metrics(
        self,
        current_time_ns: str,
        db: Database,
        db_info: Dict[str, Any],
        db_counters: Dict[str, Any],
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate metrics for a single database."""
        metrics = []

        # Apply incident effects
        latency_multiplier = 1.0
        error_multiplier = 1.0
        connection_pressure = 1.0
        timeout_multiplier = 1.0

        if effect:
            effect_type = effect.get("effect", "")
            params = effect.get("parameters", {})

            if effect_type == "database_slow":
                latency_multiplier = params.get("latency_multiplier", 5.0)
            elif effect_type == "query_timeout":
                timeout_multiplier = params.get("timeout_multiplier", 10.0)
                latency_multiplier = 3.0
            elif effect_type == "database_errors":
                error_multiplier = params.get("error_multiplier", 10.0)
            elif effect_type == "connection_exhaustion":
                connection_pressure = params.get("connection_pressure", 1.5)

        typical_query_time = db_info.get("typical_query_time_ms", (1, 50))
        max_connections = db_info.get("max_connections", 100)

        # Connection pool metrics
        used_connections = min(
            max_connections,
            int(db_counters.get("connection_count_used", 20) * connection_pressure)
        )
        idle_connections = max(0, max_connections - used_connections - random.randint(5, 20))
        pending_requests = 0 if connection_pressure < 1.2 else random.randint(1, 20)

        metrics.extend([
            # db.client.connection.count by state
            {
                "name": "db.client.connection.count",
                "unit": "{connection}",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(used_connections),
                        "attributes": [
                            {"key": "db.client.connection.state", "value": {"stringValue": "used"}},
                        ],
                    }],
                },
            },
            {
                "name": "db.client.connection.count",
                "unit": "{connection}",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asInt": str(idle_connections),
                        "attributes": [
                            {"key": "db.client.connection.state", "value": {"stringValue": "idle"}},
                        ],
                    }],
                },
            },
            self._create_gauge_metric("db.client.connection.max", "{connection}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(max_connections),
            }]),
            self._create_gauge_metric("db.client.connection.pending_requests", "{request}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(pending_requests),
            }]),
        ])

        # Connection timeouts
        if random.random() < 0.1 * timeout_multiplier or timeout_multiplier > 1:
            timeout_increment = int(random.randint(1, 5) * timeout_multiplier)
            db_counters["connection_timeouts"] = db_counters.get("connection_timeouts", 0) + timeout_increment

        metrics.append(self._create_sum_metric("db.client.connection.timeouts", "{timeout}", True, [{
            "timeUnixNano": current_time_ns,
            "asInt": str(db_counters.get("connection_timeouts", 0)),
        }]))

        # Query metrics
        query_increment = random.randint(100, 10000)
        db_counters["query_count"] = db_counters.get("query_count", 0) + query_increment

        # Query duration
        avg_query_time = random.uniform(*typical_query_time) * latency_multiplier
        query_time_increment = int(query_increment * avg_query_time)
        db_counters["query_time_sum_ms"] = db_counters.get("query_time_sum_ms", 0) + query_time_increment

        metrics.extend([
            self._create_sum_metric("db.client.operation.count", "{operation}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(db_counters["query_count"]),
            }]),
            # Average query duration (approximation)
            self._create_gauge_metric("db.client.operation.duration.avg", "ms", [{
                "timeUnixNano": current_time_ns,
                "asDouble": avg_query_time,
            }]),
        ])

        # Query duration percentiles
        for percentile, multiplier in [("p50", 0.8), ("p95", 2.0), ("p99", 4.0)]:
            metrics.append({
                "name": "db.client.operation.duration",
                "unit": "ms",
                "gauge": {
                    "dataPoints": [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": avg_query_time * multiplier,
                        "attributes": [
                            {"key": "percentile", "value": {"stringValue": percentile}},
                        ],
                    }],
                },
            })

        # Rows affected
        rows_increment = random.randint(1000, 100000)
        db_counters["rows_affected"] = db_counters.get("rows_affected", 0) + rows_increment

        metrics.append(self._create_sum_metric("db.client.operation.rows_affected", "{row}", True, [{
            "timeUnixNano": current_time_ns,
            "asInt": str(db_counters["rows_affected"]),
        }]))

        # Slow queries
        slow_query_threshold_ms = 100
        slow_query_count = 0
        if avg_query_time > slow_query_threshold_ms:
            slow_query_count = int(query_increment * 0.1)
        elif random.random() < 0.05:
            slow_query_count = random.randint(1, 5)

        db_counters["slow_queries"] = db_counters.get("slow_queries", 0) + slow_query_count

        metrics.append(self._create_sum_metric("db.slow_queries", "{query}", True, [{
            "timeUnixNano": current_time_ns,
            "asInt": str(db_counters["slow_queries"]),
        }]))

        # Error metrics
        error_count = 0
        if random.random() < 0.02 * error_multiplier or error_multiplier > 1:
            error_count = int(random.randint(1, 10) * error_multiplier)
            db_counters["errors"] = db_counters.get("errors", 0) + error_count

        metrics.append(self._create_sum_metric("db.client.operation.errors", "{error}", True, [{
            "timeUnixNano": current_time_ns,
            "asInt": str(db_counters.get("errors", 0)),
        }]))

        # Replication metrics (if supported)
        if db_info.get("supports_replication", False):
            is_primary = db_info.get("is_primary", True)

            if not is_primary:
                # Replica lag
                replica_lag = random.uniform(0, 2)
                if effect and effect.get("effect") == "replication_lag":
                    replica_lag = effect.get("parameters", {}).get("lag_seconds", 30)

                metrics.extend([
                    self._create_gauge_metric("db.replication.lag", "s", [{
                        "timeUnixNano": current_time_ns,
                        "asDouble": replica_lag,
                    }]),
                    self._create_gauge_metric("db.replication.state", "1", [{
                        "timeUnixNano": current_time_ns,
                        "asInt": "1",  # 1 = streaming, 0 = stopped
                    }]),
                ])
            else:
                # Primary-specific metrics
                metrics.append(self._create_gauge_metric("db.replication.connected_replicas", "{replica}", [{
                    "timeUnixNano": current_time_ns,
                    "asInt": str(random.randint(1, 3)),
                }]))

        # Database-type specific metrics
        db_type = db.type.lower()

        if db_type in ["postgresql", "postgres"]:
            metrics.extend(self._generate_postgres_metrics(current_time_ns, db, effect))
        elif db_type == "mysql":
            metrics.extend(self._generate_mysql_metrics(current_time_ns, db, effect))
        elif db_type == "redis":
            metrics.extend(self._generate_redis_metrics(current_time_ns, db, effect))
        elif db_type == "mongodb":
            metrics.extend(self._generate_mongodb_metrics(current_time_ns, db, effect))

        return metrics

    def _generate_postgres_metrics(
        self,
        current_time_ns: str,
        db: Database,
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate PostgreSQL-specific metrics."""
        metrics = []

        # Transaction metrics
        metrics.extend([
            self._create_sum_metric("db.postgresql.transactions.committed", "{transaction}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(1_000_000, 100_000_000)),
            }]),
            self._create_sum_metric("db.postgresql.transactions.rolled_back", "{transaction}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(1000, 100000)),
            }]),
        ])

        # Buffer cache metrics
        cache_hit_ratio = random.uniform(0.9, 0.99)
        if effect and effect.get("effect") == "cache_miss":
            cache_hit_ratio = random.uniform(0.5, 0.7)

        metrics.append(self._create_gauge_metric("db.postgresql.buffer_cache.hit_ratio", "1", [{
            "timeUnixNano": current_time_ns,
            "asDouble": cache_hit_ratio,
        }]))

        # Dead tuples (vacuum related)
        metrics.append(self._create_gauge_metric("db.postgresql.dead_tuples", "{tuple}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(random.randint(1000, 100000)),
        }]))

        # Locks
        metrics.append(self._create_gauge_metric("db.postgresql.locks.count", "{lock}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(random.randint(10, 200)),
        }]))

        return metrics

    def _generate_mysql_metrics(
        self,
        current_time_ns: str,
        db: Database,
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate MySQL-specific metrics."""
        metrics = []

        # Thread metrics
        metrics.extend([
            self._create_gauge_metric("db.mysql.threads.running", "{thread}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(5, 50)),
            }]),
            self._create_gauge_metric("db.mysql.threads.connected", "{thread}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(20, 100)),
            }]),
        ])

        # Query cache
        metrics.append(self._create_gauge_metric("db.mysql.query_cache.hit_ratio", "1", [{
            "timeUnixNano": current_time_ns,
            "asDouble": random.uniform(0.6, 0.95),
        }]))

        # InnoDB metrics
        metrics.extend([
            self._create_gauge_metric("db.mysql.innodb.buffer_pool.usage", "1", [{
                "timeUnixNano": current_time_ns,
                "asDouble": random.uniform(0.5, 0.9),
            }]),
            self._create_sum_metric("db.mysql.innodb.row_lock.waits", "{wait}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100, 10000)),
            }]),
        ])

        return metrics

    def _generate_redis_metrics(
        self,
        current_time_ns: str,
        db: Database,
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate Redis-specific metrics."""
        metrics = []

        # Memory metrics
        metrics.extend([
            self._create_gauge_metric("db.redis.memory.used", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100_000_000, 2_000_000_000)),
            }]),
            self._create_gauge_metric("db.redis.memory.peak", "By", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(500_000_000, 4_000_000_000)),
            }]),
        ])

        # Key metrics
        metrics.extend([
            self._create_gauge_metric("db.redis.keys.count", "{key}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(10000, 1000000)),
            }]),
            self._create_gauge_metric("db.redis.keys.expired", "{key}", [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100, 10000)),
            }]),
        ])

        # Hit ratio
        hit_ratio = random.uniform(0.85, 0.99)
        if effect and effect.get("effect") == "cache_miss_storm":
            hit_ratio = random.uniform(0.3, 0.6)

        metrics.append(self._create_gauge_metric("db.redis.hit_ratio", "1", [{
            "timeUnixNano": current_time_ns,
            "asDouble": hit_ratio,
        }]))

        return metrics

    def _generate_mongodb_metrics(
        self,
        current_time_ns: str,
        db: Database,
        effect: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate MongoDB-specific metrics."""
        metrics = []

        # Document metrics
        metrics.extend([
            self._create_sum_metric("db.mongodb.documents.inserted", "{document}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100000, 10000000)),
            }]),
            self._create_sum_metric("db.mongodb.documents.updated", "{document}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(100000, 10000000)),
            }]),
            self._create_sum_metric("db.mongodb.documents.deleted", "{document}", True, [{
                "timeUnixNano": current_time_ns,
                "asInt": str(random.randint(10000, 1000000)),
            }]),
        ])

        # Cursor metrics
        metrics.append(self._create_gauge_metric("db.mongodb.cursors.open", "{cursor}", [{
            "timeUnixNano": current_time_ns,
            "asInt": str(random.randint(10, 500)),
        }]))

        # WiredTiger cache
        metrics.append(self._create_gauge_metric("db.mongodb.wiredtiger.cache.usage", "1", [{
            "timeUnixNano": current_time_ns,
            "asDouble": random.uniform(0.4, 0.85),
        }]))

        return metrics

    # _create_gauge_metric, _create_sum_metric, and _format_attributes
    # are now inherited from BaseInfrastructureGenerator
