"""Machine-learning based anomaly detection for process behavior.

Collects process feature vectors over a training window, fits an IsolationForest
model, and then detects anomalous processes in subsequent polling cycles.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from agent.alert import AlertType, AlertSeverity

if TYPE_CHECKING:
    from agent.config import MLAnomalyConfig
    from agent.alert import AlertStore

logger = logging.getLogger(__name__)

# Optional dependencies – graceful degradation
try:
    import numpy as np

    _NUMPY_AVAILABLE = True
except ImportError:
    logger.warning("numpy not installed – MLAnomalyDetector disabled")
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

try:
    from sklearn.ensemble import IsolationForest

    _SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning("scikit-learn not installed – MLAnomalyDetector disabled")
    IsolationForest = None  # type: ignore
    _SKLEARN_AVAILABLE = False

try:
    import joblib

    _JOBLIB_AVAILABLE = True
except ImportError:
    logger.warning("joblib not installed – MLAnomalyDetector cannot persist models")
    joblib = None  # type: ignore
    _JOBLIB_AVAILABLE = False


class MLAnomalyDetector:
    """Collects process behavior baselines and detects anomalous processes."""

    _FEATURE_NAMES = [
        "cpu_percent",
        "memory_percent",
        "num_threads",
        "has_network_connections",
        "parent_is_system",
    ]
    _FEATURE_DIM = len(_FEATURE_NAMES)

    def __init__(
        self,
        config: MLAnomalyConfig,
        alert_store: AlertStore,
        callback: Optional[callable] = None,
    ) -> None:
        self._config = config
        self._alert_store = alert_store
        self._callback = callback
        self._running = False
        self._model: IsolationForest | None = None
        self._training_buffer: list = []
        self._trained = False
        self._training_start: float | None = None
        self._last_retrain: float | None = None
        self._process_monitor = None

    @property
    def enabled(self) -> bool:
        if not _NUMPY_AVAILABLE or not _SKLEARN_AVAILABLE:
            return False
        return self._config.enabled

    def set_callback(self, cb: callable) -> None:
        self._callback = cb

    def set_process_monitor(self, monitor) -> None:
        self._process_monitor = monitor

    def collect_features(self, processes: list[dict]) -> np.ndarray:
        feature_rows: list[list[float]] = []

        for proc in processes:
            try:
                cpu = float(proc.get("cpu_percent", 0.0) or 0.0)
                mem = float(proc.get("memory_percent", 0.0) or 0.0)
                threads = int(proc.get("num_threads", 0) or 0)
                has_net = 1.0 if proc.get("has_network_connections") else 0.0

                parent_is_system = 0.0
                parent_pid = proc.get("ppid")
                if parent_pid is not None and int(parent_pid) in (0, 4):
                    parent_is_system = 1.0

                row = [cpu, mem, float(threads), has_net, parent_is_system]
                feature_rows.append(row)
            except (ValueError, TypeError, OSError):
                continue

        if not feature_rows:
            return np.zeros((0, self._FEATURE_DIM), dtype=np.float64)

        arr = np.array(feature_rows, dtype=np.float64)

        # Cap extreme values to prevent model skew
        arr[:, 0] = np.clip(arr[:, 0], 0.0, 100.0)
        arr[:, 1] = np.clip(arr[:, 1], 0.0, 100.0)
        arr[:, 2] = np.clip(arr[:, 2], 0.0, 10000.0)

        return arr

    def _train_model(self, features: np.ndarray) -> None:
        if features.shape[0] < 10:
            logger.debug("Too few samples (%d) to train – skipping", features.shape[0])
            return

        contamination = self._config.contamination
        if not (0.0 < contamination < 0.5):
            contamination = 0.01

        model = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            random_state=42,
            n_jobs=1,
        )
        model.fit(features)
        self._model = model
        self._trained = True

        if _JOBLIB_AVAILABLE and self._config.model_path:
            model_file = Path(self._config.model_path)
            model_file.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, model_file)
            logger.info("Model saved to %s", model_file)

    def _load_or_train(self) -> bool:
        model_file = Path(self._config.model_path) if self._config.model_path else None
        if model_file and model_file.is_file():
            try:
                self._model = joblib.load(model_file)
                self._trained = True
                logger.info("Loaded model from %s", model_file)
                return True
            except Exception:
                logger.exception("Failed to load model from %s – will retrain", model_file)
                try:
                    model_file.unlink()
                except Exception:
                    pass
        return False

    def _predict(self, features: np.ndarray, processes: list[dict]) -> list[tuple]:
        if self._model is None or features.shape[0] == 0:
            return []

        try:
            scores = self._model.score_samples(features)
            preds = self._model.predict(features)
        except Exception:
            logger.exception("Prediction error")
            return []

        results: list[tuple] = []
        for i, proc in enumerate(processes):
            if i >= len(scores):
                break
            is_anomaly = bool(preds[i] == -1)
            if is_anomaly:
                results.append((proc, float(scores[i]), True))

        return results

    async def start(self) -> None:
        if not self.enabled:
            logger.info("MLAnomalyDetector disabled – skipping run")
            return

        self._running = True
        self._training_start = asyncio.get_event_loop().time()
        training_seconds = self._config.training_hours * 3600
        poll_interval = 15

        loaded = self._load_or_train()
        if loaded:
            logger.info("MLAnomalyDetector running in inference mode")
        else:
            logger.info(
                "MLAnomalyDetector running in training mode (%dh window)",
                self._config.training_hours,
            )

        retrain_interval = self._config.retrain_interval_hours * 3600
        self._last_retrain = asyncio.get_event_loop().time() if loaded else None

        while self._running:
            try:
                await self._cycle(
                    training_seconds=training_seconds,
                    retrain_interval=retrain_interval,
                )
            except Exception:
                logger.exception("MLAnomalyDetector cycle error")
            await asyncio.sleep(poll_interval)

    async def stop(self) -> None:
        self._running = False

    async def _cycle(self, *, training_seconds: float, retrain_interval: float) -> None:
        if self._process_monitor is None:
            return

        snapshot = self._process_monitor.latest_snapshot

        snapshot_sorted = sorted(
            snapshot,
            key=lambda p: float(p.get("memory_percent", 0) or 0),
            reverse=True,
        )[:50]

        features = self.collect_features(snapshot_sorted)
        if features.shape[0] < 2:
            return

        now = asyncio.get_event_loop().time()

        if not self._trained:
            self._training_buffer.extend(features.tolist())
            elapsed = now - (self._training_start or now)
            if elapsed >= training_seconds and len(self._training_buffer) >= 10:
                all_features = np.array(self._training_buffer, dtype=np.float64)
                logger.info(
                    "Training model on %d samples (%.1fh elapsed)",
                    all_features.shape[0],
                    elapsed / 3600,
                )
                self._train_model(all_features)
                self._training_buffer.clear()
                self._last_retrain = now
        else:
            results = self._predict(features, snapshot_sorted)
            for proc, score, _is_anomaly in results:
                alert_details = {
                    "pid": proc.get("pid"),
                    "name": proc.get("name"),
                    "anomaly_score": round(score, 4),
                    "cpu_percent": proc.get("cpu_percent"),
                    "memory_percent": proc.get("memory_percent"),
                }
                self._alert_store.warn(
                    AlertType.SYSTEM,
                    f"ML anomaly detected: {proc.get('name', 'unknown')} "
                    f"(score={score:.4f}, pid={proc.get('pid')})",
                    group_key=f"ml:{proc.get('name', 'unknown')}",
                    **alert_details,
                )
                if self._callback:
                    try:
                        self._callback(alert_details)
                    except Exception:
                        logger.exception("ML callback error")

            if self._last_retrain and (now - self._last_retrain) >= retrain_interval:
                logger.info("Retraining model (interval=%dh)", self._config.retrain_interval_hours)
                self._train_model(features)
                self._last_retrain = now
