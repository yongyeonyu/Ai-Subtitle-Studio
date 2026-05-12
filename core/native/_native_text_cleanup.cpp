#include <Python.h>

#include <algorithm>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

struct ReplacementPair {
    std::string old_value;
    std::string new_value;
    std::string first_key;
    std::vector<std::string> activation_keys;
};

struct CompiledCorrections {
    std::vector<ReplacementPair> pairs;
    std::unordered_map<std::string, std::vector<size_t>> by_first_key;
};

constexpr const char* kCompiledCorrectionsCapsuleName =
    "ai_subtitle_studio.CompiledTextCorrections";

size_t utf8_codepoint_size(unsigned char lead) {
    if ((lead & 0x80u) == 0u) {
        return 1;
    }
    if ((lead & 0xE0u) == 0xC0u) {
        return 2;
    }
    if ((lead & 0xF0u) == 0xE0u) {
        return 3;
    }
    if ((lead & 0xF8u) == 0xF0u) {
        return 4;
    }
    return 1;
}

std::string first_utf8_key(const std::string& text) {
    if (text.empty()) {
        return {};
    }
    const auto width = std::min(text.size(), utf8_codepoint_size(static_cast<unsigned char>(text[0])));
    return text.substr(0, width);
}

std::vector<std::string> utf8_keys_in_text(const std::string& text) {
    std::vector<std::string> out;
    std::unordered_set<std::string> seen;
    size_t pos = 0;
    while (pos < text.size()) {
        const auto width = std::min(text.size() - pos, utf8_codepoint_size(static_cast<unsigned char>(text[pos])));
        std::string key = text.substr(pos, width);
        if (!key.empty() && seen.insert(key).second) {
            out.push_back(std::move(key));
        }
        pos += width;
    }
    return out;
}

bool unicode_to_string(PyObject* obj, std::string& out) {
    if (!PyUnicode_Check(obj)) {
        PyErr_SetString(PyExc_TypeError, "expected a string");
        return false;
    }
    Py_ssize_t size = 0;
    const char* value = PyUnicode_AsUTF8AndSize(obj, &size);
    if (value == nullptr) {
        return false;
    }
    out.assign(value, static_cast<size_t>(size));
    return true;
}

bool correction_pairs_from_obj(PyObject* obj, CompiledCorrections& out) {
    if (obj == nullptr || obj == Py_None) {
        return true;
    }
    if (!PyDict_Check(obj)) {
        PyErr_SetString(PyExc_TypeError, "corrections must be a dict");
        return false;
    }
    Py_ssize_t pos = 0;
    PyObject* key = nullptr;
    PyObject* value = nullptr;
    while (PyDict_Next(obj, &pos, &key, &value)) {
        std::string old_value;
        std::string new_value;
        if (!unicode_to_string(key, old_value) || !unicode_to_string(value, new_value)) {
            return false;
        }
        if (old_value.empty()) {
            continue;
        }
        ReplacementPair pair;
        pair.old_value = std::move(old_value);
        pair.new_value = std::move(new_value);
        pair.first_key = first_utf8_key(pair.old_value);
        pair.activation_keys = utf8_keys_in_text(pair.new_value);
        const size_t index = out.pairs.size();
        if (!pair.first_key.empty()) {
            out.by_first_key[pair.first_key].push_back(index);
        }
        out.pairs.push_back(std::move(pair));
    }
    return true;
}

void compiled_corrections_capsule_destructor(PyObject* capsule) {
    void* ptr = PyCapsule_GetPointer(capsule, kCompiledCorrectionsCapsuleName);
    if (ptr == nullptr) {
        PyErr_Clear();
        return;
    }
    delete static_cast<CompiledCorrections*>(ptr);
}

const CompiledCorrections* compiled_corrections_from_capsule(PyObject* capsule) {
    void* ptr = PyCapsule_GetPointer(capsule, kCompiledCorrectionsCapsuleName);
    if (ptr == nullptr) {
        return nullptr;
    }
    return static_cast<const CompiledCorrections*>(ptr);
}

void activate_candidates_for_keys(
    const std::vector<std::string>& keys,
    const CompiledCorrections& compiled,
    std::vector<unsigned char>& active,
    size_t min_index = 0
) {
    for (const auto& key : keys) {
        if (key.empty()) {
            continue;
        }
        const auto found = compiled.by_first_key.find(key);
        if (found == compiled.by_first_key.end()) {
            continue;
        }
        for (const auto idx : found->second) {
            if (idx >= min_index && idx < active.size()) {
                active[idx] = 1;
            }
        }
    }
}

void replace_all_sequential(
    std::string& text,
    const CompiledCorrections& compiled,
    std::vector<size_t>& applied_indices
) {
    std::vector<unsigned char> active(compiled.pairs.size(), 0);
    activate_candidates_for_keys(utf8_keys_in_text(text), compiled, active);
    for (size_t i = 0; i < compiled.pairs.size(); ++i) {
        if (!active[i]) {
            continue;
        }
        const auto& pair = compiled.pairs[i];
        if (pair.old_value.empty()) {
            continue;
        }
        size_t pos = text.find(pair.old_value);
        if (pos == std::string::npos) {
            continue;
        }
        applied_indices.push_back(i);
        activate_candidates_for_keys(pair.activation_keys, compiled, active, i + 1);
        if (pair.old_value == pair.new_value) {
            continue;
        }
        while (pos != std::string::npos) {
            text.replace(pos, pair.old_value.size(), pair.new_value);
            pos = text.find(pair.old_value, pos + pair.new_value.size());
        }
    }
}

PyObject* applied_pairs_to_python(
    const std::vector<size_t>& applied_indices,
    const std::vector<ReplacementPair>& pairs
) {
    PyObject* out = PyList_New(static_cast<Py_ssize_t>(applied_indices.size()));
    if (out == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(applied_indices.size()); ++i) {
        const auto idx = applied_indices[static_cast<size_t>(i)];
        const auto& pair = pairs[idx];
        PyObject* item = Py_BuildValue("(ss)", pair.old_value.c_str(), pair.new_value.c_str());
        if (item == nullptr) {
            Py_DECREF(out);
            return nullptr;
        }
        PyList_SET_ITEM(out, i, item);
    }
    return out;
}

PyObject* py_apply_corrections(PyObject*, PyObject* args) {
    PyObject* text_obj = nullptr;
    PyObject* corrections_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OO", &text_obj, &corrections_obj)) {
        return nullptr;
    }

    std::string text;
    if (!unicode_to_string(text_obj, text)) {
        return nullptr;
    }
    CompiledCorrections compiled;
    if (!correction_pairs_from_obj(corrections_obj, compiled)) {
        return nullptr;
    }

    std::vector<size_t> applied_indices;
    Py_BEGIN_ALLOW_THREADS
    replace_all_sequential(text, compiled, applied_indices);
    Py_END_ALLOW_THREADS

    PyObject* py_text = PyUnicode_FromStringAndSize(text.data(), static_cast<Py_ssize_t>(text.size()));
    PyObject* py_applied = applied_pairs_to_python(applied_indices, compiled.pairs);
    if (py_text == nullptr || py_applied == nullptr) {
        Py_XDECREF(py_text);
        Py_XDECREF(py_applied);
        return nullptr;
    }
    return Py_BuildValue("(NN)", py_text, py_applied);
}

PyObject* py_compile_corrections(PyObject*, PyObject* args) {
    PyObject* corrections_obj = nullptr;
    if (!PyArg_ParseTuple(args, "O", &corrections_obj)) {
        return nullptr;
    }

    auto* compiled = new CompiledCorrections();
    if (!correction_pairs_from_obj(corrections_obj, *compiled)) {
        delete compiled;
        return nullptr;
    }

    PyObject* capsule = PyCapsule_New(
        compiled,
        kCompiledCorrectionsCapsuleName,
        compiled_corrections_capsule_destructor
    );
    if (capsule == nullptr) {
        delete compiled;
        return nullptr;
    }
    return capsule;
}

PyObject* py_apply_corrections_compiled(PyObject*, PyObject* args) {
    PyObject* text_obj = nullptr;
    PyObject* compiled_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OO", &text_obj, &compiled_obj)) {
        return nullptr;
    }

    std::string text;
    if (!unicode_to_string(text_obj, text)) {
        return nullptr;
    }

    const CompiledCorrections* compiled = compiled_corrections_from_capsule(compiled_obj);
    if (compiled == nullptr) {
        return nullptr;
    }

    std::vector<size_t> applied_indices;
    Py_BEGIN_ALLOW_THREADS
    replace_all_sequential(text, *compiled, applied_indices);
    Py_END_ALLOW_THREADS

    PyObject* py_text = PyUnicode_FromStringAndSize(text.data(), static_cast<Py_ssize_t>(text.size()));
    PyObject* py_applied = applied_pairs_to_python(applied_indices, compiled->pairs);
    if (py_text == nullptr || py_applied == nullptr) {
        Py_XDECREF(py_text);
        Py_XDECREF(py_applied);
        return nullptr;
    }
    return Py_BuildValue("(NN)", py_text, py_applied);
}

PyObject* py_apply_corrections_batch(PyObject*, PyObject* args) {
    PyObject* texts_obj = nullptr;
    PyObject* corrections_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OO", &texts_obj, &corrections_obj)) {
        return nullptr;
    }

    PyObject* seq = PySequence_Fast(texts_obj, "texts must be a sequence");
    if (seq == nullptr) {
        return nullptr;
    }

    std::vector<std::string> texts;
    texts.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(seq)));
    PyObject** items = PySequence_Fast_ITEMS(seq);
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(seq); ++i) {
        std::string text;
        if (!unicode_to_string(items[i], text)) {
            Py_DECREF(seq);
            return nullptr;
        }
        texts.push_back(std::move(text));
    }
    Py_DECREF(seq);

    CompiledCorrections compiled;
    if (!correction_pairs_from_obj(corrections_obj, compiled)) {
        return nullptr;
    }

    std::vector<std::vector<size_t>> applied_batches(texts.size());
    Py_BEGIN_ALLOW_THREADS
    for (size_t i = 0; i < texts.size(); ++i) {
        replace_all_sequential(texts[i], compiled, applied_batches[i]);
    }
    Py_END_ALLOW_THREADS

    PyObject* out_texts = PyList_New(static_cast<Py_ssize_t>(texts.size()));
    PyObject* out_applied = PyList_New(static_cast<Py_ssize_t>(applied_batches.size()));
    if (out_texts == nullptr || out_applied == nullptr) {
        Py_XDECREF(out_texts);
        Py_XDECREF(out_applied);
        return nullptr;
    }

    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(texts.size()); ++i) {
        PyObject* py_text = PyUnicode_FromStringAndSize(
            texts[static_cast<size_t>(i)].data(),
            static_cast<Py_ssize_t>(texts[static_cast<size_t>(i)].size())
        );
        PyObject* py_applied = applied_pairs_to_python(applied_batches[static_cast<size_t>(i)], compiled.pairs);
        if (py_text == nullptr || py_applied == nullptr) {
            Py_XDECREF(py_text);
            Py_XDECREF(py_applied);
            Py_DECREF(out_texts);
            Py_DECREF(out_applied);
            return nullptr;
        }
        PyList_SET_ITEM(out_texts, i, py_text);
        PyList_SET_ITEM(out_applied, i, py_applied);
    }

    return Py_BuildValue("(NN)", out_texts, out_applied);
}

PyObject* py_apply_corrections_batch_compiled(PyObject*, PyObject* args) {
    PyObject* texts_obj = nullptr;
    PyObject* compiled_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OO", &texts_obj, &compiled_obj)) {
        return nullptr;
    }

    PyObject* seq = PySequence_Fast(texts_obj, "texts must be a sequence");
    if (seq == nullptr) {
        return nullptr;
    }

    std::vector<std::string> texts;
    texts.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(seq)));
    PyObject** items = PySequence_Fast_ITEMS(seq);
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(seq); ++i) {
        std::string text;
        if (!unicode_to_string(items[i], text)) {
            Py_DECREF(seq);
            return nullptr;
        }
        texts.push_back(std::move(text));
    }
    Py_DECREF(seq);

    const CompiledCorrections* compiled = compiled_corrections_from_capsule(compiled_obj);
    if (compiled == nullptr) {
        return nullptr;
    }

    std::vector<std::vector<size_t>> applied_batches(texts.size());
    Py_BEGIN_ALLOW_THREADS
    for (size_t i = 0; i < texts.size(); ++i) {
        replace_all_sequential(texts[i], *compiled, applied_batches[i]);
    }
    Py_END_ALLOW_THREADS

    PyObject* out_texts = PyList_New(static_cast<Py_ssize_t>(texts.size()));
    PyObject* out_applied = PyList_New(static_cast<Py_ssize_t>(applied_batches.size()));
    if (out_texts == nullptr || out_applied == nullptr) {
        Py_XDECREF(out_texts);
        Py_XDECREF(out_applied);
        return nullptr;
    }

    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(texts.size()); ++i) {
        PyObject* py_text = PyUnicode_FromStringAndSize(
            texts[static_cast<size_t>(i)].data(),
            static_cast<Py_ssize_t>(texts[static_cast<size_t>(i)].size())
        );
        PyObject* py_applied = applied_pairs_to_python(applied_batches[static_cast<size_t>(i)], compiled->pairs);
        if (py_text == nullptr || py_applied == nullptr) {
            Py_XDECREF(py_text);
            Py_XDECREF(py_applied);
            Py_DECREF(out_texts);
            Py_DECREF(out_applied);
            return nullptr;
        }
        PyList_SET_ITEM(out_texts, i, py_text);
        PyList_SET_ITEM(out_applied, i, py_applied);
    }

    return Py_BuildValue("(NN)", out_texts, out_applied);
}

PyMethodDef kMethods[] = {
    {
        "compile_corrections",
        py_compile_corrections,
        METH_VARARGS,
        "Compile a correction dictionary into a reusable native correction database.",
    },
    {
        "apply_corrections",
        py_apply_corrections,
        METH_VARARGS,
        "Apply correction dictionary replacements to one subtitle string.",
    },
    {
        "apply_corrections_compiled",
        py_apply_corrections_compiled,
        METH_VARARGS,
        "Apply a compiled correction database to one subtitle string.",
    },
    {
        "apply_corrections_batch",
        py_apply_corrections_batch,
        METH_VARARGS,
        "Apply correction dictionary replacements to multiple subtitle strings in one native batch.",
    },
    {
        "apply_corrections_batch_compiled",
        py_apply_corrections_batch_compiled,
        METH_VARARGS,
        "Apply a compiled correction database to multiple subtitle strings in one native batch.",
    },
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef kModule = {
    PyModuleDef_HEAD_INIT,
    "_native_text_cleanup",
    "Native subtitle correction-dictionary helpers.",
    -1,
    kMethods,
};

}  // namespace

PyMODINIT_FUNC PyInit__native_text_cleanup(void) {
    return PyModule_Create(&kModule);
}
