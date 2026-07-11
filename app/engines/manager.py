"""引擎生命週期：同時只載一顆；切換＝卸舊載新。載入在呼叫端執行緒進行。"""
import threading
from typing import Callable

from app.engines.base import Engine
from app.logger import get_logger

log = get_logger("engines")


class EngineManager:
    def __init__(self, factories: dict[str, Callable[[], Engine]]):
        self._factories = factories
        self._lock = threading.Lock()
        self.current: Engine | None = None
        self.state = "idle"  # idle | loading | ready | error

    def switch(self, name: str) -> None:
        with self._lock:
            if self.current and self.current.name == name and self.state == "ready":
                return
            if self.current:
                log.info("unloading %s", self.current.name)
                self.current.unload()
                self.current = None
            self.state = "loading"
            try:
                eng = self._factories[name]()
                eng.load()
                self.current = eng
                self.state = "ready"
            except Exception:
                self.state = "error"
                raise
