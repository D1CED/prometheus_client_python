#!/usr/bin/env python


from ..samples import NativeHistogram
from ..utils import floatToGoString
from ..validation import (
    _is_valid_legacy_labelname, _is_valid_legacy_metric_name,
)

CONTENT_TYPE_LATEST = 'application/openmetrics-text; version=1.0.0; charset=utf-8'
"""Content type of the latest OpenMetrics text format"""

CONTENT_TYPE_NH = 'application/openmetrics-text; version=1.1.0-nativehistogram.*; charset=utf-8'


def _is_valid_exemplar_metric(metric, sample):
    if metric.type == 'counter' and sample.name.endswith('_total'):
        return True
    if metric.type in ('gaugehistogram') and sample.name.endswith('_bucket'):
        return True
    if metric.type in ('histogram') and sample.name.endswith('_bucket') or sample.name == metric.name:
        return True
    return False


def generate_latest(registry, allow_native_histograms=False):
    '''Returns the metrics from the registry in latest text format as a string.'''
    output = []
    for metric in registry.collect():
        try:
            mname = metric.name
            output.append('# HELP {} {}\n'.format(
                escape_metric_name(mname), _escape(metric.documentation)))
            output.append(f'# TYPE {escape_metric_name(mname)} {metric.type}\n')
            if metric.unit:
                output.append(f'# UNIT {escape_metric_name(mname)} {metric.unit}\n')
            for s in metric.samples:
                if s.native_histogram is not None and not allow_native_histograms:
                    continue
                if not _is_valid_legacy_metric_name(s.name):
                    labelstr = escape_metric_name(s.name)
                    if s.labels:
                        labelstr += ', '
                else:
                    labelstr = ''
                
                if s.labels:
                    items = sorted(s.labels.items())
                    labelstr += ','.join(
                        ['{}="{}"'.format(
                            escape_label_name(k), _escape(v))
                            for k, v in items])
                if labelstr:
                    labelstr = "{" + labelstr + "}"
                    
                if s.exemplar:
                    if not _is_valid_exemplar_metric(metric, s):
                        raise ValueError(f"Metric {metric.name} has exemplars, but is not a histogram bucket or counter")
                    labels = '{{{0}}}'.format(','.join(
                        ['{}="{}"'.format(
                            k, v.replace('\\', r'\\').replace('\n', r'\n').replace('"', r'\"'))
                            for k, v in sorted(s.exemplar.labels.items())]))
                    if s.exemplar.timestamp is not None:
                        exemplarstr = ' # {} {} {}'.format(
                            labels,
                            floatToGoString(s.exemplar.value),
                            s.exemplar.timestamp,
                        )
                    else:
                        exemplarstr = ' # {} {}'.format(
                            labels,
                            floatToGoString(s.exemplar.value),
                        )
                else:
                    exemplarstr = ''
                timestamp = ''
                if s.timestamp is not None:
                    timestamp = f' {s.timestamp}'

                value = None
                if s.value is not None:
                    value = floatToGoString(s.value)
                elif s.native_histogram is not None:
                    value = native_histogram_as_str(s.native_histogram)
                else:
                    raise ValueError('sample must hold float or native_histogram')

                if _is_valid_legacy_metric_name(s.name):
                    output.append('{}{} {}{}{}\n'.format(
                        s.name,
                        labelstr,
                        value,
                        timestamp,
                        exemplarstr,
                    ))
                else:
                    output.append('{} {}{}{}\n'.format(
                        labelstr,
                        value,
                        timestamp,
                        exemplarstr,
                    ))
        except Exception as exception:
            exception.args = (exception.args or ('',)) + (metric,)
            raise

    output.append('# EOF\n')
    return ''.join(output).encode('utf-8')


def generate_nh(registry):
    return generate_latest(registry, allow_native_histograms=True)


def native_histogram_as_str(native_histogram: NativeHistogram) -> str:
    nh_sum = floatToGoString(native_histogram.sum_value)
    nh_count = int(native_histogram.count_value)
    nh_schema = native_histogram.schema
    nh_zero_threshold = floatToGoString(native_histogram.zero_threshold)
    nh_zero_count = int(native_histogram.zero_count)

    nh_pos_spans = ''
    if native_histogram.pos_spans:
        nh_pos_spans = ','.join(f'{span.offset}:{span.length}' for span in native_histogram.pos_spans)

    nh_pos_deltas = ''
    if native_histogram.pos_deltas:
        nh_pos_deltas = ','.join(map(str, native_histogram.pos_deltas))

    return f'{{sum:{nh_sum},count:{nh_count},schema:{nh_schema},zero_threshold:{nh_zero_threshold},zero_count:{nh_zero_count},positive_spans:[{nh_pos_spans}],positive_deltas:[{nh_pos_deltas}]}}'


def escape_metric_name(s: str) -> str:
    """Escapes the metric name and puts it in quotes iff the name does not
    conform to the legacy Prometheus character set.
    """
    if _is_valid_legacy_metric_name(s):
        return s
    return '"{}"'.format(_escape(s))


def escape_label_name(s: str) -> str:
    """Escapes the label name and puts it in quotes iff the name does not
    conform to the legacy Prometheus character set.
    """
    if _is_valid_legacy_labelname(s):
        return s
    return '"{}"'.format(_escape(s))


def _escape(s: str) -> str:
    """Performs backslash escaping on backslash, newline, and double-quote characters."""
    return s.replace('\\', r'\\').replace('\n', r'\n').replace('"', r'\"')
