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

PyObject* py_stt_segments_summary(PyObject*, PyObject* args) {
    PyObject* starts_obj = nullptr;
    PyObject* ends_obj = nullptr;
    PyObject* source_codes_obj = nullptr;
    PyObject* recheck_flags_obj = nullptr;
    PyObject* precision_flags_obj = nullptr;
    PyObject* secondary_hint_flags_obj = nullptr;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOO:stt_segments_summary",
            &starts_obj,
            &ends_obj,
            &source_codes_obj,
            &recheck_flags_obj,
            &precision_flags_obj,
            &secondary_hint_flags_obj)) {
        return nullptr;
    }

    std::vector<double> starts;
    std::vector<double> ends;
    std::vector<long> source_codes;
    std::vector<long> recheck_flags;
    std::vector<long> precision_flags;
    std::vector<long> secondary_hint_flags;
    if (!read_double_sequence(starts_obj, starts) ||
        !read_double_sequence(ends_obj, ends) ||
        !read_int_sequence(source_codes_obj, source_codes) ||
        !read_int_sequence(recheck_flags_obj, recheck_flags) ||
        !read_int_sequence(precision_flags_obj, precision_flags) ||
        !read_int_sequence(secondary_hint_flags_obj, secondary_hint_flags)) {
        return nullptr;
    }

    const size_t count = std::min(
        std::min(starts.size(), ends.size()),
        std::min(
            source_codes.size(),
            std::min(recheck_flags.size(), std::min(precision_flags.size(), secondary_hint_flags.size()))));
    long stt1_selected_count = 0;
    long stt2_selected_count = 0;
    long recheck_applied_count = 0;
    long word_precision_count = 0;
    long secondary_hint_count = 0;
    long unknown_source_count = 0;
    long invalid_duration_count = 0;
    long non_monotonic_count = 0;
    long overlap_count = 0;
    long source_switch_count = 0;
    double total_duration = 0.0;
    double stt1_duration = 0.0;
    double stt2_duration = 0.0;
    double previous_start = 0.0;
    double previous_end = 0.0;
    long previous_source = -1;
    bool has_previous = false;

    for (size_t i = 0; i < count; ++i) {
        const double start = starts[i];
        const double end = ends[i];
        const double duration = std::max(0.0, end - start);
        const long source_code = source_codes[i];
        if (!(end > start)) {
            ++invalid_duration_count;
        } else {
            total_duration += duration;
        }
        if (has_previous) {
            if (start < previous_start) {
                ++non_monotonic_count;
            }
            if (start < previous_end) {
                ++overlap_count;
            }
            if (previous_source > 0 && source_code > 0 && previous_source != source_code) {
                ++source_switch_count;
            }
        }
        if (source_code == 1) {
            ++stt1_selected_count;
            stt1_duration += duration;
        } else if (source_code == 2 || source_code == 3) {
            ++stt2_selected_count;
            stt2_duration += duration;
        } else {
            ++unknown_source_count;
        }
        if (recheck_flags[i] != 0) {
            ++recheck_applied_count;
        }
        if (precision_flags[i] != 0) {
            ++word_precision_count;
        }
        if (secondary_hint_flags[i] != 0) {
            ++secondary_hint_count;
        }
        previous_start = start;
        previous_end = end;
        previous_source = source_code;
        has_previous = true;
    }

    const double stt2_coverage_ratio = total_duration > 0.0 ? stt2_duration / total_duration : 0.0;
    PyObject* result = PyDict_New();
    if (result == nullptr) {
        return nullptr;
    }
    if (set_item(result, "schema", PyUnicode_FromString("ai_subtitle_studio.subtitle_stt_segments.summary.v1")) != 0 ||
        set_item(result, "segment_count", PyLong_FromSize_t(count)) != 0 ||
        set_item(result, "stt1_selected_count", PyLong_FromLong(stt1_selected_count)) != 0 ||
        set_item(result, "stt2_selected_count", PyLong_FromLong(stt2_selected_count)) != 0 ||
        set_item(result, "recheck_applied_count", PyLong_FromLong(recheck_applied_count)) != 0 ||
        set_item(result, "word_precision_count", PyLong_FromLong(word_precision_count)) != 0 ||
        set_item(result, "secondary_hint_count", PyLong_FromLong(secondary_hint_count)) != 0 ||
        set_item(result, "unknown_source_count", PyLong_FromLong(unknown_source_count)) != 0 ||
        set_item(result, "invalid_duration_count", PyLong_FromLong(invalid_duration_count)) != 0 ||
        set_item(result, "non_monotonic_count", PyLong_FromLong(non_monotonic_count)) != 0 ||
        set_item(result, "overlap_count", PyLong_FromLong(overlap_count)) != 0 ||
        set_item(result, "source_switch_count", PyLong_FromLong(source_switch_count)) != 0 ||
        set_item(result, "total_duration", PyFloat_FromDouble(round6(total_duration))) != 0 ||
        set_item(result, "stt1_duration", PyFloat_FromDouble(round6(stt1_duration))) != 0 ||
        set_item(result, "stt2_duration", PyFloat_FromDouble(round6(stt2_duration))) != 0 ||
        set_item(result, "stt2_coverage_ratio", PyFloat_FromDouble(round6(stt2_coverage_ratio))) != 0 ||
        set_item(result, "stt2_active", PyBool_FromLong(stt2_selected_count > 0 || recheck_applied_count > 0)) != 0 ||
        set_item(result, "selective_recheck_active", PyBool_FromLong(recheck_applied_count > 0)) != 0 ||
        set_item(result, "stable_for_timeline_feed", PyBool_FromLong(invalid_duration_count == 0 && non_monotonic_count == 0)) != 0 ||
        set_item(result, "native_backend", PyUnicode_FromString("cpp")) != 0) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

PyMethodDef methods[] = {
    {"stt_segments_summary", py_stt_segments_summary, METH_VARARGS, "Summarize STT1/STT2 candidate lane selection metadata."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_subtitle_stt_segments",
    "Native subtitle STT segment helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_subtitle_stt_segments(void) {
    return PyModule_Create(&module);
}
