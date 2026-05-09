#include <Python.h>

#include <algorithm>
#include <cmath>
#include <vector>

namespace {

struct BufferView {
    Py_buffer view{};
    bool acquired = false;

    ~BufferView() {
        if (acquired) {
            PyBuffer_Release(&view);
        }
    }
};

bool get_buffer(PyObject* obj, BufferView& out) {
    if (PyObject_GetBuffer(obj, &out.view, PyBUF_SIMPLE) != 0) {
        return false;
    }
    out.acquired = true;
    return true;
}

int clamp_target_samples(int target_samples) {
    if (target_samples <= 0) {
        target_samples = 64;
    }
    return std::max(16, std::min(256, target_samples));
}

double delta_bytes_raw(const unsigned char* left, Py_ssize_t left_len,
                       const unsigned char* right, Py_ssize_t right_len,
                       int target_samples) {
    const Py_ssize_t n = std::min(left_len, right_len);
    if (left == nullptr || right == nullptr || n <= 0) {
        return 0.0;
    }

    target_samples = clamp_target_samples(target_samples);
    const Py_ssize_t step = std::max<Py_ssize_t>(1, n / target_samples);

    double total = 0.0;
    Py_ssize_t count = 0;
    for (Py_ssize_t i = 0; i < n; i += step) {
        total += std::abs(static_cast<int>(left[i]) - static_cast<int>(right[i]));
        ++count;
    }
    return total / static_cast<double>(count > 0 ? count : 1);
}

PyObject* float_list_from_vector(const std::vector<double>& values) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(values.size()); ++i) {
        PyObject* item = PyFloat_FromDouble(values[static_cast<size_t>(i)]);
        if (item == nullptr) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, i, item);
    }
    return list;
}

PyObject* tuple_score_hits_deltas(double score, int hits, const std::vector<double>& deltas) {
    PyObject* out = PyTuple_New(3);
    if (out == nullptr) {
        return nullptr;
    }

    PyObject* py_score = PyFloat_FromDouble(score);
    PyObject* py_hits = PyLong_FromLong(hits);
    PyObject* py_deltas = float_list_from_vector(deltas);
    if (py_score == nullptr || py_hits == nullptr || py_deltas == nullptr) {
        Py_XDECREF(py_score);
        Py_XDECREF(py_hits);
        Py_XDECREF(py_deltas);
        Py_DECREF(out);
        return nullptr;
    }

    PyTuple_SET_ITEM(out, 0, py_score);
    PyTuple_SET_ITEM(out, 1, py_hits);
    PyTuple_SET_ITEM(out, 2, py_deltas);
    return out;
}

bool read_triplet(PyObject* obj, double& a0, double& a1, double& a2) {
    PyObject* seq = PySequence_Fast(obj, "color average item must be a sequence");
    if (seq == nullptr) {
        return false;
    }
    if (PySequence_Fast_GET_SIZE(seq) < 3) {
        Py_DECREF(seq);
        PyErr_SetString(PyExc_ValueError, "color average item must have at least 3 values");
        return false;
    }

    PyObject** items = PySequence_Fast_ITEMS(seq);
    a0 = PyFloat_AsDouble(items[0]);
    a1 = PyFloat_AsDouble(items[1]);
    a2 = PyFloat_AsDouble(items[2]);
    Py_DECREF(seq);
    return !PyErr_Occurred();
}

bool sequence_to_doubles(PyObject* obj, std::vector<double>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected a sequence of numbers");
    if (seq == nullptr) {
        return false;
    }

    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.reserve(static_cast<size_t>(n));
    PyObject** items = PySequence_Fast_ITEMS(seq);
    for (Py_ssize_t i = 0; i < n; ++i) {
        const double value = PyFloat_AsDouble(items[i]);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(value);
    }
    Py_DECREF(seq);
    return true;
}

PyObject* py_delta_bytes(PyObject*, PyObject* args) {
    PyObject* left_obj = nullptr;
    PyObject* right_obj = nullptr;
    int target_samples = 64;
    if (!PyArg_ParseTuple(args, "OO|i:delta_bytes", &left_obj, &right_obj, &target_samples)) {
        return nullptr;
    }

    BufferView left;
    BufferView right;
    if (!get_buffer(left_obj, left) || !get_buffer(right_obj, right)) {
        return nullptr;
    }

    const auto* left_bytes = static_cast<const unsigned char*>(left.view.buf);
    const auto* right_bytes = static_cast<const unsigned char*>(right.view.buf);
    return PyFloat_FromDouble(delta_bytes_raw(left_bytes, left.view.len, right_bytes, right.view.len, target_samples));
}

PyObject* py_gray_delta(PyObject*, PyObject* args) {
    PyObject* prev_obj = nullptr;
    PyObject* next_obj = nullptr;
    double region_threshold = 0.0;
    int target_samples = 64;
    if (!PyArg_ParseTuple(args, "OOdi:gray_delta", &prev_obj, &next_obj, &region_threshold, &target_samples)) {
        return nullptr;
    }

    PyObject* prev_seq = PySequence_Fast(prev_obj, "prev_thumb must be a sequence");
    if (prev_seq == nullptr) {
        return nullptr;
    }
    PyObject* next_seq = PySequence_Fast(next_obj, "next_thumb must be a sequence");
    if (next_seq == nullptr) {
        Py_DECREF(prev_seq);
        return nullptr;
    }

    const Py_ssize_t n = std::min(PySequence_Fast_GET_SIZE(prev_seq), PySequence_Fast_GET_SIZE(next_seq));
    std::vector<double> deltas;
    deltas.reserve(static_cast<size_t>(n));
    PyObject** prev_items = PySequence_Fast_ITEMS(prev_seq);
    PyObject** next_items = PySequence_Fast_ITEMS(next_seq);
    for (Py_ssize_t i = 0; i < n; ++i) {
        BufferView left;
        BufferView right;
        if (!get_buffer(prev_items[i], left) || !get_buffer(next_items[i], right)) {
            Py_DECREF(prev_seq);
            Py_DECREF(next_seq);
            return nullptr;
        }
        const auto* left_bytes = static_cast<const unsigned char*>(left.view.buf);
        const auto* right_bytes = static_cast<const unsigned char*>(right.view.buf);
        deltas.push_back(delta_bytes_raw(left_bytes, left.view.len, right_bytes, right.view.len, target_samples));
    }

    Py_DECREF(prev_seq);
    Py_DECREF(next_seq);

    int hits = 0;
    for (double value : deltas) {
        if (value >= region_threshold) {
            ++hits;
        }
    }

    std::vector<double> ranked = deltas;
    std::sort(ranked.begin(), ranked.end(), std::greater<double>());
    const size_t top_n = std::min<size_t>(3, ranked.size());
    double score = 0.0;
    for (size_t i = 0; i < top_n; ++i) {
        score += ranked[i];
    }
    score /= static_cast<double>(top_n > 0 ? top_n : 1);
    return tuple_score_hits_deltas(score, hits, deltas);
}

PyObject* py_color_avg_delta(PyObject*, PyObject* args) {
    PyObject* prev_obj = nullptr;
    PyObject* next_obj = nullptr;
    double threshold = 0.0;
    double weight_luma = 0.0;
    double weight_chroma = 0.0;
    if (!PyArg_ParseTuple(args, "OOddd:color_avg_delta", &prev_obj, &next_obj, &threshold, &weight_luma, &weight_chroma)) {
        return nullptr;
    }

    PyObject* prev_seq = PySequence_Fast(prev_obj, "prev_avg must be a sequence");
    if (prev_seq == nullptr) {
        return nullptr;
    }
    PyObject* next_seq = PySequence_Fast(next_obj, "next_avg must be a sequence");
    if (next_seq == nullptr) {
        Py_DECREF(prev_seq);
        return nullptr;
    }

    const Py_ssize_t n = std::min(PySequence_Fast_GET_SIZE(prev_seq), PySequence_Fast_GET_SIZE(next_seq));
    std::vector<double> deltas;
    deltas.reserve(static_cast<size_t>(n));
    PyObject** prev_items = PySequence_Fast_ITEMS(prev_seq);
    PyObject** next_items = PySequence_Fast_ITEMS(next_seq);
    for (Py_ssize_t i = 0; i < n; ++i) {
        double a0 = 0.0;
        double a1 = 0.0;
        double a2 = 0.0;
        double b0 = 0.0;
        double b1 = 0.0;
        double b2 = 0.0;
        if (!read_triplet(prev_items[i], a0, a1, a2) || !read_triplet(next_items[i], b0, b1, b2)) {
            Py_DECREF(prev_seq);
            Py_DECREF(next_seq);
            return nullptr;
        }
        const double luma = std::abs(a0 - b0);
        const double chroma = (std::abs(a1 - b1) + std::abs(a2 - b2)) / 2.0;
        deltas.push_back(weight_luma * luma + weight_chroma * chroma);
    }

    Py_DECREF(prev_seq);
    Py_DECREF(next_seq);

    int hits = 0;
    double score = 0.0;
    for (double value : deltas) {
        if (value >= threshold) {
            ++hits;
        }
        score += value;
    }
    score /= static_cast<double>(deltas.empty() ? 1 : deltas.size());
    return tuple_score_hits_deltas(score, hits, deltas);
}

PyObject* py_interval_overlaps(PyObject*, PyObject* args) {
    PyObject* segment_starts_obj = nullptr;
    PyObject* segment_ends_obj = nullptr;
    PyObject* vad_starts_obj = nullptr;
    PyObject* vad_ends_obj = nullptr;
    if (!PyArg_ParseTuple(
            args,
            "OOOO:interval_overlaps",
            &segment_starts_obj,
            &segment_ends_obj,
            &vad_starts_obj,
            &vad_ends_obj)) {
        return nullptr;
    }

    std::vector<double> segment_starts;
    std::vector<double> segment_ends;
    std::vector<double> vad_starts;
    std::vector<double> vad_ends;
    if (!sequence_to_doubles(segment_starts_obj, segment_starts) ||
        !sequence_to_doubles(segment_ends_obj, segment_ends) ||
        !sequence_to_doubles(vad_starts_obj, vad_starts) ||
        !sequence_to_doubles(vad_ends_obj, vad_ends)) {
        return nullptr;
    }

    const size_t segment_n = std::min(segment_starts.size(), segment_ends.size());
    const size_t vad_n = std::min(vad_starts.size(), vad_ends.size());
    PyObject* out = PyList_New(static_cast<Py_ssize_t>(segment_n));
    if (out == nullptr) {
        return nullptr;
    }

    for (size_t i = 0; i < segment_n; ++i) {
        const double start = std::max(0.0, segment_starts[i]);
        const double end = std::max(start, segment_ends[i]);
        double overlap = 0.0;
        for (size_t j = 0; j < vad_n; ++j) {
            const double vad_start = vad_starts[j];
            const double vad_end = vad_ends[j];
            overlap += std::max(0.0, std::min(end, vad_end) - std::max(start, vad_start));
        }
        PyObject* item = PyFloat_FromDouble(overlap);
        if (item == nullptr) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, static_cast<Py_ssize_t>(i), item);
    }
    return out;
}

PyMethodDef methods[] = {
    {"delta_bytes", py_delta_bytes, METH_VARARGS, "Sampled byte mean absolute delta."},
    {"gray_delta", py_gray_delta, METH_VARARGS, "Compute sampled gray-region deltas."},
    {"color_avg_delta", py_color_avg_delta, METH_VARARGS, "Compute color average deltas."},
    {"interval_overlaps", py_interval_overlaps, METH_VARARGS, "Compute segment/VAD interval overlaps."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_cut_boundary",
    "Native C++ helpers for cut-boundary verification.",
    -1,
    methods,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_cut_boundary() {
    return PyModule_Create(&module);
}
