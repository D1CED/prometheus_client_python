---
title: Histogram
weight: 4
---

Histograms track the size and number of events in buckets.
This allows for aggregatable calculation of quantiles.

```python
from prometheus_client import Histogram
h = Histogram('request_latency_seconds', 'Description of histogram')
h.observe(4.7)    # Observe 4.7 (seconds in this case)
```

The default buckets are intended to cover a typical web/rpc request from milliseconds to seconds.
They can be overridden by passing `buckets` keyword argument to `Histogram`.

There are utilities for timing code:

```python
@h.time()
def f():
  pass

with h.time():
  pass
```

## Native Histograms Text Format

You can enable the collection of observations into native histograms by setting the `native`
parameter to `True` when constructing a `Histogram`.

Native histograms and classic histograms can be used simultaneously.

```python
from prometheus_client import Histogram
h = Histogram('request_latency_seconds', 'Description of histogram', native=True)
h.observe(4.7)    # Observe 4.7 (seconds in this case)
```

Native histograms can be configured by four parameters:

1. The `nh_bucket_factor`,
2. the `nh_max_populated_buckets`,
3. the `nh_min_reset_duration`,
4. the `nh_zero_threshold`.

It is only presented to a client that advertises support for the
`application/openmetrics-text;version=1.1.0-nativehistogram.*` version.

### Limitations of the Current Native Histogram Implementation

- Only the OTel format with counter-integer type and positive observations are supported.
- Exemplars are not supported, but can be exposed in a hybrid configuration on the classic histogram.
- Floating point calculations around 0 or close to ±infinity is likely wonky.
- Multiprocessing is not supported.

    Sources:

    https://github.com/prometheus/proposals/blob/main/proposals/2024-01-29_native_histograms_text_format.md
    https://prometheus.io/docs/specs/native_histograms/
    https://opentelemetry.io/docs/specs/otel/metrics/data-model/#exponentialhistogram
