#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <vector>

namespace {

struct Interval {
    double start;
    double end;
};

bool read_double_sequence(PyObject* value, std::vector<double>& out) {
    PyObject* seq = PySequence_Fast(value, "expected a numeric sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.clear();
    out.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        double number = PyFloat_AsDouble(item);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        if (!std::isfinite(number)) {
            number = 0.0;
        }
        out.push_back(number);
    }
    Py_DECREF(seq);
    return true;
}

int set_item(PyObject* dict, const char* key, PyObject* value) {
    if (value == nullptr) {
        return -1;
    }
    const int rc = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    return rc;
}

double round6(double value) {
    if (!std::isfinite(value)) {
        return 0.0;
    }
    return std::round(value * 1000000.0) / 1000000.0;
}

PyObject* py_global_canvas_summary(PyObject*, PyObject* args) {
    PyObject* starts_obj = nullptr;
    PyObject* ends_obj = nullptr;
    double requested_duration = 0.0;
    long requested_bin_count = 120;
    if (!PyArg_ParseTuple(args, "OOdl:global_canvas_summary", &starts_obj, &ends_obj, &requested_duration, &requested_bin_count)) {
        return nullptr;
    }

    std::vector<double> starts;
    std::vector<double> ends;
    if (!read_double_sequence(starts_obj, starts) || !read_double_sequence(ends_obj, ends)) {
        return nullptr;
    }

    const size_t count = std::min(starts.size(), ends.size());
    long invalid_duration_count = 0;
    long non_monotonic_count = 0;
    double previous_start = 0.0;
    bool has_previous = false;
    double max_end = 0.0;
    std::vector<Interval> intervals;
    intervals.reserve(count);

    for (size_t i = 0; i < count; ++i) {
        const double start = std::max(0.0, starts[i]);
        const double end = std::max(0.0, ends[i]);
        if (has_previous && start < previous_start) {
            ++non_monotonic_count;
        }
        previous_start = start;
        has_previous = true;
        max_end = std::max(max_end, end);
        if (end > start) {
            intervals.push_back({start, end});
        } else {
            ++invalid_duration_count;
        }
    }

    const double duration = std::max(std::max(0.0, requested_duration), max_end);
    const long bin_count = std::max<long>(1, std::min<long>(2048, requested_bin_count));
    const double bin_width = duration > 0.0 ? duration / static_cast<double>(bin_count) : 0.0;
    std::vector<long> bins(static_cast<size_t>(bin_count), 0);
    if (duration > 0.0) {
        for (const auto& interval : intervals) {
            const double clipped_start = std::min(std::max(0.0, interval.start), duration);
            const double clipped_end = std::min(std::max(0.0, interval.end), duration);
            if (clipped_end <= clipped_start) {
                continue;
            }
            const long start_bin = std::min<long>(
                bin_count - 1,
                std::max<long>(0, static_cast<long>(std::floor((clipped_start / duration) * static_cast<double>(bin_count)))));
            const long end_bin_exclusive = std::min<long>(
                bin_count,
                std::max<long>(start_bin + 1, static_cast<long>(std::ceil((clipped_end / duration) * static_cast<double>(bin_count)))));
            for (long idx = start_bin; idx < end_bin_exclusive; ++idx) {
                bins[static_cast<size_t>(idx)] += 1;
            }
        }
    }

    long occupied_bin_count = 0;
    long dense_bin_count = 0;
    long max_bin_active = 0;
    long bin_active_total = 0;
    for (const long active : bins) {
        if (active > 0) {
            ++occupied_bin_count;
        }
        if (active > 1) {
            ++dense_bin_count;
        }
        max_bin_active = std::max(max_bin_active, active);
        bin_active_total += active;
    }
    const double avg_bin_active = bin_count > 0 ? static_cast<double>(bin_active_total) / static_cast<double>(bin_count) : 0.0;

    std::sort(intervals.begin(), intervals.end(), [](const Interval& left, const Interval& right) {
        if (left.start == right.start) {
            return left.end < right.end;
        }
        return left.start < right.start;
    });

    double coverage_duration = 0.0;
    double longest_empty_span = 0.0;
    double merged_start = 0.0;
    double merged_end = 0.0;
    double previous_end = 0.0;
    bool has_merged = false;
    bool has_prev_end = false;
    std::vector<std::pair<double, int>> events;
    events.reserve(intervals.size() * 2);
    for (const auto& interval : intervals) {
        if (has_prev_end && interval.start > previous_end) {
            longest_empty_span = std::max(longest_empty_span, interval.start - previous_end);
        }
        if (!has_merged) {
            merged_start = interval.start;
            merged_end = interval.end;
            has_merged = true;
        } else if (interval.start <= merged_end) {
            merged_end = std::max(merged_end, interval.end);
        } else {
            coverage_duration += std::max(0.0, merged_end - merged_start);
            merged_start = interval.start;
            merged_end = interval.end;
        }
        previous_end = has_prev_end ? std::max(previous_end, interval.end) : interval.end;
        has_prev_end = true;
        events.push_back({interval.start, 1});
        events.push_back({interval.end, -1});
    }
    if (has_merged) {
        coverage_duration += std::max(0.0, merged_end - merged_start);
    }

    std::sort(events.begin(), events.end(), [](const auto& left, const auto& right) {
        if (left.first == right.first) {
            return left.second < right.second;
        }
        return left.first < right.first;
    });
    long active = 0;
    long max_active_segments = 0;
    for (const auto& event : events) {
        active += event.second;
        max_active_segments = std::max(max_active_segments, active);
    }

    PyObject* result = PyDict_New();
    if (result == nullptr) {
        return nullptr;
    }
    if (set_item(result, "schema", PyUnicode_FromString("ai_subtitle_studio.subtitle_global_canvas.summary.v1")) != 0 ||
        set_item(result, "segment_count", PyLong_FromSize_t(count)) != 0 ||
        set_item(result, "valid_segment_count", PyLong_FromSize_t(intervals.size())) != 0 ||
        set_item(result, "invalid_duration_count", PyLong_FromLong(invalid_duration_count)) != 0 ||
        set_item(result, "non_monotonic_count", PyLong_FromLong(non_monotonic_count)) != 0 ||
        set_item(result, "duration", PyFloat_FromDouble(round6(duration))) != 0 ||
        set_item(result, "bin_count", PyLong_FromLong(bin_count)) != 0 ||
        set_item(result, "bin_width_sec", PyFloat_FromDouble(round6(bin_width))) != 0 ||
        set_item(result, "occupied_bin_count", PyLong_FromLong(occupied_bin_count)) != 0 ||
        set_item(result, "empty_bin_count", PyLong_FromLong(std::max<long>(0, bin_count - occupied_bin_count))) != 0 ||
        set_item(result, "dense_bin_count", PyLong_FromLong(dense_bin_count)) != 0 ||
        set_item(result, "max_bin_active", PyLong_FromLong(max_bin_active)) != 0 ||
        set_item(result, "avg_bin_active", PyFloat_FromDouble(round6(avg_bin_active))) != 0 ||
        set_item(result, "coverage_duration", PyFloat_FromDouble(round6(coverage_duration))) != 0 ||
        set_item(result, "coverage_ratio", PyFloat_FromDouble(round6(duration > 0.0 ? coverage_duration / duration : 0.0))) != 0 ||
        set_item(result, "longest_empty_span_sec", PyFloat_FromDouble(round6(longest_empty_span))) != 0 ||
        set_item(result, "max_active_segments", PyLong_FromLong(max_active_segments)) != 0 ||
        set_item(result, "stable_for_global_canvas", PyBool_FromLong(invalid_duration_count == 0 && non_monotonic_count == 0)) != 0 ||
        set_item(result, "native_backend", PyUnicode_FromString("cpp")) != 0) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

PyMethodDef methods[] = {
    {"global_canvas_summary", py_global_canvas_summary, METH_VARARGS, "Summarize subtitle global canvas occupancy bins."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_subtitle_global_canvas",
    "Native subtitle global canvas helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_subtitle_global_canvas(void) {
    return PyModule_Create(&module);
}
