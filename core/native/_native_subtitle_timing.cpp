#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <vector>

namespace {

bool read_float_sequence(PyObject* value, std::vector<double>& out) {
    PyObject* seq = PySequence_Fast(value, "expected a sequence of numbers");
    if (seq == nullptr) {
        return false;
    }
    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.clear();
    out.reserve(static_cast<size_t>(std::max<Py_ssize_t>(0, n)));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        const double number = PyFloat_AsDouble(item);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(number);
    }
    Py_DECREF(seq);
    return true;
}

double overlap(double left_start, double left_end, double right_start, double right_end) {
    const double start = std::max(left_start, right_start);
    const double end = std::min(left_end, right_end);
    return std::max(0.0, end - start);
}

PyObject* build_metrics_result(double timing_mae, double overlap_score, int matched_pairs,
                               const std::vector<size_t>& matched_reference_indices,
                               double max_start_error, double max_end_error,
                               double max_pair_timing_error, long worst_hypothesis_index,
                               long worst_reference_index) {
    PyObject* matched_indices = PyList_New(static_cast<Py_ssize_t>(matched_reference_indices.size()));
    if (matched_indices == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < matched_reference_indices.size(); ++i) {
        PyObject* value = PyLong_FromSize_t(matched_reference_indices[i]);
        if (value == nullptr) {
            Py_DECREF(matched_indices);
            return nullptr;
        }
        PyList_SET_ITEM(matched_indices, static_cast<Py_ssize_t>(i), value);
    }

    PyObject* result = Py_BuildValue("{s:d,s:d,s:i,s:d,s:d,s:d,s:l,s:l}",
                                     "timing_mae_sec", timing_mae,
                                     "overlap_score", overlap_score,
                                     "matched_pairs", matched_pairs,
                                     "max_start_error_sec", max_start_error,
                                     "max_end_error_sec", max_end_error,
                                     "max_pair_timing_error_sec", max_pair_timing_error,
                                     "worst_match_hypothesis_index", worst_hypothesis_index,
                                     "worst_match_reference_index", worst_reference_index);
    if (result == nullptr) {
        Py_DECREF(matched_indices);
        return nullptr;
    }
    if (PyDict_SetItemString(result, "matched_reference_indices", matched_indices) != 0) {
        Py_DECREF(matched_indices);
        Py_DECREF(result);
        return nullptr;
    }
    Py_DECREF(matched_indices);
    return result;
}

PyObject* py_timing_metrics(PyObject*, PyObject* args) {
    PyObject* hyp_starts_obj = nullptr;
    PyObject* hyp_ends_obj = nullptr;
    PyObject* ref_starts_obj = nullptr;
    PyObject* ref_ends_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OOOO", &hyp_starts_obj, &hyp_ends_obj, &ref_starts_obj, &ref_ends_obj)) {
        return nullptr;
    }

    std::vector<double> hyp_starts;
    std::vector<double> hyp_ends;
    std::vector<double> ref_starts;
    std::vector<double> ref_ends;
    if (!read_float_sequence(hyp_starts_obj, hyp_starts) ||
        !read_float_sequence(hyp_ends_obj, hyp_ends) ||
        !read_float_sequence(ref_starts_obj, ref_starts) ||
        !read_float_sequence(ref_ends_obj, ref_ends)) {
        return nullptr;
    }

    const size_t hyp_count = std::min(hyp_starts.size(), hyp_ends.size());
    const size_t ref_count = std::min(ref_starts.size(), ref_ends.size());
    if (hyp_count == 0 || ref_count == 0) {
        const std::vector<size_t> empty_indices;
        return build_metrics_result(0.0, 0.0, 0, empty_indices, 0.0, 0.0, 0.0, -1, -1);
    }

    double total_timing_error = 0.0;
    double total_overlap_score = 0.0;
    double max_start_error = 0.0;
    double max_end_error = 0.0;
    double max_pair_timing_error = 0.0;
    long worst_hypothesis_index = -1;
    long worst_reference_index = -1;
    int matched_pairs = 0;
    std::vector<size_t> matched_reference_indices;
    matched_reference_indices.reserve(hyp_count);

    Py_BEGIN_ALLOW_THREADS
    for (size_t i = 0; i < hyp_count; ++i) {
        const double hyp_start = hyp_starts[i];
        const double hyp_end = hyp_ends[i];
        const double hyp_mid = (hyp_start + hyp_end) / 2.0;
        double best_score = -1.0;
        size_t best_index = 0;

        for (size_t j = 0; j < ref_count; ++j) {
            const double ref_start = ref_starts[j];
            const double ref_end = ref_ends[j];
            const double ref_mid = (ref_start + ref_end) / 2.0;
            const double prox = std::max(0.0, 1.0 - std::abs(hyp_mid - ref_mid) / 4.0);
            const double score = overlap(hyp_start, hyp_end, ref_start, ref_end) * 2.0 + prox;
            if (score > best_score) {
                best_score = score;
                best_index = j;
            }
        }

        const double ref_start = ref_starts[best_index];
        const double ref_end = ref_ends[best_index];
        const double start_err = std::abs(hyp_start - ref_start);
        const double end_err = std::abs(hyp_end - ref_end);
        const double pair_timing_error = (start_err + end_err) / 2.0;
        const double hyp_span = hyp_end - hyp_start;
        const double ref_span = ref_end - ref_start;
        const double span = std::max(0.001, std::max(hyp_span, ref_span));
        // 변경 금지: X5/실앱 벤치에서 평균값만으로 숨는 자막 타이밍 drift를 찾기 위한 native timing 계약입니다.
        // Swift/Python benchmark fallback과 같은 match owner를 기준으로 최대 start/end/pair 오차를 기록합니다.
        max_start_error = std::max(max_start_error, start_err);
        max_end_error = std::max(max_end_error, end_err);
        if (pair_timing_error > max_pair_timing_error) {
            max_pair_timing_error = pair_timing_error;
            worst_hypothesis_index = static_cast<long>(i);
            worst_reference_index = static_cast<long>(best_index);
        }
        total_timing_error += pair_timing_error;
        total_overlap_score += std::min(1.0, overlap(hyp_start, hyp_end, ref_start, ref_end) / span);
        ++matched_pairs;
        matched_reference_indices.push_back(best_index);
    }
    Py_END_ALLOW_THREADS

    const double denom = std::max(1, matched_pairs);
    return build_metrics_result(total_timing_error / denom,
                                (total_overlap_score / denom) * 100.0,
                                matched_pairs,
                                matched_reference_indices,
                                max_start_error,
                                max_end_error,
                                max_pair_timing_error,
                                worst_hypothesis_index,
                                worst_reference_index);
}

PyMethodDef methods[] = {
    {"timing_metrics", py_timing_metrics, METH_VARARGS, "Compute subtitle timing MAE and overlap score."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_native_subtitle_timing",
    "Native subtitle timing metric helpers.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_subtitle_timing(void) {
    return PyModule_Create(&module);
}
