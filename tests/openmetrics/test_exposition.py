import math
import time
import unittest

from prometheus_client import (
    CollectorRegistry, Counter, Enum, Gauge, Histogram, Info, Metric, Summary,
)
from prometheus_client.core import (
    Exemplar, GaugeHistogramMetricFamily, Timestamp,
)
from prometheus_client.openmetrics.exposition import (
    generate_latest, generate_nh,
)


class TestGenerateText(unittest.TestCase):
    def setUp(self):
        self.registry = CollectorRegistry()

        # Mock time so _created values are fixed.
        self.old_time = time.time
        time.time = lambda: 123.456

    def tearDown(self):
        time.time = self.old_time

    def custom_collector(self, metric_family):
        class CustomCollector:
            def collect(self):
                return [metric_family]

        self.registry.register(CustomCollector())

    def test_counter(self):
        c = Counter('cc', 'A counter', registry=self.registry)
        c.inc()
        self.assertEqual(b'# HELP cc A counter\n# TYPE cc counter\ncc_total 1.0\ncc_created 123.456\n# EOF\n',
                         generate_latest(self.registry))
        
    def test_counter_utf8(self):
        c = Counter('cc.with.dots', 'A counter', registry=self.registry)
        c.inc()
        self.assertEqual(b'# HELP "cc.with.dots" A counter\n# TYPE "cc.with.dots" counter\n{"cc.with.dots_total"} 1.0\n{"cc.with.dots_created"} 123.456\n# EOF\n',
                         generate_latest(self.registry))

    def test_counter_total(self):
        c = Counter('cc_total', 'A counter', registry=self.registry)
        c.inc()
        self.assertEqual(b'# HELP cc A counter\n# TYPE cc counter\ncc_total 1.0\ncc_created 123.456\n# EOF\n',
                         generate_latest(self.registry))

    def test_counter_unit(self):
        c = Counter('cc_seconds', 'A counter', registry=self.registry, unit="seconds")
        c.inc()
        self.assertEqual(b'# HELP cc_seconds A counter\n# TYPE cc_seconds counter\n# UNIT cc_seconds seconds\ncc_seconds_total 1.0\ncc_seconds_created 123.456\n# EOF\n',
                         generate_latest(self.registry))

    def test_gauge(self):
        g = Gauge('gg', 'A gauge', registry=self.registry)
        g.set(17)
        self.assertEqual(b'# HELP gg A gauge\n# TYPE gg gauge\ngg 17.0\n# EOF\n', generate_latest(self.registry))

    def test_summary(self):
        s = Summary('ss', 'A summary', ['a', 'b'], registry=self.registry)
        s.labels('c', 'd').observe(17)
        self.assertEqual(b"""# HELP ss A summary
# TYPE ss summary
ss_count{a="c",b="d"} 1.0
ss_sum{a="c",b="d"} 17.0
ss_created{a="c",b="d"} 123.456
# EOF
""", generate_latest(self.registry))

    def test_histogram(self):
        s = Histogram('hh', 'A histogram', registry=self.registry)
        s.observe(0.05)
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh_bucket{le="0.005"} 0.0
hh_bucket{le="0.01"} 0.0
hh_bucket{le="0.025"} 0.0
hh_bucket{le="0.05"} 1.0
hh_bucket{le="0.075"} 1.0
hh_bucket{le="0.1"} 1.0
hh_bucket{le="0.25"} 1.0
hh_bucket{le="0.5"} 1.0
hh_bucket{le="0.75"} 1.0
hh_bucket{le="1.0"} 1.0
hh_bucket{le="2.5"} 1.0
hh_bucket{le="5.0"} 1.0
hh_bucket{le="7.5"} 1.0
hh_bucket{le="10.0"} 1.0
hh_bucket{le="+Inf"} 1.0
hh_count 1.0
hh_sum 0.05
hh_created 123.456
# EOF
""", generate_latest(self.registry))

    def test_histogram_negative_buckets(self):
        s = Histogram('hh', 'A histogram', buckets=[-1, -0.5, 0, 0.5, 1], registry=self.registry)
        s.observe(-0.5)
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh_bucket{le="-1.0"} 0.0
hh_bucket{le="-0.5"} 1.0
hh_bucket{le="0.0"} 1.0
hh_bucket{le="0.5"} 1.0
hh_bucket{le="1.0"} 1.0
hh_bucket{le="+Inf"} 1.0
hh_count 1.0
hh_created 123.456
# EOF
""", generate_latest(self.registry))

    def test_histogram_exemplar(self):
        s = Histogram('hh', 'A histogram', buckets=[1, 2, 3, 4], registry=self.registry)
        s.observe(0.5, {'a': 'b'})
        s.observe(1.5, {'le': '7'})
        s.observe(2.5, {'a': 'b'})
        s.observe(3.5, {'a': '\n"\\'})
        print(generate_latest(self.registry))
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh_bucket{le="1.0"} 1.0 # {a="b"} 0.5 123.456
hh_bucket{le="2.0"} 2.0 # {le="7"} 1.5 123.456
hh_bucket{le="3.0"} 3.0 # {a="b"} 2.5 123.456
hh_bucket{le="4.0"} 4.0 # {a="\\n\\"\\\\"} 3.5 123.456
hh_bucket{le="+Inf"} 4.0
hh_count 4.0
hh_sum 8.0
hh_created 123.456
# EOF
""", generate_latest(self.registry))

    def test_hybrid_histogram_native_suppressed(self):
        s = Histogram('hh', 'A histogram', registry=self.registry, native=True)
        s.observe(0.05)
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh_bucket{le="0.005"} 0.0
hh_bucket{le="0.01"} 0.0
hh_bucket{le="0.025"} 0.0
hh_bucket{le="0.05"} 1.0
hh_bucket{le="0.075"} 1.0
hh_bucket{le="0.1"} 1.0
hh_bucket{le="0.25"} 1.0
hh_bucket{le="0.5"} 1.0
hh_bucket{le="0.75"} 1.0
hh_bucket{le="1.0"} 1.0
hh_bucket{le="2.5"} 1.0
hh_bucket{le="5.0"} 1.0
hh_bucket{le="7.5"} 1.0
hh_bucket{le="10.0"} 1.0
hh_bucket{le="+Inf"} 1.0
hh_count 1.0
hh_sum 0.05
hh_created 123.456
# EOF
""", generate_latest(self.registry))

    def test_hybrid_histogram(self):
        s = Histogram('hh', 'A histogram', registry=self.registry, native=True)
        s.observe(0.05)
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh {sum:0.05,count:1,schema:3,zero_threshold:1.52587890625e-05,zero_count:0,positive_spans:[-35:1],positive_deltas:[1]}
hh_bucket{le="0.005"} 0.0
hh_bucket{le="0.01"} 0.0
hh_bucket{le="0.025"} 0.0
hh_bucket{le="0.05"} 1.0
hh_bucket{le="0.075"} 1.0
hh_bucket{le="0.1"} 1.0
hh_bucket{le="0.25"} 1.0
hh_bucket{le="0.5"} 1.0
hh_bucket{le="0.75"} 1.0
hh_bucket{le="1.0"} 1.0
hh_bucket{le="2.5"} 1.0
hh_bucket{le="5.0"} 1.0
hh_bucket{le="7.5"} 1.0
hh_bucket{le="10.0"} 1.0
hh_bucket{le="+Inf"} 1.0
hh_count 1.0
hh_sum 0.05
hh_created 123.456
# EOF
""", generate_nh(self.registry))

    def test_native_histogram(self):
        s = Histogram('hh', 'A histogram', registry=self.registry, classic=False, native=True)
        s.observe(0.5)
        s.observe(1.5)
        s.observe(0.5)
        s.observe(2.5)
        s.observe(0.5)
        s.observe(3.5)
        s.observe(0.5)
        s.observe(0.0)
        s.observe(3.6)
        s.observe(3.9)
        print(generate_nh(self.registry))
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh {sum:17.0,count:10,schema:3,zero_threshold:1.52587890625e-05,zero_count:1,positive_spans:[-9:1,12:1,5:1,3:2],positive_deltas:[4,-3,0,1,-1]}
hh_created 123.456
# EOF
""", generate_nh(self.registry))

    def test_native_histogram_bucket_boundaries(self):
        """
        Let base be `2**2**-schema`.
        In OTel the i-th bucket is of the shape `( base**i, base**(i+1) ]`.

        See: https://opentelemetry.io/docs/specs/otel/metrics/data-model/#exponential-buckets
        """
        s = Histogram('hh', 'A histogram', registry=self.registry, classic=False, native=True)

        s.observe(math.nextafter(1, -math.inf))
        s.observe(1)

        s.observe(math.nextafter(1, math.inf))
        s.observe(1.09050)
        s.observe(math.nextafter(2**2**-3, -math.inf))

        # The boundary is at 2**2**-3 == 1.0905077326652577
        # which due to rounding issues falls into the next bucket.
        s.observe(2**2**-3)

        s.observe(1.09051)
        s.observe(1.09052)

        s.observe(math.nextafter(2, -math.inf))
        s.observe(2)

        s.observe(math.nextafter(2, math.inf))
        s.observe(math.nextafter(math.nextafter(2, math.inf), math.inf))

        # Expected result is (bucket:count)     -1:2 0:4 1:2 7:2 8:2
        # but because of rounding errors we get -1:2 0:3 1:3 7:2 8:2

        print(generate_nh(self.registry))
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh {sum:16.452545465330516,count:12,schema:3,zero_threshold:1.52587890625e-05,zero_count:0,positive_spans:[-1:3,5:2],positive_deltas:[2,1,0,-1,0]}
hh_created 123.456
# EOF
""", generate_nh(self.registry))

    def test_native_histogram_resolution_shrink(self):
        s3 = Histogram('hh3', 'A histogram scale 3 reduced to 2', registry=self.registry, classic=False, native=True, nh_max_populated_buckets=50)
        s2 = Histogram('hh2', 'A histogram scale 2', registry=self.registry, classic=False, native=True, nh_bucket_factor=1.2)

        # test negative buckets
        s2.observe(0.5)
        s2.observe(0.51)
        s3.observe(0.5)
        s3.observe(0.51)

        for i in range(500):
            s2.observe(i)
            s3.observe(i)

        print(generate_nh(self.registry))
        self.assertEqual(b"""# HELP hh3 A histogram scale 3 reduced to 2
# TYPE hh3 histogram
hh3 {sum:124751.01000000001,count:502,schema:2,zero_threshold:1.52587890625e-05,zero_count:1,positive_spans:[-5:2,2:1,3:1,2:2,1:27],positive_deltas:[1,0,0,0,0,0,0,0,1,-1,1,0,1,0,0,1,2,0,1,1,3,1,2,3,4,3,5,5,7,7,10,10,1]}
hh3_created 123.456
# HELP hh2 A histogram scale 2
# TYPE hh2 histogram
hh2 {sum:124751.01000000001,count:502,schema:2,zero_threshold:1.52587890625e-05,zero_count:1,positive_spans:[-5:2,2:1,3:1,2:2,1:27],positive_deltas:[1,0,0,0,0,0,0,0,1,-1,1,0,1,0,0,1,2,0,1,1,3,1,2,3,4,3,5,5,7,7,10,10,1]}
hh2_created 123.456
# EOF
""", generate_nh(self.registry))

    def test_native_histogram_reset(self):
        s = Histogram('hh', 'A histogram', registry=self.registry, classic=False, native=True, nh_min_reset_duration_seconds=1, nh_max_populated_buckets=50)
        for i in range(500):
            s.observe(i)
        time.sleep(1.01)
        s.observe(2)
        print(generate_nh(self.registry))
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh {sum:2.0,count:1,schema:3,zero_threshold:1.52587890625e-05,zero_count:0,positive_spans:[7:1],positive_deltas:[1]}
hh_created 123.456
# EOF
""", generate_nh(self.registry))

    def test_native_histogram_zero_threshold(self):
        s = Histogram('hh', 'A histogram', registry=self.registry, classic=False, native=True, nh_zero_threshold=0.5)
        s.observe(0.5)
        print(generate_nh(self.registry))
        self.assertEqual(b"""# HELP hh A histogram
# TYPE hh histogram
hh {sum:0.5,count:1,schema:3,zero_threshold:0.5,zero_count:1,positive_spans:[],positive_deltas:[]}
hh_created 123.456
# EOF
""", generate_nh(self.registry))

    def test_counter_exemplar(self):
        c = Counter('cc', 'A counter', registry=self.registry)
        c.inc(exemplar={'a': 'b'})
        self.assertEqual(b"""# HELP cc A counter
# TYPE cc counter
cc_total 1.0 # {a="b"} 1.0 123.456
cc_created 123.456
# EOF
""", generate_latest(self.registry))

    def test_untyped_exemplar(self):
        class MyCollector:
            def collect(self):
                metric = Metric("hh", "help", 'untyped')
                # This is not sane, but it covers all the cases.
                metric.add_sample("hh_bucket", {}, 0, None, Exemplar({'a': 'b'}, 0.5))
                yield metric

        self.registry.register(MyCollector())
        with self.assertRaises(ValueError):
            generate_latest(self.registry)

    def test_histogram_non_bucket_exemplar(self):
        class MyCollector:
            def collect(self):
                metric = Metric("hh", "help", 'histogram')
                # This is not sane, but it covers all the cases.
                metric.add_sample("hh_count", {}, 0, None, Exemplar({'a': 'b'}, 0.5))
                yield metric

        self.registry.register(MyCollector())
        with self.assertRaises(ValueError):
            generate_latest(self.registry)

    def test_counter_non_total_exemplar(self):
        class MyCollector:
            def collect(self):
                metric = Metric("cc", "A counter", 'counter')
                metric.add_sample("cc_total", {}, 1, None, None)
                metric.add_sample("cc_created", {}, 123.456, None, Exemplar({'a': 'b'}, 1.0, 123.456))
                yield metric

        self.registry.register(MyCollector())
        with self.assertRaises(ValueError):
            generate_latest(self.registry)

    def test_gaugehistogram(self):
        self.custom_collector(
            GaugeHistogramMetricFamily('gh', 'help', buckets=[('1.0', 4), ('+Inf', (5))], gsum_value=7))
        self.assertEqual(b"""# HELP gh help
# TYPE gh gaugehistogram
gh_bucket{le="1.0"} 4.0
gh_bucket{le="+Inf"} 5.0
gh_gcount 5.0
gh_gsum 7.0
# EOF
""", generate_latest(self.registry))

    def test_gaugehistogram_negative_buckets(self):
        self.custom_collector(
            GaugeHistogramMetricFamily('gh', 'help', buckets=[('-1.0', 4), ('+Inf', (5))], gsum_value=-7))
        self.assertEqual(b"""# HELP gh help
# TYPE gh gaugehistogram
gh_bucket{le="-1.0"} 4.0
gh_bucket{le="+Inf"} 5.0
gh_gcount 5.0
gh_gsum -7.0
# EOF
""", generate_latest(self.registry))

    def test_info(self):
        i = Info('ii', 'A info', ['a', 'b'], registry=self.registry)
        i.labels('c', 'd').info({'foo': 'bar'})
        self.assertEqual(b"""# HELP ii A info
# TYPE ii info
ii_info{a="c",b="d",foo="bar"} 1.0
# EOF
""", generate_latest(self.registry))

    def test_enum(self):
        i = Enum('ee', 'An enum', ['a', 'b'], registry=self.registry, states=['foo', 'bar'])
        i.labels('c', 'd').state('bar')
        self.assertEqual(b"""# HELP ee An enum
# TYPE ee stateset
ee{a="c",b="d",ee="foo"} 0.0
ee{a="c",b="d",ee="bar"} 1.0
# EOF
""", generate_latest(self.registry))

    def test_unicode(self):
        c = Counter('cc', '\u4500', ['l'], registry=self.registry)
        c.labels('\u4500').inc()
        self.assertEqual(b"""# HELP cc \xe4\x94\x80
# TYPE cc counter
cc_total{l="\xe4\x94\x80"} 1.0
cc_created{l="\xe4\x94\x80"} 123.456
# EOF
""", generate_latest(self.registry))

    def test_escaping(self):
        c = Counter('cc', 'A\ncount\\er\"', ['a'], registry=self.registry)
        c.labels('\\x\n"').inc(1)
        self.assertEqual(b"""# HELP cc A\\ncount\\\\er\\"
# TYPE cc counter
cc_total{a="\\\\x\\n\\""} 1.0
cc_created{a="\\\\x\\n\\""} 123.456
# EOF
""", generate_latest(self.registry))

    def test_nonnumber(self):
        class MyNumber:
            def __repr__(self):
                return "MyNumber(123)"

            def __float__(self):
                return 123.0

        class MyCollector:
            def collect(self):
                metric = Metric("nonnumber", "Non number", 'untyped')
                metric.add_sample("nonnumber", {}, MyNumber())
                yield metric

        self.registry.register(MyCollector())
        self.assertEqual(b'# HELP nonnumber Non number\n# TYPE nonnumber unknown\nnonnumber 123.0\n# EOF\n',
                         generate_latest(self.registry))

    def test_timestamp(self):
        class MyCollector:
            def collect(self):
                metric = Metric("ts", "help", 'unknown')
                metric.add_sample("ts", {"foo": "a"}, 0, 123.456)
                metric.add_sample("ts", {"foo": "b"}, 0, -123.456)
                metric.add_sample("ts", {"foo": "c"}, 0, 123)
                metric.add_sample("ts", {"foo": "d"}, 0, Timestamp(123, 456000000))
                metric.add_sample("ts", {"foo": "e"}, 0, Timestamp(123, 456000))
                metric.add_sample("ts", {"foo": "f"}, 0, Timestamp(123, 456))
                yield metric

        self.registry.register(MyCollector())
        self.assertEqual(b"""# HELP ts help
# TYPE ts unknown
ts{foo="a"} 0.0 123.456
ts{foo="b"} 0.0 -123.456
ts{foo="c"} 0.0 123
ts{foo="d"} 0.0 123.456000000
ts{foo="e"} 0.0 123.000456000
ts{foo="f"} 0.0 123.000000456
# EOF
""", generate_latest(self.registry))


if __name__ == '__main__':
    unittest.main()
