from collections import Counter
from datetime import datetime, timedelta
from math import floor, frexp, ldexp, log
import os
from threading import Lock
from typing import Dict, List, Optional, Tuple
import warnings

from .mmap_dict import mmap_key, MmapedDict
from .samples import BucketSpan, NativeHistogram

LOG2E = 1.44269504088896340735


class ThreadSafeNativeHistogram:
    """A native histogram protected by a lock."""

    _multiprocess = False

    def __init__(self, schema: int, zero_threshold: float, max_populated_buckets: int, min_reset_duration_seconds: int):
        self._lock = Lock()

        self._sum = 0.0
        self._initial_schema = schema
        self._schema = schema
        self._zero_threshold = zero_threshold
        self._zero_count = 0
        self._positive_buckets: Counter = Counter()

        self._max_populated_buckets = max_populated_buckets
        self._min_reset_duration = timedelta(seconds=min_reset_duration_seconds)
        self._last_reset = datetime.now()

    @staticmethod
    def calculate_bucket(schema: int, value: float) -> int:
        """
        Please carefully read:
        https://opentelemetry.io/docs/specs/otel/metrics/data-model/#producer-expectations
        """
        frac, exp = frexp(value)
        if schema <= 0:
            return (exp - 2 if frac == 0.5 else exp - 1) >> -schema
        else:
            if frac == 0.5:
                return ((exp - 1) << schema) - 1
            else:
                return floor(log(value) * ldexp(LOG2E, schema))

    def add_observation(self, value: float) -> None:
        if value < 0:
            raise ValueError('native histograms currently do not support negative observations')

        with self._lock:
            if value <= self._zero_threshold:
                self._zero_count += 1
                self._sum += value
                return

            if self._schema != self._initial_schema and self._last_reset + self._min_reset_duration < datetime.now():
                self._reset()
            self._sum += value
            self._positive_buckets[self.calculate_bucket(self._schema, value)] += 1
            if len(self._positive_buckets) > self._max_populated_buckets:
                if self._last_reset + self._min_reset_duration < datetime.now():
                    self._reset()
                else:
                    self._reduce_resolution()

    def _reset(self) -> None:
        """reset native histogram

        lock must be held by caller
        """
        self._sum = 0
        self._zero_count = 0
        self._schema = self._initial_schema
        self._positive_buckets.clear()
        self._last_reset = datetime.now()

    def _reduce_resolution(self) -> None:
        """reduce the resolution of the native histogram

        lock must be held by caller
        """
        if self._schema == -4:
            raise ValueError("can not reduce the histogram resolution beyond -4")

        self._schema -= 1

        new_counter: Counter = Counter()
        for bucket, count in self._positive_buckets.items():
            new_counter[bucket // 2] += count
        self._positive_buckets = new_counter

    @staticmethod
    def _buckets_delta_encoding(counter: Dict[int, int]) -> Tuple[List[BucketSpan], List[int]]:
        spans: List[BucketSpan] = []
        deltas: List[int] = []
        last_bucket: Optional[int] = None
        last_count: int = 0

        for bucket, count in sorted(filter(lambda kv: kv[1], counter.items())):
            if last_bucket is None:
                spans.append(BucketSpan(bucket, 1))
            elif last_bucket + 1 == bucket:
                spans[-1] = BucketSpan(spans[-1].offset, spans[-1].length + 1)
            else:
                spans.append(BucketSpan(bucket - last_bucket - 1, 1))

            deltas.append(count - last_count)
            last_bucket = bucket
            last_count = count

        return spans, deltas

    def extract(self) -> NativeHistogram:
        with self._lock:
            pos_spans, pos_deltas = self._buckets_delta_encoding(self._positive_buckets)

            return NativeHistogram(
                count_value=sum(self._positive_buckets.values()) + self._zero_count,
                sum_value=self._sum,
                schema=self._schema,
                zero_threshold=self._zero_threshold,
                zero_count=self._zero_count,
                pos_spans=pos_spans,
                pos_deltas=pos_deltas,
            )


class MutexValue:
    """A float protected by a mutex."""

    _multiprocess = False

    def __init__(self, typ, metric_name, name, labelnames, labelvalues, help_text, **kwargs):
        self._value = 0.0
        self._exemplar = None
        self._lock = Lock()

    def inc(self, amount):
        with self._lock:
            self._value += amount

    def set(self, value, timestamp=None):
        with self._lock:
            self._value = value

    def set_exemplar(self, exemplar):
        with self._lock:
            self._exemplar = exemplar

    def get(self):
        with self._lock:
            return self._value

    def get_exemplar(self):
        with self._lock:
            return self._exemplar


def MultiProcessValue(process_identifier=os.getpid):
    """Returns a MmapedValue class based on a process_identifier function.

    The 'process_identifier' function MUST comply with this simple rule:
    when called in simultaneously running processes it MUST return distinct values.

    Using a different function than the default 'os.getpid' is at your own risk.
    """
    files = {}
    values = []
    pid = {'value': process_identifier()}
    # Use a single global lock when in multi-processing mode
    # as we presume this means there is no threading going on.
    # This avoids the need to also have mutexes in __MmapDict.
    lock = Lock()

    class MmapedValue:
        """A float protected by a mutex backed by a per-process mmaped file."""

        _multiprocess = True

        def __init__(self, typ, metric_name, name, labelnames, labelvalues, help_text, multiprocess_mode='', **kwargs):
            self._params = typ, metric_name, name, labelnames, labelvalues, help_text, multiprocess_mode
            # This deprecation warning can go away in a few releases when removing the compatibility
            if 'prometheus_multiproc_dir' in os.environ and 'PROMETHEUS_MULTIPROC_DIR' not in os.environ:
                os.environ['PROMETHEUS_MULTIPROC_DIR'] = os.environ['prometheus_multiproc_dir']
                warnings.warn("prometheus_multiproc_dir variable has been deprecated in favor of the upper case naming PROMETHEUS_MULTIPROC_DIR", DeprecationWarning)
            with lock:
                self.__check_for_pid_change()
                self.__reset()
                values.append(self)

        def __reset(self):
            typ, metric_name, name, labelnames, labelvalues, help_text, multiprocess_mode = self._params
            if typ == 'gauge':
                file_prefix = typ + '_' + multiprocess_mode
            else:
                file_prefix = typ
            if file_prefix not in files:
                filename = os.path.join(
                    os.environ.get('PROMETHEUS_MULTIPROC_DIR'),
                    '{}_{}.db'.format(file_prefix, pid['value']))

                files[file_prefix] = MmapedDict(filename)
            self._file = files[file_prefix]
            self._key = mmap_key(metric_name, name, labelnames, labelvalues, help_text)
            self._value, self._timestamp = self._file.read_value(self._key)

        def __check_for_pid_change(self):
            actual_pid = process_identifier()
            if pid['value'] != actual_pid:
                pid['value'] = actual_pid
                # There has been a fork(), reset all the values.
                for f in files.values():
                    f.close()
                files.clear()
                for value in values:
                    value.__reset()

        def inc(self, amount):
            with lock:
                self.__check_for_pid_change()
                self._value += amount
                self._timestamp = 0.0
                self._file.write_value(self._key, self._value, self._timestamp)

        def set(self, value, timestamp=None):
            with lock:
                self.__check_for_pid_change()
                self._value = value
                self._timestamp = timestamp or 0.0
                self._file.write_value(self._key, self._value, self._timestamp)

        def set_exemplar(self, exemplar):
            # TODO: Implement exemplars for multiprocess mode.
            return

        def get(self):
            with lock:
                self.__check_for_pid_change()
                return self._value

        def get_exemplar(self):
            # TODO: Implement exemplars for multiprocess mode.
            return None

    return MmapedValue


def get_value_class():
    # Should we enable multi-process mode?
    # This needs to be chosen before the first metric is constructed,
    # and as that may be in some arbitrary library the user/admin has
    # no control over we use an environment variable.
    if 'prometheus_multiproc_dir' in os.environ or 'PROMETHEUS_MULTIPROC_DIR' in os.environ:
        return MultiProcessValue()
    else:
        return MutexValue


ValueClass = get_value_class()
