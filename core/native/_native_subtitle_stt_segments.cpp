#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cstdint>
#include <cmath>
#include <iomanip>
#include <sstream>
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

constexpr uint64_t kTimelineFeedSignatureOffset = 1469598103934665603ULL;
constexpr uint64_t kTimelineFeedSignaturePrime = 1099511628211ULL;

void mix_signature_value(uint64_t& hash, long long value) {
    // 변경 금지: STT 후보 lane -> timeline feed가 같은 입력인지 추적하는 계약입니다.
    // Swift/Python fallback과 같은 순서/반올림/overflow를 유지해야 자막-에디터 싱크 디버깅이 가능합니다.
    hash ^= static_cast<uint64_t>(value);
    hash *= kTimelineFeedSignaturePrime;
}

std::string signature_hex(uint64_t hash) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(16) << hash;
    return out.str();
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
    uint64_t timeline_feed_signature = kTimelineFeedSignatureOffset;
    bool has_stt2 = false;
    double stt2_first_start = 0.0;
    double stt2_last_end = 0.0;
    bool has_current_stt2_run = false;
    double current_stt2_run_start = 0.0;
    double current_stt2_run_end = 0.0;
    long current_stt2_run_count = 0;
    double longest_stt2_run_sec = 0.0;
    double longest_stt2_run_start = 0.0;
    double longest_stt2_run_end = 0.0;
    long longest_stt2_run_count = 0;

    auto flush_stt2_run = [&]() {
        if (!has_current_stt2_run) {
            return;
        }
        const double run_sec = std::max(0.0, current_stt2_run_end - current_stt2_run_start);
        if (run_sec > longest_stt2_run_sec ||
            (std::abs(run_sec - longest_stt2_run_sec) <= 0.000000001 &&
             current_stt2_run_count > longest_stt2_run_count)) {
            longest_stt2_run_sec = run_sec;
            longest_stt2_run_start = current_stt2_run_start;
            longest_stt2_run_end = current_stt2_run_end;
            longest_stt2_run_count = current_stt2_run_count;
        }
        has_current_stt2_run = false;
        current_stt2_run_start = 0.0;
        current_stt2_run_end = 0.0;
        current_stt2_run_count = 0;
    };

    for (size_t i = 0; i < count; ++i) {
        const double start = starts[i];
        const double end = ends[i];
        const double duration = std::max(0.0, end - start);
        const long source_code = source_codes[i];
        const bool is_stt2_source = source_code == 2 || source_code == 3;
        mix_signature_value(timeline_feed_signature, static_cast<long long>(std::llround(start * 1000.0)));
        mix_signature_value(timeline_feed_signature, static_cast<long long>(std::llround(end * 1000.0)));
        mix_signature_value(timeline_feed_signature, static_cast<long long>(source_code));
        mix_signature_value(timeline_feed_signature, static_cast<long long>(recheck_flags[i] != 0 ? 1 : 0));
        mix_signature_value(timeline_feed_signature, static_cast<long long>(precision_flags[i] != 0 ? 1 : 0));
        mix_signature_value(timeline_feed_signature, static_cast<long long>(secondary_hint_flags[i] != 0 ? 1 : 0));
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
        // 변경 금지: STT2/RECHECK 연속 선택 구간은 자막 생성 정책이 아니라 X5/Macau artifact 진단값입니다.
        // Swift/Python fallback과 동일하게 "연속된 STT2 계열 row"만 묶어 자막-에디터 드리프트 원인 추적에 사용합니다.
        if (is_stt2_source) {
            if (!has_stt2) {
                has_stt2 = true;
                stt2_first_start = start;
                stt2_last_end = end;
            } else {
                stt2_last_end = std::max(stt2_last_end, end);
            }
            if (!has_current_stt2_run) {
                has_current_stt2_run = true;
                current_stt2_run_start = start;
                current_stt2_run_end = end;
                current_stt2_run_count = 1;
            } else {
                current_stt2_run_end = std::max(current_stt2_run_end, end);
                ++current_stt2_run_count;
            }
        } else {
            flush_stt2_run();
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
    flush_stt2_run();

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
        set_item(result, "stt2_first_start", PyFloat_FromDouble(round6(has_stt2 ? stt2_first_start : 0.0))) != 0 ||
        set_item(result, "stt2_last_end", PyFloat_FromDouble(round6(has_stt2 ? stt2_last_end : 0.0))) != 0 ||
        set_item(result, "longest_stt2_run_sec", PyFloat_FromDouble(round6(longest_stt2_run_sec))) != 0 ||
        set_item(result, "longest_stt2_run_start", PyFloat_FromDouble(round6(longest_stt2_run_start))) != 0 ||
        set_item(result, "longest_stt2_run_end", PyFloat_FromDouble(round6(longest_stt2_run_end))) != 0 ||
        set_item(result, "longest_stt2_run_count", PyLong_FromLong(longest_stt2_run_count)) != 0 ||
        set_item(result, "stt2_active", PyBool_FromLong(stt2_selected_count > 0 || recheck_applied_count > 0)) != 0 ||
        set_item(result, "selective_recheck_active", PyBool_FromLong(recheck_applied_count > 0)) != 0 ||
        set_item(result, "stable_for_timeline_feed", PyBool_FromLong(invalid_duration_count == 0 && non_monotonic_count == 0)) != 0 ||
        set_item(result, "timeline_feed_signature", PyUnicode_FromString(signature_hex(timeline_feed_signature).c_str())) != 0 ||
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
