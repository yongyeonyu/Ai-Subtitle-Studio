#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <vector>

namespace {

bool extract_double_vector(PyObject* obj, std::vector<double>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected a sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t size = PySequence_Fast_GET_SIZE(seq);
    out.reserve(static_cast<size_t>(size));
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        const double value = PyFloat_AsDouble(item);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(value);
    }
    Py_DECREF(seq);
    return true;
}

bool extract_bool_vector(PyObject* obj, std::vector<int>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected a sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t size = PySequence_Fast_GET_SIZE(seq);
    out.reserve(static_cast<size_t>(size));
    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        const long value = PyLong_AsLong(item);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(value != 0 ? 1 : 0);
    }
    Py_DECREF(seq);
    return true;
}

double overlap_ratio_for_spans(double left_start, double left_end, double right_start, double right_end) {
    const double overlap = std::max(0.0, std::min(left_end, right_end) - std::max(left_start, right_start));
    const double span = std::max(0.001, std::min(std::max(0.0, left_end - left_start), std::max(0.0, right_end - right_start)));
    return overlap / span;
}

PyObject* py_overlap_segment_groups(PyObject*, PyObject* args) {
    PyObject* range_starts_obj = nullptr;
    PyObject* range_ends_obj = nullptr;
    PyObject* segment_starts_obj = nullptr;
    PyObject* segment_ends_obj = nullptr;
    double min_overlap_ratio = 0.35;
    if (!PyArg_ParseTuple(
            args,
            "OOOOd",
            &range_starts_obj,
            &range_ends_obj,
            &segment_starts_obj,
            &segment_ends_obj,
            &min_overlap_ratio)) {
        return nullptr;
    }

    std::vector<double> range_starts;
    std::vector<double> range_ends;
    std::vector<double> segment_starts;
    std::vector<double> segment_ends;
    if (!extract_double_vector(range_starts_obj, range_starts) ||
        !extract_double_vector(range_ends_obj, range_ends) ||
        !extract_double_vector(segment_starts_obj, segment_starts) ||
        !extract_double_vector(segment_ends_obj, segment_ends)) {
        return nullptr;
    }

    const size_t range_count = std::min(range_starts.size(), range_ends.size());
    const size_t segment_count = std::min(segment_starts.size(), segment_ends.size());
    PyObject* outer = PyList_New(static_cast<Py_ssize_t>(range_count));
    if (outer == nullptr) {
        return nullptr;
    }

    for (size_t range_idx = 0; range_idx < range_count; ++range_idx) {
        const double range_start = range_starts[range_idx];
        const double range_end = std::max(range_start, range_ends[range_idx]);
        const double range_duration = std::max(0.0, range_end - range_start);
        PyObject* inner = PyList_New(0);
        if (inner == nullptr) {
            Py_DECREF(outer);
            return nullptr;
        }
        for (size_t segment_idx = 0; segment_idx < segment_count; ++segment_idx) {
            const double seg_start = segment_starts[segment_idx];
            const double seg_end = std::max(seg_start, segment_ends[segment_idx]);
            const double overlap = std::max(0.0, std::min(seg_end, range_end) - std::max(seg_start, range_start));
            const double span = std::max(0.001, std::min(std::max(0.0, seg_end - seg_start), range_duration));
            if (overlap / span >= min_overlap_ratio) {
                PyObject* value = PyLong_FromLong(static_cast<long>(segment_idx));
                if (value == nullptr || PyList_Append(inner, value) != 0) {
                    Py_XDECREF(value);
                    Py_DECREF(inner);
                    Py_DECREF(outer);
                    return nullptr;
                }
                Py_DECREF(value);
            }
        }
        PyList_SET_ITEM(outer, static_cast<Py_ssize_t>(range_idx), inner);
    }
    return outer;
}

PyObject* py_uncovered_vad_indices(PyObject*, PyObject* args) {
    PyObject* vad_starts_obj = nullptr;
    PyObject* vad_ends_obj = nullptr;
    PyObject* primary_starts_obj = nullptr;
    PyObject* primary_ends_obj = nullptr;
    PyObject* primary_nonempty_obj = nullptr;
    double min_duration = 0.0;
    double overlap_threshold = 0.18;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOdd",
            &vad_starts_obj,
            &vad_ends_obj,
            &primary_starts_obj,
            &primary_ends_obj,
            &primary_nonempty_obj,
            &min_duration,
            &overlap_threshold)) {
        return nullptr;
    }

    std::vector<double> vad_starts;
    std::vector<double> vad_ends;
    std::vector<double> primary_starts;
    std::vector<double> primary_ends;
    std::vector<int> primary_nonempty;
    if (!extract_double_vector(vad_starts_obj, vad_starts) ||
        !extract_double_vector(vad_ends_obj, vad_ends) ||
        !extract_double_vector(primary_starts_obj, primary_starts) ||
        !extract_double_vector(primary_ends_obj, primary_ends) ||
        !extract_bool_vector(primary_nonempty_obj, primary_nonempty)) {
        return nullptr;
    }

    const size_t vad_count = std::min(vad_starts.size(), vad_ends.size());
    const size_t primary_count = std::min({primary_starts.size(), primary_ends.size(), primary_nonempty.size()});
    PyObject* out = PyList_New(0);
    if (out == nullptr) {
        return nullptr;
    }

    for (size_t vad_idx = 0; vad_idx < vad_count; ++vad_idx) {
        const double start = std::max(0.0, vad_starts[vad_idx]);
        const double raw_end = std::max(start, vad_ends[vad_idx]);
        if (raw_end - start < min_duration) {
            continue;
        }
        bool covered = false;
        const double span = std::max(0.001, raw_end - start);
        for (size_t seg_idx = 0; seg_idx < primary_count; ++seg_idx) {
            if (primary_nonempty[seg_idx] == 0) {
                continue;
            }
            const double seg_start = primary_starts[seg_idx];
            const double seg_end = std::max(seg_start, primary_ends[seg_idx]);
            const double overlap = std::max(0.0, std::min(raw_end, seg_end) - std::max(start, seg_start));
            if (overlap / span >= overlap_threshold) {
                covered = true;
                break;
            }
        }
        if (!covered) {
            PyObject* value = PyLong_FromLong(static_cast<long>(vad_idx));
            if (value == nullptr || PyList_Append(out, value) != 0) {
                Py_XDECREF(value);
                Py_DECREF(out);
                return nullptr;
            }
            Py_DECREF(value);
        }
    }
    return out;
}

PyObject* py_overlap_range_components(PyObject*, PyObject* args) {
    PyObject* range_starts_obj = nullptr;
    PyObject* range_ends_obj = nullptr;
    double min_overlap_ratio = 0.9;
    if (!PyArg_ParseTuple(
            args,
            "OOd",
            &range_starts_obj,
            &range_ends_obj,
            &min_overlap_ratio)) {
        return nullptr;
    }

    std::vector<double> range_starts;
    std::vector<double> range_ends;
    if (!extract_double_vector(range_starts_obj, range_starts) ||
        !extract_double_vector(range_ends_obj, range_ends)) {
        return nullptr;
    }

    const size_t range_count = std::min(range_starts.size(), range_ends.size());
    std::vector<int> visited(range_count, 0);
    PyObject* outer = PyList_New(0);
    if (outer == nullptr) {
        return nullptr;
    }

    for (size_t root_idx = 0; root_idx < range_count; ++root_idx) {
        if (visited[root_idx] != 0) {
            continue;
        }
        std::vector<size_t> stack = {root_idx};
        visited[root_idx] = 1;
        PyObject* inner = PyList_New(0);
        if (inner == nullptr) {
            Py_DECREF(outer);
            return nullptr;
        }
        while (!stack.empty()) {
            const size_t current_idx = stack.back();
            stack.pop_back();
            const double current_start = range_starts[current_idx];
            const double current_end = std::max(current_start, range_ends[current_idx]);
            PyObject* value = PyLong_FromLong(static_cast<long>(current_idx));
            if (value == nullptr || PyList_Append(inner, value) != 0) {
                Py_XDECREF(value);
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            Py_DECREF(value);
            for (size_t other_idx = 0; other_idx < range_count; ++other_idx) {
                if (visited[other_idx] != 0) {
                    continue;
                }
                const double other_start = range_starts[other_idx];
                const double other_end = std::max(other_start, range_ends[other_idx]);
                if (overlap_ratio_for_spans(current_start, current_end, other_start, other_end) >= min_overlap_ratio) {
                    visited[other_idx] = 1;
                    stack.push_back(other_idx);
                }
            }
        }
        if (PyList_Append(outer, inner) != 0) {
            Py_DECREF(inner);
            Py_DECREF(outer);
            return nullptr;
        }
        Py_DECREF(inner);
    }
    return outer;
}

PyObject* py_low_score_primary_indices(PyObject*, PyObject* args) {
    PyObject* primary_scores_obj = nullptr;
    PyObject* primary_nonempty_obj = nullptr;
    double threshold = 50.0;
    if (!PyArg_ParseTuple(
            args,
            "OOd",
            &primary_scores_obj,
            &primary_nonempty_obj,
            &threshold)) {
        return nullptr;
    }

    std::vector<double> primary_scores;
    std::vector<int> primary_nonempty;
    if (!extract_double_vector(primary_scores_obj, primary_scores) ||
        !extract_bool_vector(primary_nonempty_obj, primary_nonempty)) {
        return nullptr;
    }

    const size_t primary_count = std::min(primary_scores.size(), primary_nonempty.size());
    PyObject* out = PyList_New(0);
    if (out == nullptr) {
        return nullptr;
    }
    for (size_t idx = 0; idx < primary_count; ++idx) {
        if (primary_nonempty[idx] == 0 || primary_scores[idx] > threshold) {
            continue;
        }
        PyObject* value = PyLong_FromLong(static_cast<long>(idx));
        if (value == nullptr || PyList_Append(out, value) != 0) {
            Py_XDECREF(value);
            Py_DECREF(out);
            return nullptr;
        }
        Py_DECREF(value);
    }
    return out;
}

PyObject* py_match_low_score_pair_indices(PyObject*, PyObject* args) {
    PyObject* primary_starts_obj = nullptr;
    PyObject* primary_ends_obj = nullptr;
    PyObject* primary_scores_obj = nullptr;
    PyObject* primary_nonempty_obj = nullptr;
    PyObject* secondary_starts_obj = nullptr;
    PyObject* secondary_ends_obj = nullptr;
    PyObject* secondary_scores_obj = nullptr;
    PyObject* secondary_nonempty_obj = nullptr;
    double threshold = 50.0;
    double overlap_threshold = 0.18;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOOOOdd",
            &primary_starts_obj,
            &primary_ends_obj,
            &primary_scores_obj,
            &primary_nonempty_obj,
            &secondary_starts_obj,
            &secondary_ends_obj,
            &secondary_scores_obj,
            &secondary_nonempty_obj,
            &threshold,
            &overlap_threshold)) {
        return nullptr;
    }

    std::vector<double> primary_starts;
    std::vector<double> primary_ends;
    std::vector<double> primary_scores;
    std::vector<int> primary_nonempty;
    std::vector<double> secondary_starts;
    std::vector<double> secondary_ends;
    std::vector<double> secondary_scores;
    std::vector<int> secondary_nonempty;
    if (!extract_double_vector(primary_starts_obj, primary_starts) ||
        !extract_double_vector(primary_ends_obj, primary_ends) ||
        !extract_double_vector(primary_scores_obj, primary_scores) ||
        !extract_bool_vector(primary_nonempty_obj, primary_nonempty) ||
        !extract_double_vector(secondary_starts_obj, secondary_starts) ||
        !extract_double_vector(secondary_ends_obj, secondary_ends) ||
        !extract_double_vector(secondary_scores_obj, secondary_scores) ||
        !extract_bool_vector(secondary_nonempty_obj, secondary_nonempty)) {
        return nullptr;
    }

    const size_t primary_count = std::min({primary_starts.size(), primary_ends.size(), primary_scores.size(), primary_nonempty.size()});
    const size_t secondary_count = std::min({secondary_starts.size(), secondary_ends.size(), secondary_scores.size(), secondary_nonempty.size()});
    std::vector<int> used_secondary(secondary_count, 0);
    PyObject* out = PyList_New(0);
    if (out == nullptr) {
        return nullptr;
    }

    for (size_t primary_idx = 0; primary_idx < primary_count; ++primary_idx) {
        if (primary_nonempty[primary_idx] == 0 || primary_scores[primary_idx] > threshold) {
            continue;
        }
        const double primary_start = primary_starts[primary_idx];
        const double primary_end = std::max(primary_start, primary_ends[primary_idx]);
        size_t best_secondary_idx = secondary_count;
        double best_overlap = 0.0;
        for (size_t secondary_idx = 0; secondary_idx < secondary_count; ++secondary_idx) {
            if (used_secondary[secondary_idx] != 0 || secondary_nonempty[secondary_idx] == 0 || secondary_scores[secondary_idx] > threshold) {
                continue;
            }
            const double secondary_start = secondary_starts[secondary_idx];
            const double secondary_end = std::max(secondary_start, secondary_ends[secondary_idx]);
            const double overlap = overlap_ratio_for_spans(primary_start, primary_end, secondary_start, secondary_end);
            if (overlap > best_overlap) {
                best_overlap = overlap;
                best_secondary_idx = secondary_idx;
            }
        }
        if (best_secondary_idx == secondary_count || best_overlap < overlap_threshold) {
            continue;
        }
        used_secondary[best_secondary_idx] = 1;
        PyObject* pair = PyList_New(2);
        if (pair == nullptr) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(pair, 0, PyLong_FromLong(static_cast<long>(primary_idx)));
        PyList_SET_ITEM(pair, 1, PyLong_FromLong(static_cast<long>(best_secondary_idx)));
        if (PyList_GET_ITEM(pair, 0) == nullptr || PyList_GET_ITEM(pair, 1) == nullptr || PyList_Append(out, pair) != 0) {
            Py_DECREF(pair);
            Py_DECREF(out);
            return nullptr;
        }
        Py_DECREF(pair);
    }
    return out;
}

PyMethodDef kMethods[] = {
    {"low_score_primary_indices", py_low_score_primary_indices, METH_VARARGS, "Find low-score primary indices."},
    {"match_low_score_pair_indices", py_match_low_score_pair_indices, METH_VARARGS, "Match low-score primary/secondary pairs."},
    {"uncovered_vad_indices", py_uncovered_vad_indices, METH_VARARGS, "Find uncovered VAD rows."},
    {"overlap_segment_groups", py_overlap_segment_groups, METH_VARARGS, "Group segment indices by overlapping ranges."},
    {"overlap_range_components", py_overlap_range_components, METH_VARARGS, "Group overlapping recheck ranges."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef kModule = {
    PyModuleDef_HEAD_INIT,
    "_native_stt_recheck",
    "Native STT recheck helpers",
    -1,
    kMethods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_stt_recheck(void) {
    return PyModule_Create(&kModule);
}
