#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>

namespace {

struct BufferView {
    Py_buffer view{};
    bool ok = false;

    ~BufferView() {
        if (ok) {
            PyBuffer_Release(&view);
        }
    }
};

bool get_buffer(PyObject* obj, BufferView& out) {
    if (obj == nullptr) {
        PyErr_SetString(PyExc_ValueError, "missing buffer");
        return false;
    }
    if (PyObject_GetBuffer(obj, &out.view, PyBUF_SIMPLE) != 0) {
        return false;
    }
    out.ok = true;
    return true;
}

float read_float32_unaligned(const char* ptr) {
    uint32_t bits = 0;
    std::memcpy(&bits, ptr, sizeof(bits));
    float value = 0.0f;
    std::memcpy(&value, &bits, sizeof(value));
    return std::isfinite(value) ? value : 0.0f;
}

PyObject* empty_downsample_result() {
    PyObject* empty = PyBytes_FromStringAndSize("", 0);
    if (empty == nullptr) {
        return nullptr;
    }
    PyObject* out = Py_BuildValue("(Od)", empty, 0.0);
    Py_DECREF(empty);
    return out;
}

PyObject* py_downsample_f32le(PyObject*, PyObject* args) {
    PyObject* raw_obj = nullptr;
    int sample_rate = 2000;
    int points_per_second = 100;
    double duration = 0.0;
    if (!PyArg_ParseTuple(args, "Oiid:downsample_f32le", &raw_obj, &sample_rate, &points_per_second, &duration)) {
        return nullptr;
    }

    BufferView raw;
    if (!get_buffer(raw_obj, raw)) {
        return nullptr;
    }
    const Py_ssize_t sample_count = raw.view.len / static_cast<Py_ssize_t>(sizeof(float));
    if (sample_count < 2 || sample_rate <= 0 || points_per_second <= 0) {
        return empty_downsample_result();
    }

    double dur = duration > 0.0 ? duration : static_cast<double>(sample_count) / static_cast<double>(sample_rate);
    if (!(dur > 0.0) || !std::isfinite(dur)) {
        dur = static_cast<double>(sample_count) / static_cast<double>(sample_rate);
    }
    const Py_ssize_t total_points = std::max<Py_ssize_t>(1, static_cast<Py_ssize_t>(dur * static_cast<double>(points_per_second)));
    const Py_ssize_t chunk = std::max<Py_ssize_t>(1, sample_count / total_points);
    const Py_ssize_t trim = (sample_count / chunk) * chunk;
    const Py_ssize_t out_count = std::min(total_points, trim / chunk);
    if (out_count <= 0) {
        return empty_downsample_result();
    }

    std::vector<float> peaks(static_cast<size_t>(out_count), 0.0f);
    const auto* samples = static_cast<const char*>(raw.view.buf);
    float max_peak = 0.0f;

    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t i = 0; i < out_count; ++i) {
        float peak = 0.0f;
        const Py_ssize_t base = i * chunk;
        for (Py_ssize_t j = 0; j < chunk; ++j) {
            const char* ptr = samples + (base + j) * static_cast<Py_ssize_t>(sizeof(float));
            const float value = std::abs(read_float32_unaligned(ptr));
            if (value > peak) {
                peak = value;
            }
        }
        peaks[static_cast<size_t>(i)] = peak;
        if (peak > max_peak) {
            max_peak = peak;
        }
    }
    if (max_peak > 1e-6f) {
        for (float& value : peaks) {
            value /= max_peak;
        }
    }
    Py_END_ALLOW_THREADS

    PyObject* bytes = PyBytes_FromStringAndSize(
        reinterpret_cast<const char*>(peaks.data()),
        static_cast<Py_ssize_t>(peaks.size() * sizeof(float))
    );
    if (bytes == nullptr) {
        return nullptr;
    }
    PyObject* out = Py_BuildValue("(Od)", bytes, dur);
    Py_DECREF(bytes);
    return out;
}

int set_item(PyObject* dict, const char* key, PyObject* value) {
    if (value == nullptr) {
        return -1;
    }
    const int rc = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    return rc;
}

PyObject* py_waveform_summary(PyObject*, PyObject* args) {
    PyObject* values_obj = nullptr;
    double threshold = 0.02;
    if (!PyArg_ParseTuple(args, "O|d:waveform_summary", &values_obj, &threshold)) {
        return nullptr;
    }

    BufferView values;
    if (!get_buffer(values_obj, values)) {
        return nullptr;
    }
    const Py_ssize_t count = values.view.len / static_cast<Py_ssize_t>(sizeof(float));
    const auto* samples = static_cast<const char*>(values.view.buf);
    double max_peak = 0.0;
    double sum_peak = 0.0;
    Py_ssize_t speech_like = 0;

    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t i = 0; i < count; ++i) {
        const char* ptr = samples + i * static_cast<Py_ssize_t>(sizeof(float));
        const double peak = static_cast<double>(std::abs(read_float32_unaligned(ptr)));
        if (peak > max_peak) {
            max_peak = peak;
        }
        sum_peak += peak;
        if (peak >= threshold) {
            ++speech_like;
        }
    }
    Py_END_ALLOW_THREADS

    const double mean_peak = count > 0 ? sum_peak / static_cast<double>(count) : 0.0;
    const double speech_ratio = count > 0 ? static_cast<double>(speech_like) / static_cast<double>(count) : 0.0;
    PyObject* result = PyDict_New();
    if (result == nullptr) {
        return nullptr;
    }
    if (set_item(result, "schema", PyUnicode_FromString("ai_subtitle_studio.subtitle_waveform.summary.v1")) != 0 ||
        set_item(result, "sample_count", PyLong_FromSsize_t(count)) != 0 ||
        set_item(result, "max_peak", PyFloat_FromDouble(max_peak)) != 0 ||
        set_item(result, "mean_peak", PyFloat_FromDouble(mean_peak)) != 0 ||
        set_item(result, "speech_like_count", PyLong_FromSsize_t(speech_like)) != 0 ||
        set_item(result, "speech_like_ratio", PyFloat_FromDouble(speech_ratio)) != 0 ||
        set_item(result, "native_backend", PyUnicode_FromString("cpp")) != 0) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

PyMethodDef methods[] = {
    {"downsample_f32le", py_downsample_f32le, METH_VARARGS, "Downsample f32le PCM bytes into normalized subtitle waveform peaks."},
    {"waveform_summary", py_waveform_summary, METH_VARARGS, "Summarize normalized f32 subtitle waveform peaks."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_subtitle_waveform",
    "Native subtitle waveform helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_subtitle_waveform(void) {
    return PyModule_Create(&module);
}
