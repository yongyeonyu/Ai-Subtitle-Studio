from __future__ import annotations

from core.runtime.logger import get_logger


class EditorPipelineSafetyMixin:
    def _pipeline_log_nonfatal(self, label: str, exc: Exception) -> None:
        try:
            get_logger().log(f"⚠️ 에디터 파이프라인 {label} 실패: {exc}")
        except Exception:
            pass

    def _pipeline_window(self):
        try:
            return self.window()
        except RuntimeError:
            return None
        except Exception as exc:
            self._pipeline_log_nonfatal("window 조회", exc)
            return None

    def _pipeline_best_effort(self, action, *, label: str, default=None, log: bool = True):
        try:
            return action()
        except RuntimeError as exc:
            if log:
                self._pipeline_log_nonfatal(label, exc)
            return default
        except Exception as exc:
            if log:
                self._pipeline_log_nonfatal(label, exc)
            return default

    def _pipeline_call_if_callable(self, target, attr: str, *args, label: str | None = None, default=None, log: bool = True, **kwargs):
        fn = getattr(target, attr, None) if target is not None else None
        if not callable(fn):
            return default
        return self._pipeline_best_effort(
            lambda: fn(*args, **kwargs),
            label=label or attr,
            default=default,
            log=log,
        )

    def _pipeline_stop_timer(self, timer, *, label: str, log: bool = False) -> bool:
        if timer is None or not hasattr(timer, "stop"):
            return False

        def _stop():
            timer.stop()
            return True

        return bool(self._pipeline_best_effort(_stop, label=label, default=False, log=log))

    def _pipeline_clear_attr(self, attr: str, *, label: str, log: bool = False) -> bool:
        if not hasattr(self, attr):
            return False
        target = getattr(self, attr, None)
        if not hasattr(target, "clear"):
            return False

        def _clear():
            target.clear()
            return True

        return bool(self._pipeline_best_effort(_clear, label=label, default=False, log=log))

    def _pipeline_set_attr(self, attr: str, value, *, label: str, log: bool = False) -> bool:
        if not hasattr(self, attr):
            return False

        def _assign():
            setattr(self, attr, value)
            return True

        return bool(self._pipeline_best_effort(_assign, label=label, default=False, log=log))
