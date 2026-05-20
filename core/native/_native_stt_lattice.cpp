#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <vector>

namespace {

bool read_float_sequence(PyObject* obj, std::vector<double>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected a sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t size = PySequence_Fast_GET_SIZE(seq);
    PyObject** items = PySequence_Fast_ITEMS(seq);
    out.clear();
    out.reserve(static_cast<size_t>(size));
    for (Py_ssize_t index = 0; index < size; ++index) {
        const double value = PyFloat_AsDouble(items[index]);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(value);
    }
    Py_DECREF(seq);
    return true;
}

bool read_int_sequence(PyObject* obj, std::vector<int>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected a sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t size = PySequence_Fast_GET_SIZE(seq);
    PyObject** items = PySequence_Fast_ITEMS(seq);
    out.clear();
    out.reserve(static_cast<size_t>(size));
    for (Py_ssize_t index = 0; index < size; ++index) {
        const long value = PyLong_AsLong(items[index]);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(static_cast<int>(value));
    }
    Py_DECREF(seq);
    return true;
}

double clip01(double value) {
    return std::max(0.0, std::min(1.0, value));
}

double temporal_score(double anchor_start, double anchor_end, double word_start, double word_end) {
    const double overlap = std::max(0.0, std::min(anchor_end, word_end) - std::max(anchor_start, word_start));
    const double anchor_span = std::max(0.0, anchor_end - anchor_start);
    const double word_span = std::max(0.0, word_end - word_start);
    const double span = std::max(std::max(anchor_span, word_span), 0.05);
    const double overlap_score = overlap / span;
    const double anchor_mid = (anchor_start + anchor_end) / 2.0;
    const double word_mid = (word_start + word_end) / 2.0;
    const double midpoint_score = std::max(0.0, 1.0 - std::abs(anchor_mid - word_mid) / 0.75);
    return std::max(overlap_score, midpoint_score * 0.75);
}

bool is_used(int index, const std::vector<int>& used_indices) {
    return std::find(used_indices.begin(), used_indices.end(), index) != used_indices.end();
}

PyObject* py_best_word_match(PyObject*, PyObject* args) {
    double anchor_start = 0.0;
    double anchor_end = 0.0;
    PyObject* starts_obj = nullptr;
    PyObject* ends_obj = nullptr;
    PyObject* textual_obj = nullptr;
    PyObject* used_obj = nullptr;
    double min_match_score = 0.0;
    if (!PyArg_ParseTuple(
            args,
            "ddOOOOd:best_word_match",
            &anchor_start,
            &anchor_end,
            &starts_obj,
            &ends_obj,
            &textual_obj,
            &used_obj,
            &min_match_score)) {
        return nullptr;
    }

    std::vector<double> starts;
    std::vector<double> ends;
    std::vector<double> textual_scores;
    std::vector<int> used_indices;
    if (!read_float_sequence(starts_obj, starts) ||
        !read_float_sequence(ends_obj, ends) ||
        !read_float_sequence(textual_obj, textual_scores) ||
        !read_int_sequence(used_obj, used_indices)) {
        return nullptr;
    }

    const size_t count = starts.size();
    if (ends.size() != count || textual_scores.size() != count) {
        PyErr_SetString(PyExc_ValueError, "word starts, ends, and textual scores must have the same length");
        return nullptr;
    }

    int best_index = -1;
    double best_score = 0.0;

    for (size_t raw_index = 0; raw_index < count; ++raw_index) {
        const int index = static_cast<int>(raw_index);
        if (is_used(index, used_indices)) {
            continue;
        }
        const double temporal = temporal_score(anchor_start, anchor_end, starts[raw_index], ends[raw_index]);
        const double textual = clip01(textual_scores[raw_index]);
        const double score = temporal * 0.62 + textual * 0.38;
        if (score > best_score) {
            best_score = score;
            best_index = index;
        }
    }

    if (best_score < min_match_score) {
        best_index = -1;
    }
    return Py_BuildValue("id", best_index, best_score);
}

PyMethodDef methods[] = {
    {"best_word_match", py_best_word_match, METH_VARARGS, "Find the best lattice word match candidate."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_stt_lattice",
    "Native STT lattice helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_stt_lattice(void) {
    return PyModule_Create(&module);
}
