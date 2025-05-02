import unittest

from prometheus_client.samples import BucketSpan
from prometheus_client.values import ThreadSafeNativeHistogram


class TestValues(unittest.TestCase):

    def test_buckets_delta_encoding(self):
        inp = {-2: 3, -1: 5, 0: 0, 1: 0, 2: 1, 3: 0, 4: 3, 5: 2}
        got = ThreadSafeNativeHistogram._buckets_delta_encoding(inp)
        want = [BucketSpan(-2, 2), BucketSpan(2, 1), BucketSpan(1, 2)], [3, 2, -4, 2, -1]
        print(got)
        self.assertEqual(got, want)
