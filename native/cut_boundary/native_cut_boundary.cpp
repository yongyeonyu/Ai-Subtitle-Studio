#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <utility>
#include <vector>

namespace {

int clamp_target_samples(int value) {
    if (value <= 0) {
        value = 64;
    }
    return std::max(16, std::min(256, value));
}

double delta_bytes_raw(const unsigned char* left, Py_ssize_t left_size, const unsigned char* right, Py_ssize_t right_size, int target_samples) {
    const Py_ssize_t n = std::min(left_size, right_size);
    if (left == nullptr || right == nullptr || n <= 0) {
        return 0.0;
    }

    const int samples = clamp_target_samples(target_samples);
    const Py_ssize_t step = std::max<Py_ssize_t>(1, n / samples);
    double total = 0.0;
    Py_ssize_t count = 0;
    for (Py_ssize_t i = 0; i < n; i += step) {
        total += std::abs(static_cast<int>(left[i]) - static_cast<int>(right[i]));
        ++count;
    }
    return count > 0 ? total / static_cast<double>(count) : 0.0;
}

PyObject* py_delta_bytes(PyObject*, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {"left", "right", "target_samples", nullptr};
    Py_buffer left{};
    Py_buffer right{};
    int target_samples = 64;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "y*y*|i", const_cast<char**>(kwlist), &left, &right, &target_samples)) {
        return nullptr;
    }

    double out = 0.0;
    Py_BEGIN_ALLOW_THREADS
    out = delta_bytes_raw(
        static_cast<const unsigned char*>(left.buf),
        left.len,
        static_cast<const unsigned char*>(right.buf),
        right.len,
        target_samples
    );
    Py_END_ALLOW_THREADS

    PyBuffer_Release(&left);
    PyBuffer_Release(&right);
    return PyFloat_FromDouble(out);
}

PyObject* py_gray_delta(PyObject*, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {"prev_thumb", "next_thumb", "region_threshold", "target_samples", nullptr};
    PyObject* prev_obj = nullptr;
    PyObject* next_obj = nullptr;
    double region_threshold = 0.0;
    int target_samples = 64;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOdi", const_cast<char**>(kwlist), &prev_obj, &next_obj, &region_threshold, &target_samples)) {
        return nullptr;
    }

    PyObject* prev = PySequence_Fast(prev_obj, "prev_thumb must be a sequence");
    if (prev == nullptr) {
        return nullptr;
    }
    PyObject* next = PySequence_Fast(next_obj, "next_thumb must be a sequence");
    if (next == nullptr) {
        Py_DECREF(prev);
        return nullptr;
    }

    const Py_ssize_t n = std::min(PySequence_Fast_GET_SIZE(prev), PySequence_Fast_GET_SIZE(next));
    std::vector<double> deltas;
    deltas.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    int hits = 0;

    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* left_obj = PySequence_Fast_GET_ITEM(prev, i);
        PyObject* right_obj = PySequence_Fast_GET_ITEM(next, i);
        Py_buffer left{};
        Py_buffer right{};
        if (PyObject_GetBuffer(left_obj, &left, PyBUF_SIMPLE) != 0) {
            PyErr_Clear();
            continue;
        }
        if (PyObject_GetBuffer(right_obj, &right, PyBUF_SIMPLE) != 0) {
            PyErr_Clear();
            PyBuffer_Release(&left);
            continue;
        }

        const double delta = delta_bytes_raw(
            static_cast<const unsigned char*>(left.buf),
            left.len,
            static_cast<const unsigned char*>(right.buf),
            right.len,
            target_samples
        );
        PyBuffer_Release(&left);
        PyBuffer_Release(&right);

        deltas.push_back(delta);
        if (delta >= region_threshold) {
            ++hits;
        }
    }

    Py_DECREF(prev);
    Py_DECREF(next);

    if (deltas.empty()) {
        return Py_BuildValue("(diO)", 0.0, 0, PyList_New(0));
    }

    std::vector<double> ranked = deltas;
    std::sort(ranked.begin(), ranked.end(), std::greater<double>());
    const size_t top_n = std::min<size_t>(3, ranked.size());
    double score = 0.0;
    for (size_t i = 0; i < top_n; ++i) {
        score += ranked[i];
    }
    score /= static_cast<double>(top_n);

    PyObject* list = PyList_New(static_cast<Py_ssize_t>(deltas.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < deltas.size(); ++i) {
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), PyFloat_FromDouble(deltas[i]));
    }

    PyObject* result = Py_BuildValue("(diO)", score, hits, list);
    Py_DECREF(list);
    return result;
}

bool read_triplet(PyObject* item, double& a0, double& a1, double& a2) {
    PyObject* seq = PySequence_Fast(item, "color average must be a sequence");
    if (seq == nullptr) {
        PyErr_Clear();
        return false;
    }
    if (PySequence_Fast_GET_SIZE(seq) < 3) {
        Py_DECREF(seq);
        return false;
    }
    a0 = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, 0));
    a1 = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, 1));
    a2 = PyFloat_AsDouble(PySequence_Fast_GET_ITEM(seq, 2));
    Py_DECREF(seq);
    if (PyErr_Occurred()) {
        PyErr_Clear();
        return false;
    }
    return true;
}

PyObject* py_color_avg_delta(PyObject*, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {"prev_avg", "next_avg", "threshold", "weight_luma", "weight_chroma", nullptr};
    PyObject* prev_obj = nullptr;
    PyObject* next_obj = nullptr;
    double threshold = 0.0;
    double weight_luma = 1.0;
    double weight_chroma = 1.0;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOddd", const_cast<char**>(kwlist), &prev_obj, &next_obj, &threshold, &weight_luma, &weight_chroma)) {
        return nullptr;
    }

    PyObject* prev = PySequence_Fast(prev_obj, "prev_avg must be a sequence");
    if (prev == nullptr) {
        return nullptr;
    }
    PyObject* next = PySequence_Fast(next_obj, "next_avg must be a sequence");
    if (next == nullptr) {
        Py_DECREF(prev);
        return nullptr;
    }

    const Py_ssize_t n = std::min(PySequence_Fast_GET_SIZE(prev), PySequence_Fast_GET_SIZE(next));
    std::vector<double> deltas;
    deltas.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    int hits = 0;

    for (Py_ssize_t i = 0; i < n; ++i) {
        double a0 = 0.0, a1 = 0.0, a2 = 0.0;
        double b0 = 0.0, b1 = 0.0, b2 = 0.0;
        if (!read_triplet(PySequence_Fast_GET_ITEM(prev, i), a0, a1, a2)) {
            continue;
        }
        if (!read_triplet(PySequence_Fast_GET_ITEM(next, i), b0, b1, b2)) {
            continue;
        }

        const double luma = std::abs(a0 - b0);
        const double chroma = (std::abs(a1 - b1) + std::abs(a2 - b2)) / 2.0;
        const double score = weight_luma * luma + weight_chroma * chroma;
        deltas.push_back(score);
        if (score >= threshold) {
            ++hits;
        }
    }

    Py_DECREF(prev);
    Py_DECREF(next);

    if (deltas.empty()) {
        return Py_BuildValue("(diO)", 0.0, 0, PyList_New(0));
    }

    double score = 0.0;
    for (const double item : deltas) {
        score += item;
    }
    score /= static_cast<double>(deltas.size());

    PyObject* list = PyList_New(static_cast<Py_ssize_t>(deltas.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < deltas.size(); ++i) {
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), PyFloat_FromDouble(deltas[i]));
    }

    PyObject* result = Py_BuildValue("(diO)", score, hits, list);
    Py_DECREF(list);
    return result;
}

bool read_double_sequence(PyObject* obj, std::vector<double>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected a numeric sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.clear();
    out.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        const double value = PyFloat_AsDouble(item);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            out.push_back(0.0);
        } else if (std::isfinite(value)) {
            out.push_back(value);
        } else {
            out.push_back(0.0);
        }
    }
    Py_DECREF(seq);
    return true;
}

bool read_int_sequence(PyObject* obj, std::vector<int>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected an integer sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.clear();
    out.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        const long value = PyLong_AsLong(item);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            out.push_back(0);
        } else {
            out.push_back(static_cast<int>(value));
        }
    }
    Py_DECREF(seq);
    return true;
}

struct Interval {
    double start = 0.0;
    double end = 0.0;
    size_t index = 0;
};

PyObject* py_interval_overlaps(PyObject*, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {"segment_starts", "segment_ends", "vad_starts", "vad_ends", nullptr};
    PyObject* seg_starts_obj = nullptr;
    PyObject* seg_ends_obj = nullptr;
    PyObject* vad_starts_obj = nullptr;
    PyObject* vad_ends_obj = nullptr;
    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "OOOO",
            const_cast<char**>(kwlist),
            &seg_starts_obj,
            &seg_ends_obj,
            &vad_starts_obj,
            &vad_ends_obj
        )) {
        return nullptr;
    }

    std::vector<double> seg_starts;
    std::vector<double> seg_ends;
    std::vector<double> vad_starts;
    std::vector<double> vad_ends;
    if (
        !read_double_sequence(seg_starts_obj, seg_starts)
        || !read_double_sequence(seg_ends_obj, seg_ends)
        || !read_double_sequence(vad_starts_obj, vad_starts)
        || !read_double_sequence(vad_ends_obj, vad_ends)
    ) {
        return nullptr;
    }

    const size_t seg_n = std::min(seg_starts.size(), seg_ends.size());
    const size_t vad_n = std::min(vad_starts.size(), vad_ends.size());
    std::vector<double> overlaps(seg_n, 0.0);
    if (seg_n == 0 || vad_n == 0) {
        PyObject* list = PyList_New(static_cast<Py_ssize_t>(seg_n));
        if (list == nullptr) {
            return nullptr;
        }
        for (size_t i = 0; i < seg_n; ++i) {
            PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), PyFloat_FromDouble(0.0));
        }
        return list;
    }

    std::vector<Interval> segments;
    std::vector<Interval> vad;
    segments.reserve(seg_n);
    vad.reserve(vad_n);

    for (size_t i = 0; i < seg_n; ++i) {
        double start = std::max(0.0, seg_starts[i]);
        double end = std::max(start, seg_ends[i]);
        segments.push_back({start, end, i});
    }
    for (size_t i = 0; i < vad_n; ++i) {
        double start = std::max(0.0, vad_starts[i]);
        double end = std::max(start, vad_ends[i]);
        if (end > start) {
            vad.push_back({start, end, i});
        }
    }
    std::sort(segments.begin(), segments.end(), [](const Interval& a, const Interval& b) {
        if (a.start == b.start) {
            return a.end < b.end;
        }
        return a.start < b.start;
    });
    std::sort(vad.begin(), vad.end(), [](const Interval& a, const Interval& b) {
        if (a.start == b.start) {
            return a.end < b.end;
        }
        return a.start < b.start;
    });

    size_t vad_cursor = 0;
    Py_BEGIN_ALLOW_THREADS
    for (const Interval& seg : segments) {
        while (vad_cursor < vad.size() && vad[vad_cursor].end <= seg.start) {
            ++vad_cursor;
        }
        double overlap = 0.0;
        for (size_t j = vad_cursor; j < vad.size(); ++j) {
            if (vad[j].start >= seg.end) {
                break;
            }
            const double lo = std::max(seg.start, vad[j].start);
            const double hi = std::min(seg.end, vad[j].end);
            if (hi > lo) {
                overlap += hi - lo;
            }
        }
        overlaps[seg.index] = overlap;
    }
    Py_END_ALLOW_THREADS

    PyObject* list = PyList_New(static_cast<Py_ssize_t>(seg_n));
    if (list == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < seg_n; ++i) {
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), PyFloat_FromDouble(overlaps[i]));
    }
    return list;
}

PyObject* py_word_split_groups(PyObject*, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {
        "starts",
        "ends",
        "char_counts",
        "natural_breaks",
        "vad_indexes",
        "max_chars",
        "max_duration",
        "max_cps",
        "min_duration",
        "gap_break_sec",
        "word_gap_break_sec",
        nullptr,
    };
    PyObject* starts_obj = nullptr;
    PyObject* ends_obj = nullptr;
    PyObject* chars_obj = nullptr;
    PyObject* natural_obj = nullptr;
    PyObject* vad_obj = nullptr;
    int max_chars = 10;
    double max_duration = 6.0;
    double max_cps = 12.0;
    double min_duration = 0.0;
    double gap_break_sec = 1.5;
    double word_gap_break_sec = 0.65;
    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "OOOOOiddddd",
            const_cast<char**>(kwlist),
            &starts_obj,
            &ends_obj,
            &chars_obj,
            &natural_obj,
            &vad_obj,
            &max_chars,
            &max_duration,
            &max_cps,
            &min_duration,
            &gap_break_sec,
            &word_gap_break_sec
        )) {
        return nullptr;
    }

    std::vector<double> starts;
    std::vector<double> ends;
    std::vector<int> char_counts;
    std::vector<int> natural_breaks;
    std::vector<int> vad_indexes;
    if (
        !read_double_sequence(starts_obj, starts)
        || !read_double_sequence(ends_obj, ends)
        || !read_int_sequence(chars_obj, char_counts)
        || !read_int_sequence(natural_obj, natural_breaks)
        || !read_int_sequence(vad_obj, vad_indexes)
    ) {
        return nullptr;
    }

    const size_t n = std::min({starts.size(), ends.size(), char_counts.size(), natural_breaks.size(), vad_indexes.size()});
    std::vector<std::pair<size_t, size_t>> groups;
    groups.reserve(n);

    Py_BEGIN_ALLOW_THREADS
    size_t begin = 0;
    int chars = 0;
    for (size_t i = 0; i < n; ++i) {
        chars += std::max(0, char_counts[i]);
        bool flush = false;
        if (i + 1 >= n) {
            flush = true;
        } else {
            const double start = std::max(0.0, starts[begin]);
            const double end = std::max(start, ends[i]);
            const double duration = std::max(0.05, end - start);
            const double gap = starts[i + 1] - end;
            const double cps = duration > 0.0 ? static_cast<double>(chars) / duration : static_cast<double>(chars);
            const bool natural = natural_breaks[i] != 0;
            const bool vad_break = vad_indexes[i] >= 0 && vad_indexes[i + 1] >= 0 && vad_indexes[i] != vad_indexes[i + 1];
            const bool word_gap_break = gap >= word_gap_break_sec;

            if ((vad_break || word_gap_break) && duration >= 0.08) {
                flush = true;
            } else if (duration < min_duration) {
                flush = false;
            } else if (gap >= gap_break_sec) {
                flush = true;
            } else if (chars >= max_chars && natural) {
                flush = true;
            } else if (
                duration >= max_duration
                && (natural || gap >= std::min(gap_break_sec * 0.5, 1.0) || chars >= static_cast<int>(max_chars * 0.5))
            ) {
                flush = true;
            } else if (cps > max_cps && chars >= max_chars && natural) {
                flush = true;
            } else if (chars >= static_cast<int>(max_chars * 1.5)) {
                flush = true;
            }
        }

        if (flush) {
            groups.push_back({begin, i + 1});
            begin = i + 1;
            chars = 0;
        }
    }
    Py_END_ALLOW_THREADS

    PyObject* list = PyList_New(static_cast<Py_ssize_t>(groups.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < groups.size(); ++i) {
        PyObject* item = Py_BuildValue("(nn)", static_cast<Py_ssize_t>(groups[i].first), static_cast<Py_ssize_t>(groups[i].second));
        if (item == nullptr) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), item);
    }
    return list;
}

PyObject* py_llm_macro_group_ranges(PyObject*, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {
        "cut_before",
        "needs_llm",
        "min_rows",
        "max_rows",
        nullptr,
    };
    PyObject* cut_obj = nullptr;
    PyObject* needs_obj = nullptr;
    int min_rows = 10;
    int max_rows = 15;
    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "OOii",
            const_cast<char**>(kwlist),
            &cut_obj,
            &needs_obj,
            &min_rows,
            &max_rows
        )) {
        return nullptr;
    }

    std::vector<int> cut_before;
    std::vector<int> needs_llm;
    if (!read_int_sequence(cut_obj, cut_before) || !read_int_sequence(needs_obj, needs_llm)) {
        return nullptr;
    }

    const size_t n = std::min(cut_before.size(), needs_llm.size());
    min_rows = std::max(2, min_rows);
    max_rows = std::max(min_rows, max_rows);

    struct Group {
        size_t start;
        size_t end;
        int needs_any;
        int need_count;
    };
    std::vector<Group> groups;
    groups.reserve(n > 0 ? (n / static_cast<size_t>(max_rows) + 1) : 0);

    Py_BEGIN_ALLOW_THREADS
    size_t current_start = 0;
    int current_need_count = 0;
    size_t current_len = 0;
    for (size_t index = 0; index < n; ++index) {
        if (current_len > 0) {
            const bool cut_here = cut_before[index] != 0;
            if ((current_len >= static_cast<size_t>(min_rows) && cut_here) || current_len >= static_cast<size_t>(max_rows)) {
                groups.push_back({current_start, index, current_need_count > 0 ? 1 : 0, current_need_count});
                current_start = index;
                current_len = 0;
                current_need_count = 0;
            }
        }
        current_len += 1;
        if (needs_llm[index] != 0) {
            current_need_count += 1;
        }
    }
    if (current_len > 0) {
        groups.push_back({current_start, n, current_need_count > 0 ? 1 : 0, current_need_count});
    }
    Py_END_ALLOW_THREADS

    PyObject* list = PyList_New(static_cast<Py_ssize_t>(groups.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < groups.size(); ++i) {
        const Group& group = groups[i];
        PyObject* item = Py_BuildValue(
            "(nnii)",
            static_cast<Py_ssize_t>(group.start),
            static_cast<Py_ssize_t>(group.end),
            group.needs_any,
            group.need_count
        );
        if (item == nullptr) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), item);
    }
    return list;
}

PyMethodDef methods[] = {
    {"delta_bytes", reinterpret_cast<PyCFunction>(py_delta_bytes), METH_VARARGS | METH_KEYWORDS, "Compute sampled absolute byte delta."},
    {"gray_delta", reinterpret_cast<PyCFunction>(py_gray_delta), METH_VARARGS | METH_KEYWORDS, "Compute cut-boundary gray thumbnail deltas."},
    {"color_avg_delta", reinterpret_cast<PyCFunction>(py_color_avg_delta), METH_VARARGS | METH_KEYWORDS, "Compute cut-boundary color average deltas."},
    {"interval_overlaps", reinterpret_cast<PyCFunction>(py_interval_overlaps), METH_VARARGS | METH_KEYWORDS, "Compute batch interval overlaps for subtitle/VAD ranges."},
    {"word_split_groups", reinterpret_cast<PyCFunction>(py_word_split_groups), METH_VARARGS | METH_KEYWORDS, "Split word indexes into subtitle groups with native C++ thresholds."},
    {"llm_macro_group_ranges", reinterpret_cast<PyCFunction>(py_llm_macro_group_ranges), METH_VARARGS | METH_KEYWORDS, "Build LLM macro group ranges from cut and review flags."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_cut_boundary",
    "Native C++ cut-boundary scoring helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_cut_boundary() {
    return PyModule_Create(&module);
}
