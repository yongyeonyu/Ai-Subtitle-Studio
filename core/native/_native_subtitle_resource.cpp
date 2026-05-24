#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <string>
#include <vector>

namespace {

bool read_string_sequence(PyObject* value, std::vector<std::string>& out) {
    PyObject* seq = PySequence_Fast(value, "expected a sequence of strings");
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

bool read_int_sequence(PyObject* value, std::vector<long>& out) {
    PyObject* seq = PySequence_Fast(value, "expected a sequence of integers");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.clear();
    out.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        const long number = PyLong_AsLong(item);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(std::max<long>(0, number));
    }
    Py_DECREF(seq);
    return true;
}

std::string lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

void append_unique(std::vector<std::string>& values, const std::string& value) {
    if (value.empty()) {
        return;
    }
    if (std::find(values.begin(), values.end(), value) == values.end()) {
        values.push_back(value);
    }
}

PyObject* string_list(const std::vector<std::string>& values) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < values.size(); ++i) {
        PyObject* item = PyUnicode_FromString(values[i].c_str());
        if (item == nullptr) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), item);
    }
    return list;
}

bool set_owned_item(PyObject* dict, const char* key, PyObject* value) {
    if (value == nullptr) {
        return false;
    }
    const int status = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    return status == 0;
}

double round6(double value) {
    if (!std::isfinite(value)) {
        return 0.0;
    }
    return std::round(value * 1000000.0) / 1000000.0;
}

PyObject* py_resource_lane_summary(PyObject*, PyObject* args) {
    PyObject* tasks_obj = nullptr;
    PyObject* policies_obj = nullptr;
    PyObject* gpu_lanes_obj = nullptr;
    PyObject* ane_lanes_obj = nullptr;
    long gpu_lane_capacity_arg = 0;
    long ane_model_lane_capacity_arg = 0;
    if (!PyArg_ParseTuple(
            args,
            "OOOO|ll",
            &tasks_obj,
            &policies_obj,
            &gpu_lanes_obj,
            &ane_lanes_obj,
            &gpu_lane_capacity_arg,
            &ane_model_lane_capacity_arg)) {
        return nullptr;
    }

    std::vector<std::string> tasks;
    std::vector<std::string> policies;
    std::vector<long> gpu_lanes;
    std::vector<long> ane_lanes;
    if (!read_string_sequence(tasks_obj, tasks) ||
        !read_string_sequence(policies_obj, policies) ||
        !read_int_sequence(gpu_lanes_obj, gpu_lanes) ||
        !read_int_sequence(ane_lanes_obj, ane_lanes)) {
        return nullptr;
    }

    const size_t count = std::min(std::min(tasks.size(), policies.size()), std::min(gpu_lanes.size(), ane_lanes.size()));
    std::vector<std::string> gpu_tasks;
    std::vector<std::string> ane_tasks;
    std::vector<std::string> metal_tasks;
    long gpu_total = 0;
    long ane_total = 0;
    long max_gpu = 0;
    long max_ane = 0;
    const long gpu_lane_capacity = std::max<long>(0, gpu_lane_capacity_arg);
    const long ane_model_lane_capacity = std::max<long>(0, ane_model_lane_capacity_arg);
    long full_gpu_lane_task_count = 0;
    long full_ane_model_lane_task_count = 0;

    for (size_t i = 0; i < count; ++i) {
        const long gpu = std::max<long>(0, gpu_lanes[i]);
        const long ane = std::max<long>(0, ane_lanes[i]);
        const std::string policy = lower(policies[i]);
        gpu_total += gpu;
        ane_total += ane;
        max_gpu = std::max(max_gpu, gpu);
        max_ane = std::max(max_ane, ane);
        if (gpu > 0) {
            append_unique(gpu_tasks, tasks[i]);
        }
        if (ane > 0) {
            append_unique(ane_tasks, tasks[i]);
        }
        if (policy.find("metal") != std::string::npos) {
            append_unique(metal_tasks, tasks[i]);
        }
        // 변경 금지: ANE physical core 점유율이 아니라 Core ML/WhisperKit 모델 동시 처리 lane 포화 진단이다.
        // Swift summary와 같은 capacity를 받아 benchmark artifact의 full GPU/ANE 확인에만 사용하고, 정책은 바꾸지 않는다.
        if (gpu_lane_capacity > 0 && gpu >= gpu_lane_capacity) {
            ++full_gpu_lane_task_count;
        }
        if (ane_model_lane_capacity > 0 && ane >= ane_model_lane_capacity) {
            ++full_ane_model_lane_task_count;
        }
    }
    const double gpu_lane_peak_ratio = gpu_lane_capacity > 0 ? static_cast<double>(max_gpu) / static_cast<double>(gpu_lane_capacity) : 0.0;
    const double ane_model_lane_peak_ratio =
        ane_model_lane_capacity > 0 ? static_cast<double>(max_ane) / static_cast<double>(ane_model_lane_capacity) : 0.0;

    PyObject* result = PyDict_New();
    if (result == nullptr) {
        return nullptr;
    }
    const bool ok =
        set_owned_item(result, "schema", PyUnicode_FromString("ai_subtitle_studio.subtitle_resource.summary.v1")) &&
        set_owned_item(result, "task_count", PyLong_FromSize_t(count)) &&
        set_owned_item(result, "gpu_task_count", PyLong_FromSize_t(gpu_tasks.size())) &&
        set_owned_item(result, "ane_task_count", PyLong_FromSize_t(ane_tasks.size())) &&
        set_owned_item(result, "metal_task_count", PyLong_FromSize_t(metal_tasks.size())) &&
        set_owned_item(result, "gpu_lanes_total", PyLong_FromLong(gpu_total)) &&
        set_owned_item(result, "ane_lanes_total", PyLong_FromLong(ane_total)) &&
        set_owned_item(result, "max_gpu_lanes", PyLong_FromLong(max_gpu)) &&
        set_owned_item(result, "max_ane_lanes", PyLong_FromLong(max_ane)) &&
        set_owned_item(result, "gpu_lane_capacity", PyLong_FromLong(gpu_lane_capacity)) &&
        set_owned_item(result, "ane_model_lane_capacity", PyLong_FromLong(ane_model_lane_capacity)) &&
        set_owned_item(result, "gpu_lane_peak_ratio", PyFloat_FromDouble(round6(gpu_lane_peak_ratio))) &&
        set_owned_item(result, "ane_model_lane_peak_ratio", PyFloat_FromDouble(round6(ane_model_lane_peak_ratio))) &&
        set_owned_item(result, "full_gpu_lane_task_count", PyLong_FromLong(full_gpu_lane_task_count)) &&
        set_owned_item(result, "full_ane_model_lane_task_count", PyLong_FromLong(full_ane_model_lane_task_count)) &&
        set_owned_item(result, "gpu_lane_peak_saturated", PyBool_FromLong(gpu_lane_capacity > 0 && max_gpu >= gpu_lane_capacity)) &&
        set_owned_item(result, "ane_model_lane_peak_saturated", PyBool_FromLong(ane_model_lane_capacity > 0 && max_ane >= ane_model_lane_capacity)) &&
        set_owned_item(result, "gpu_tasks", string_list(gpu_tasks)) &&
        set_owned_item(result, "ane_tasks", string_list(ane_tasks)) &&
        set_owned_item(result, "metal_tasks", string_list(metal_tasks)) &&
        set_owned_item(result, "metal_claims_ane", PyBool_FromLong(0));
    if (!ok) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

PyMethodDef methods[] = {
    {"resource_lane_summary", py_resource_lane_summary, METH_VARARGS, "Summarize accelerator lanes for native subtitle resource plans."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_subtitle_resource",
    "Native subtitle resource summary helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_subtitle_resource(void) {
    return PyModule_Create(&module);
}
