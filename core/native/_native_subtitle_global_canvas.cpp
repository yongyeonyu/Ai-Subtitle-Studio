#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <string>
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

bool read_string_sequence(PyObject* value, std::vector<std::string>& out) {
    PyObject* seq = PySequence_Fast(value, "expected a string sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.clear();
    out.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        PyObject* text_obj = PyObject_Str(item);
        if (text_obj == nullptr) {
            Py_DECREF(seq);
            return false;
        }
        const char* text = PyUnicode_AsUTF8(text_obj);
        if (text == nullptr) {
            Py_DECREF(text_obj);
            Py_DECREF(seq);
            return false;
        }
        out.emplace_back(text);
        Py_DECREF(text_obj);
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

bool contains_string(const std::vector<std::string>& values, const std::string& needle) {
    return std::find(values.begin(), values.end(), needle) != values.end();
}

struct MergeSegment {
    double start;
    double end;
    std::string text;
    std::string lane;
    size_t order;
};

PyObject* segment_dict(const MergeSegment& segment, const std::string& output_lane, long count, bool include_text) {
    PyObject* item = PyDict_New();
    if (item == nullptr) {
        return nullptr;
    }
    if (set_item(item, "start", PyFloat_FromDouble(segment.start)) != 0 ||
        set_item(item, "end", PyFloat_FromDouble(segment.end)) != 0 ||
        set_item(item, "lane", PyUnicode_FromString(output_lane.c_str())) != 0 ||
        set_item(item, "count", PyLong_FromLong(count)) != 0) {
        Py_DECREF(item);
        return nullptr;
    }
    if (include_text && set_item(item, "text", PyUnicode_FromString(segment.text.c_str())) != 0) {
        Py_DECREF(item);
        return nullptr;
    }
    return item;
}

PyObject* py_global_canvas_merged_segments(PyObject*, PyObject* args) {
    PyObject* starts_obj = nullptr;
    PyObject* ends_obj = nullptr;
    PyObject* texts_obj = nullptr;
    PyObject* lanes_obj = nullptr;
    PyObject* allowed_lanes_obj = nullptr;
    const char* output_lane_c = "";
    double max_gap_sec = 0.0;
    int include_text = 1;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOsdp:global_canvas_merged_segments",
            &starts_obj,
            &ends_obj,
            &texts_obj,
            &lanes_obj,
            &allowed_lanes_obj,
            &output_lane_c,
            &max_gap_sec,
            &include_text)) {
        return nullptr;
    }

    std::vector<double> starts;
    std::vector<double> ends;
    std::vector<std::string> texts;
    std::vector<std::string> lanes;
    std::vector<std::string> allowed_lanes;
    if (!read_double_sequence(starts_obj, starts) ||
        !read_double_sequence(ends_obj, ends) ||
        !read_string_sequence(texts_obj, texts) ||
        !read_string_sequence(lanes_obj, lanes) ||
        !read_string_sequence(allowed_lanes_obj, allowed_lanes)) {
        return nullptr;
    }

    const size_t count = std::min(std::min(starts.size(), ends.size()), std::min(texts.size(), lanes.size()));
    std::vector<MergeSegment> segments;
    segments.reserve(count);
    for (size_t i = 0; i < count; ++i) {
        const std::string lane = lanes[i].empty() ? "SUBTITLE" : lanes[i];
        if (!contains_string(allowed_lanes, lane)) {
            continue;
        }
        const double start = std::max(0.0, std::isfinite(starts[i]) ? starts[i] : 0.0);
        const double end = std::max(start, std::isfinite(ends[i]) ? ends[i] : start);
        if (end <= start) {
            continue;
        }
        segments.push_back({start, end, texts[i], lane, i});
    }
    std::sort(segments.begin(), segments.end(), [](const MergeSegment& left, const MergeSegment& right) {
        if (left.start == right.start) {
            return left.order < right.order;
        }
        return left.start < right.start;
    });

    const std::string output_lane = output_lane_c == nullptr ? "" : output_lane_c;
    const double max_gap = std::max(0.0, std::isfinite(max_gap_sec) ? max_gap_sec : 0.0);
    std::vector<MergeSegment> merged;
    std::vector<long> counts;
    for (const auto& segment : segments) {
        if (!merged.empty() && segment.start <= merged.back().end + max_gap) {
            MergeSegment& previous = merged.back();
            previous.end = std::max(previous.end, segment.end);
            if (include_text && !segment.text.empty() && previous.text.find(segment.text) == std::string::npos) {
                if (!previous.text.empty()) {
                    previous.text += " ";
                }
                previous.text += segment.text;
            }
            counts.back() += 1;
            continue;
        }
        merged.push_back(segment);
        counts.push_back(1);
    }

    PyObject* out = PyList_New(static_cast<Py_ssize_t>(merged.size()));
    if (out == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < merged.size(); ++i) {
        PyObject* item = segment_dict(merged[i], output_lane, counts[i], include_text != 0);
        if (item == nullptr) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, static_cast<Py_ssize_t>(i), item);
    }
    return out;
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
    long max_active_bin_index = -1;
    long bin_active_total = 0;
    for (size_t idx = 0; idx < bins.size(); ++idx) {
        const long active = bins[idx];
        if (active > 0) {
            ++occupied_bin_count;
        }
        if (active > 1) {
            ++dense_bin_count;
        }
        if (active > max_bin_active) {
            max_bin_active = active;
            max_active_bin_index = active > 0 ? static_cast<long>(idx) : -1;
        }
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
    double longest_empty_start = 0.0;
    double longest_empty_end = 0.0;
    double merged_start = 0.0;
    double merged_end = 0.0;
    double previous_end = 0.0;
    bool has_merged = false;
    bool has_prev_end = false;
    std::vector<std::pair<double, int>> events;
    events.reserve(intervals.size() * 2);
    for (const auto& interval : intervals) {
        if (has_prev_end && interval.start > previous_end) {
            const double gap = interval.start - previous_end;
            // 변경 금지: global canvas 빈 구간 위치는 Swift/Python fallback과 같은 의미로 유지합니다.
            // 화면 시나리오를 바꾸지 않고 X5 artifact에서 minimap/segment drift 위치를 역추적하는 계약입니다.
            if (gap > longest_empty_span) {
                longest_empty_span = gap;
                longest_empty_start = previous_end;
                longest_empty_end = interval.start;
            }
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
        set_item(result, "max_active_bin_index", PyLong_FromLong(max_active_bin_index)) != 0 ||
        set_item(result, "avg_bin_active", PyFloat_FromDouble(round6(avg_bin_active))) != 0 ||
        set_item(result, "coverage_duration", PyFloat_FromDouble(round6(coverage_duration))) != 0 ||
        set_item(result, "coverage_ratio", PyFloat_FromDouble(round6(duration > 0.0 ? coverage_duration / duration : 0.0))) != 0 ||
        set_item(result, "longest_empty_span_sec", PyFloat_FromDouble(round6(longest_empty_span))) != 0 ||
        set_item(result, "longest_empty_start_sec", PyFloat_FromDouble(round6(longest_empty_start))) != 0 ||
        set_item(result, "longest_empty_end_sec", PyFloat_FromDouble(round6(longest_empty_end))) != 0 ||
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
    {"global_canvas_merged_segments", py_global_canvas_merged_segments, METH_VARARGS, "Merge global canvas lane segments for dense minimap drawing."},
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
