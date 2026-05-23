#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <vector>

namespace {

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

bool read_int_sequence(PyObject* value, std::vector<long>& out) {
    PyObject* seq = PySequence_Fast(value, "expected an integer sequence");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.clear();
    out.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        long number = PyLong_AsLong(item);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(std::max<long>(0, number));
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

PyObject* py_segment_summary(PyObject*, PyObject* args) {
    PyObject* starts_obj = nullptr;
    PyObject* ends_obj = nullptr;
    PyObject* text_lengths_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OOO:segment_summary", &starts_obj, &ends_obj, &text_lengths_obj)) {
        return nullptr;
    }

    std::vector<double> starts;
    std::vector<double> ends;
    std::vector<long> text_lengths;
    if (!read_double_sequence(starts_obj, starts) ||
        !read_double_sequence(ends_obj, ends) ||
        !read_int_sequence(text_lengths_obj, text_lengths)) {
        return nullptr;
    }

    const size_t count = std::min(starts.size(), std::min(ends.size(), text_lengths.size()));
    long invalid_duration_count = 0;
    long non_monotonic_count = 0;
    long overlap_count = 0;
    long empty_text_count = 0;
    long max_chars = 0;
    long total_chars = 0;
    double total_duration = 0.0;
    double max_gap = 0.0;
    double previous_start = 0.0;
    double previous_end = 0.0;
    bool has_previous = false;
    double first_start = 0.0;
    double last_end = 0.0;

    for (size_t i = 0; i < count; ++i) {
        const double start = starts[i];
        const double end = ends[i];
        const long chars = std::max<long>(0, text_lengths[i]);
        if (i == 0) {
            first_start = start;
        }
        last_end = end;
        total_chars += chars;
        max_chars = std::max(max_chars, chars);
        if (chars <= 0) {
            ++empty_text_count;
        }
        if (!(end > start)) {
            ++invalid_duration_count;
        } else {
            total_duration += end - start;
        }
        if (has_previous) {
            if (start < previous_start) {
                ++non_monotonic_count;
            }
            if (start < previous_end) {
                ++overlap_count;
            } else {
                max_gap = std::max(max_gap, start - previous_end);
            }
        }
        previous_start = start;
        previous_end = end;
        has_previous = true;
    }

    const double avg_chars = count > 0 ? static_cast<double>(total_chars) / static_cast<double>(count) : 0.0;
    PyObject* result = PyDict_New();
    if (result == nullptr) {
        return nullptr;
    }
    if (set_item(result, "schema", PyUnicode_FromString("ai_subtitle_studio.subtitle_segments.summary.v1")) != 0 ||
        set_item(result, "segment_count", PyLong_FromSize_t(count)) != 0 ||
        set_item(result, "invalid_duration_count", PyLong_FromLong(invalid_duration_count)) != 0 ||
        set_item(result, "non_monotonic_count", PyLong_FromLong(non_monotonic_count)) != 0 ||
        set_item(result, "overlap_count", PyLong_FromLong(overlap_count)) != 0 ||
        set_item(result, "empty_text_count", PyLong_FromLong(empty_text_count)) != 0 ||
        set_item(result, "total_duration", PyFloat_FromDouble(round6(total_duration))) != 0 ||
        set_item(result, "first_start", PyFloat_FromDouble(round6(first_start))) != 0 ||
        set_item(result, "last_end", PyFloat_FromDouble(round6(last_end))) != 0 ||
        set_item(result, "max_gap", PyFloat_FromDouble(round6(max_gap))) != 0 ||
        set_item(result, "max_chars", PyLong_FromLong(max_chars)) != 0 ||
        set_item(result, "avg_chars", PyFloat_FromDouble(round6(avg_chars))) != 0 ||
        set_item(result, "stable_for_save_reopen", PyBool_FromLong(invalid_duration_count == 0 && non_monotonic_count == 0)) != 0 ||
        set_item(result, "native_backend", PyUnicode_FromString("cpp")) != 0) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

PyMethodDef methods[] = {
    {"segment_summary", py_segment_summary, METH_VARARGS, "Summarize subtitle segment timing and save/reopen invariants."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_subtitle_segments",
    "Native subtitle segment helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_subtitle_segments(void) {
    return PyModule_Create(&module);
}
