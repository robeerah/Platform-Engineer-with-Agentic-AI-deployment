# Extra settings layered on top of `nomad agent -dev`.
# Exposes Nomad metrics in Prometheus format at /v1/metrics?format=prometheus

telemetry {
  collection_interval        = "10s"
  disable_hostname           = true
  prometheus_metrics         = true
  publish_allocation_metrics = true
  publish_node_metrics       = true
}

consul {
  address = "127.0.0.1:8500"
}

plugin "docker" {
  config {
    volumes {
      enabled = false
    }
  }
}
