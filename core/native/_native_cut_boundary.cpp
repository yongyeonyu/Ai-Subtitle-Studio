#include <Python.h>

#include <algorithm>
#include <cstring>
#include <cmath>
#include <utility>
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

bool get_buffer(PyObject* obj, BufferView& out, int flags = PyBUF_SIMPLE) {
    if (PyObject_GetBuffer(obj, &out.view, flags) != 0) {
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

bool dict_set_double(PyObject* dict, const char* key, double value) {
    PyObject* item = PyFloat_FromDouble(value);
    if (item == nullptr) {
        return false;
    }
    const int status = PyDict_SetItemString(dict, key, item);
    Py_DECREF(item);
    return status == 0;
}

bool dict_set_long(PyObject* dict, const char* key, long value) {
    PyObject* item = PyLong_FromLong(value);
    if (item == nullptr) {
        return false;
    }
    const int status = PyDict_SetItemString(dict, key, item);
    Py_DECREF(item);
    return status == 0;
}

float read_float32_unaligned(const char* ptr) {
    float value = 0.0f;
    std::memcpy(&value, ptr, sizeof(float));
    return value;
}

unsigned char read_u8_at(const BufferView& view, Py_ssize_t y, Py_ssize_t x) {
    const auto* base = static_cast<const char*>(view.view.buf);
    return *reinterpret_cast<const unsigned char*>(base + y * view.view.strides[0] + x * view.view.strides[1]);
}

float read_flow_at(const BufferView& view, Py_ssize_t y, Py_ssize_t x, Py_ssize_t channel) {
    const auto* base = static_cast<const char*>(view.view.buf);
    const char* ptr = base + y * view.view.strides[0] + x * view.view.strides[1] + channel * view.view.strides[2];
    return read_float32_unaligned(ptr);
}

double clamp_double(double value, double lo, double hi) {
    return std::max(lo, std::min(hi, value));
}

double sample_bilinear_replicate_u8(const BufferView& view, Py_ssize_t h, Py_ssize_t w, double x, double y) {
    if (h <= 0 || w <= 0) {
        return 0.0;
    }
    x = clamp_double(x, 0.0, static_cast<double>(w - 1));
    y = clamp_double(y, 0.0, static_cast<double>(h - 1));
    const auto x0 = static_cast<Py_ssize_t>(std::floor(x));
    const auto y0 = static_cast<Py_ssize_t>(std::floor(y));
    const Py_ssize_t x1 = std::min<Py_ssize_t>(w - 1, x0 + 1);
    const Py_ssize_t y1 = std::min<Py_ssize_t>(h - 1, y0 + 1);
    const double wx = x - static_cast<double>(x0);
    const double wy = y - static_cast<double>(y0);

    const double v00 = static_cast<double>(read_u8_at(view, y0, x0));
    const double v10 = static_cast<double>(read_u8_at(view, y0, x1));
    const double v01 = static_cast<double>(read_u8_at(view, y1, x0));
    const double v11 = static_cast<double>(read_u8_at(view, y1, x1));
    const double top = v00 * (1.0 - wx) + v10 * wx;
    const double bottom = v01 * (1.0 - wx) + v11 * wx;
    return top * (1.0 - wy) + bottom * wy;
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

bool sequence_to_ints(PyObject* obj, std::vector<int>& out) {
    PyObject* seq = PySequence_Fast(obj, "expected a sequence of integers");
    if (seq == nullptr) {
        return false;
    }

    const Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    out.reserve(static_cast<size_t>(n));
    PyObject** items = PySequence_Fast_ITEMS(seq);
    for (Py_ssize_t i = 0; i < n; ++i) {
        const long value = PyLong_AsLong(items[i]);
        if (PyErr_Occurred()) {
            Py_DECREF(seq);
            return false;
        }
        out.push_back(static_cast<int>(value));
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

PyObject* py_dense_flow_pair_metrics(PyObject*, PyObject* args) {
    PyObject* prev_obj = nullptr;
    PyObject* next_obj = nullptr;
    PyObject* flow_obj = nullptr;
    double diff_threshold = 18.0;
    if (!PyArg_ParseTuple(
            args,
            "OOOd:dense_flow_pair_metrics",
            &prev_obj,
            &next_obj,
            &flow_obj,
            &diff_threshold)) {
        return nullptr;
    }

    BufferView prev;
    BufferView next;
    BufferView flow;
    const int buffer_flags = PyBUF_ND | PyBUF_STRIDES;
    if (!get_buffer(prev_obj, prev, buffer_flags) ||
        !get_buffer(next_obj, next, buffer_flags) ||
        !get_buffer(flow_obj, flow, buffer_flags)) {
        return nullptr;
    }

    if (prev.view.ndim != 2 || next.view.ndim != 2 || flow.view.ndim < 3) {
        PyErr_SetString(PyExc_ValueError, "expected prev/next gray arrays and HxWx2 flow array");
        return nullptr;
    }
    const Py_ssize_t h = prev.view.shape[0];
    const Py_ssize_t w = prev.view.shape[1];
    if (h <= 0 || w <= 0 ||
        next.view.shape[0] != h || next.view.shape[1] != w ||
        flow.view.shape[0] != h || flow.view.shape[1] != w || flow.view.shape[2] < 2) {
        PyErr_SetString(PyExc_ValueError, "dense flow inputs must have matching shapes");
        return nullptr;
    }
    if (prev.view.itemsize != 1 || next.view.itemsize != 1 || flow.view.itemsize != static_cast<Py_ssize_t>(sizeof(float))) {
        PyErr_SetString(PyExc_ValueError, "expected uint8 gray arrays and float32 flow array");
        return nullptr;
    }

    double diff_sum = 0.0;
    double residual_sum = 0.0;
    double mag_sum = 0.0;
    double fx_sum = 0.0;
    double fy_sum = 0.0;
    long coverage_count = 0;
    long count = 0;

    Py_BEGIN_ALLOW_THREADS
    for (Py_ssize_t y = 0; y < h; ++y) {
        for (Py_ssize_t x = 0; x < w; ++x) {
            const double prev_value = static_cast<double>(read_u8_at(prev, y, x));
            const double next_value = static_cast<double>(read_u8_at(next, y, x));
            const double diff = std::abs(prev_value - next_value);
            diff_sum += diff;
            if (diff >= diff_threshold) {
                ++coverage_count;
            }

            double fx = static_cast<double>(read_flow_at(flow, y, x, 0));
            double fy = static_cast<double>(read_flow_at(flow, y, x, 1));
            if (!std::isfinite(fx)) {
                fx = 0.0;
            }
            if (!std::isfinite(fy)) {
                fy = 0.0;
            }
            fx_sum += fx;
            fy_sum += fy;
            mag_sum += std::sqrt(fx * fx + fy * fy);

            const double warped = sample_bilinear_replicate_u8(prev, h, w, static_cast<double>(x) - fx, static_cast<double>(y) - fy);
            residual_sum += std::abs(warped - next_value);
            ++count;
        }
    }
    Py_END_ALLOW_THREADS

    const double denom = static_cast<double>(count > 0 ? count : 1);
    const double diff_before = diff_sum / denom;
    const double residual = residual_sum / denom;
    const double coverage = static_cast<double>(coverage_count) / denom;
    const double mean_mag = mag_sum / denom;
    const double mean_fx = fx_sum / denom;
    const double mean_fy = fy_sum / denom;
    const double coherence = std::sqrt(mean_fx * mean_fx + mean_fy * mean_fy) / std::max(mean_mag, 1e-6);
    const double residual_ratio = residual / std::max(diff_before, 1e-6);

    PyObject* out = PyDict_New();
    if (out == nullptr) {
        return nullptr;
    }
    if (!dict_set_double(out, "diff", diff_before) ||
        !dict_set_double(out, "residual", residual) ||
        !dict_set_double(out, "residual_ratio", residual_ratio) ||
        !dict_set_double(out, "coverage", coverage) ||
        !dict_set_double(out, "mean_motion_px", mean_mag) ||
        !dict_set_double(out, "mean_fx", mean_fx) ||
        !dict_set_double(out, "mean_fy", mean_fy) ||
        !dict_set_double(out, "coherence", coherence) ||
        !dict_set_long(out, "pixel_count", count)) {
        Py_DECREF(out);
        return nullptr;
    }
    return out;
}

PyObject* py_waveform_peaks_f32le(PyObject*, PyObject* args) {
    PyObject* raw_obj = nullptr;
    int sample_rate = 2000;
    int points_per_second = 100;
    double duration = 0.0;
    if (!PyArg_ParseTuple(
            args,
            "Oiid:waveform_peaks_f32le",
            &raw_obj,
            &sample_rate,
            &points_per_second,
            &duration)) {
        return nullptr;
    }

    BufferView raw;
    if (!get_buffer(raw_obj, raw, PyBUF_SIMPLE)) {
        return nullptr;
    }
    const Py_ssize_t sample_count = raw.view.len / static_cast<Py_ssize_t>(sizeof(float));
    if (sample_count < 2 || sample_rate <= 0 || points_per_second <= 0) {
        PyObject* empty = PyBytes_FromStringAndSize("", 0);
        if (empty == nullptr) {
            return nullptr;
        }
        PyObject* out = Py_BuildValue("(Od)", empty, 0.0);
        Py_DECREF(empty);
        return out;
    }

    double dur = duration > 0.0 ? duration : static_cast<double>(sample_count) / static_cast<double>(sample_rate);
    if (!(dur > 0.0) || !std::isfinite(dur)) {
        dur = static_cast<double>(sample_count) / static_cast<double>(sample_rate);
    }
    const Py_ssize_t total_px = std::max<Py_ssize_t>(1, static_cast<Py_ssize_t>(dur * static_cast<double>(points_per_second)));
    const Py_ssize_t chunk = std::max<Py_ssize_t>(1, sample_count / total_px);
    const Py_ssize_t trim = (sample_count / chunk) * chunk;
    const Py_ssize_t out_count = std::min(total_px, trim / chunk);
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

PyObject* py_word_split_groups(PyObject*, PyObject* args) {
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
    if (!PyArg_ParseTuple(
            args,
            "OOOOOiddddd:word_split_groups",
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
            &word_gap_break_sec)) {
        return nullptr;
    }

    std::vector<double> starts;
    std::vector<double> ends;
    std::vector<int> char_counts;
    std::vector<int> natural_breaks;
    std::vector<int> vad_indexes;
    if (!sequence_to_doubles(starts_obj, starts) ||
        !sequence_to_doubles(ends_obj, ends) ||
        !sequence_to_ints(chars_obj, char_counts) ||
        !sequence_to_ints(natural_obj, natural_breaks) ||
        !sequence_to_ints(vad_obj, vad_indexes)) {
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

    PyObject* out = PyList_New(static_cast<Py_ssize_t>(groups.size()));
    if (out == nullptr) {
        return nullptr;
    }
    for (size_t i = 0; i < groups.size(); ++i) {
        PyObject* item = Py_BuildValue("(nn)", static_cast<Py_ssize_t>(groups[i].first), static_cast<Py_ssize_t>(groups[i].second));
        if (item == nullptr) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, static_cast<Py_ssize_t>(i), item);
    }
    return out;
}

PyObject* py_llm_macro_group_ranges(PyObject*, PyObject* args) {
    PyObject* cut_obj = nullptr;
    PyObject* needs_obj = nullptr;
    int min_rows = 10;
    int max_rows = 15;
    if (!PyArg_ParseTuple(args, "OOii:llm_macro_group_ranges", &cut_obj, &needs_obj, &min_rows, &max_rows)) {
        return nullptr;
    }

    std::vector<int> cut_before;
    std::vector<int> needs_llm;
    if (!sequence_to_ints(cut_obj, cut_before) || !sequence_to_ints(needs_obj, needs_llm)) {
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
                current_need_count = 0;
                current_len = 0;
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

    PyObject* out = PyList_New(static_cast<Py_ssize_t>(groups.size()));
    if (out == nullptr) {
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
    {"dense_flow_pair_metrics", py_dense_flow_pair_metrics, METH_VARARGS, "Compute dense optical-flow pair metrics without NumPy temporaries."},
    {"waveform_peaks_f32le", py_waveform_peaks_f32le, METH_VARARGS, "Downsample f32le PCM bytes into normalized waveform peaks."},
    {"interval_overlaps", py_interval_overlaps, METH_VARARGS, "Compute segment/VAD interval overlaps."},
    {"word_split_groups", py_word_split_groups, METH_VARARGS, "Split word indexes into subtitle groups with native C++ thresholds."},
    {"llm_macro_group_ranges", py_llm_macro_group_ranges, METH_VARARGS, "Build LLM macro group ranges from cut and review flags."},
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
