from __future__ import annotations

from pathlib import Path

from setuptools import Extension, setup


ROOT = Path(__file__).resolve().parents[1]


setup(
    name="ai-subtitle-studio-native",
    version="0.0.0",
    ext_modules=[
        Extension(
            "core._native_cut_boundary",
            sources=[str(ROOT / "core" / "native" / "_native_cut_boundary.cpp")],
            language="c++",
            extra_compile_args=["-std=c++17", "-O3"],
        ),
        Extension(
            "core._native_stt_lattice",
            sources=[str(ROOT / "core" / "native" / "_native_stt_lattice.cpp")],
            language="c++",
            extra_compile_args=["-std=c++17", "-O3"],
        ),
        Extension(
            "core._native_stt_recheck",
            sources=[str(ROOT / "core" / "native" / "_native_stt_recheck.cpp")],
            language="c++",
            extra_compile_args=["-std=c++17", "-O3"],
        ),
    ],
)
