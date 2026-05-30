"""Tests for agent.detectors.ml_anomaly — MLAnomalyDetector.

All tests mock numpy, sklearn, joblib at module level. No real dependencies.
"""

import asyncio, sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.alert import AlertSeverity, AlertStore, AlertType
from agent.config import MLAnomalyConfig


# ---------------------------------------------------------------------------
# Reusable mock factories & helpers
# ---------------------------------------------------------------------------

def _arr(rows, cols=5, tolist_data=None):
    arr = MagicMock()
    arr.shape = (rows, cols)
    arr.tolist.return_value = tolist_data or [[0.0] * cols for _ in range(rows)]
    return arr

def _np(preserve_data=False):
    m = MagicMock();  m.float64 = "float64"
    if preserve_data:
        m.array.side_effect = lambda d, dtype=None: _arr(len(d), tolist_data=d)
    else:
        m.array.side_effect = lambda d, dtype=None: _arr(len(d))
    m.zeros.side_effect = lambda sh, dtype=None: _arr(sh[0], sh[1])
    m.clip.side_effect = lambda a, lo, hi: a
    return m

def _if():
    IF = MagicMock();  inst = MagicMock()
    inst.score_samples.return_value = [-0.1, -0.2, -0.3, -0.05, -0.15]
    inst.predict.return_value = [1, -1, 1, 1, -1]
    IF.return_value = inst
    return IF, inst

class SleepStopper:
    def __init__(self, det, limit=2):
        self._d = det; self._c = 0; self._lim = limit
    async def __call__(self, s):
        self._c += 1
        if self._c >= self._lim: self._d._running = False


def _patches(**_kw):
    """patch.multiple with defaults; _kw overrides."""
    defaults = dict(_NUMPY_AVAILABLE=True, _SKLEARN_AVAILABLE=True)
    defaults.update(_kw)
    return patch.multiple("agent.detectors.ml_anomaly", create=True, **defaults)


# ---------------------------------------------------------------------------
# enabled
# ---------------------------------------------------------------------------

class TestMLAnomalyEnabled:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True)
        self.store = AlertStore()

    def test_all_available(self):
        with _patches():
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            assert MLAnomalyDetector(self.cfg, self.store).enabled is True

    def test_numpy_missing(self):
        with _patches(_NUMPY_AVAILABLE=False):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            assert MLAnomalyDetector(self.cfg, self.store).enabled is False

    def test_sklearn_missing(self):
        with _patches(_SKLEARN_AVAILABLE=False):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            assert MLAnomalyDetector(self.cfg, self.store).enabled is False

    def test_config_disabled(self):
        with _patches():
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            cfg = MLAnomalyConfig(enabled=False)
            assert MLAnomalyDetector(cfg, self.store).enabled is False

    def test_both_deps_missing(self):
        with _patches(_NUMPY_AVAILABLE=False, _SKLEARN_AVAILABLE=False):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            assert MLAnomalyDetector(self.cfg, self.store).enabled is False


# ---------------------------------------------------------------------------
# collect_features
# ---------------------------------------------------------------------------

class TestMLAnomalyCollectFeatures:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True)
        self.store = AlertStore()

    def test_correct_shape(self):
        procs = [{"cpu_percent": 12, "memory_percent": 3.5, "num_threads": 8,
                   "has_network_connections": True, "ppid": 0},
                  {"cpu_percent": 45, "memory_percent": 20.1, "num_threads": 24,
                   "has_network_connections": False, "ppid": 100}]
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            feats = MLAnomalyDetector(self.cfg, self.store).collect_features(procs)
            assert feats.shape == (2, 5)

    def test_empty_list(self):
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            f = MLAnomalyDetector(self.cfg, self.store).collect_features([])
            assert f.shape[0] == 0 and f.shape[1] == 5

    def test_missing_keys_defaulted(self):
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            f = MLAnomalyDetector(self.cfg, self.store).collect_features([{"cpu_percent": 10}])
            assert f.shape[0] == 1

    def test_invalid_values_skipped(self):
        procs = [{"cpu_percent": "bad", "memory_percent": 0, "num_threads": 0,
                   "has_network_connections": False, "ppid": 0},
                  {"cpu_percent": 15, "memory_percent": 5, "num_threads": 10,
                   "has_network_connections": True, "ppid": None}]
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            assert MLAnomalyDetector(self.cfg, self.store).collect_features(procs).shape[0] == 1

    def test_parent_is_system(self):
        procs = [dict(cpu_percent=10, memory_percent=5, num_threads=4,
                      has_network_connections=False, ppid=p)
                 for p in ("0", "4", 500)]
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            assert MLAnomalyDetector(self.cfg, self.store).collect_features(procs).shape == (3, 5)

    def test_extreme_values_capped(self):
        procs = [{"cpu_percent": 9999, "memory_percent": -50, "num_threads": 99999,
                   "has_network_connections": True, "ppid": 0}]
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            assert MLAnomalyDetector(self.cfg, self.store).collect_features(procs).shape == (1, 5)


# ---------------------------------------------------------------------------
# _train_model
# ---------------------------------------------------------------------------

class TestMLAnomalyTrainModel:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True, model_path="models/t.joblib", contamination=0.02)
        self.store = AlertStore()

    def test_sufficient(self):
        if_mock, if_inst = _if();  jb = MagicMock()
        with _patches(_JOBLIB_AVAILABLE=True, np=_np(), IsolationForest=if_mock, joblib=jb):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._train_model(_arr(50))
            if_mock.assert_called_once();  if_inst.fit.assert_called_once()
            assert d._trained and d._model is if_inst

    def test_too_few(self):
        if_mock, if_inst = _if();  jb = MagicMock()
        with _patches(_JOBLIB_AVAILABLE=True, np=_np(), IsolationForest=if_mock, joblib=jb):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._train_model(_arr(5))
            if_inst.fit.assert_not_called()
            assert d._trained is False

    def test_saves_joblib(self):
        if_mock, if_inst = _if();  jb = MagicMock()
        with _patches(_JOBLIB_AVAILABLE=True, np=_np(), IsolationForest=if_mock, joblib=jb):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._train_model(_arr(20))
            jb.dump.assert_called_once_with(if_inst, Path("models/t.joblib"))

    def test_no_joblib_skips_save(self):
        if_mock, if_inst = _if()
        with _patches(_JOBLIB_AVAILABLE=False, np=_np(), IsolationForest=if_mock, joblib=MagicMock()):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._train_model(_arr(20))
            if_inst.fit.assert_called_once()


# ---------------------------------------------------------------------------
# _load_or_train
# ---------------------------------------------------------------------------

class TestMLAnomalyLoadOrTrain:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True, model_path="models/e.joblib")
        self.store = AlertStore()

    def test_loads(self):
        jb = MagicMock();  model = MagicMock();  jb.load.return_value = model
        with _patches(_JOBLIB_AVAILABLE=True, np=_np(), IsolationForest=_if()[0], joblib=jb), \
             patch.object(Path, "is_file", return_value=True):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            assert d._load_or_train() is True
            assert d._trained and d._model is model

    def test_no_file(self):
        with _patches(np=_np(), IsolationForest=_if()[0]), \
             patch.object(Path, "is_file", return_value=False):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            assert d._load_or_train() is False

    def test_error(self):
        jb = MagicMock();  jb.load.side_effect = RuntimeError("corrupt")
        with _patches(_JOBLIB_AVAILABLE=True, np=_np(), IsolationForest=_if()[0], joblib=jb), \
             patch.object(Path, "is_file", return_value=True), \
             patch.object(Path, "unlink") as mu:
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            assert d._load_or_train() is False;  mu.assert_called_once()


# ---------------------------------------------------------------------------
# _predict
# ---------------------------------------------------------------------------

class TestMLAnomalyPredict:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True)
        self.store = AlertStore()

    def test_anomalies(self):
        if_mock, if_inst = _if()
        with _patches(np=_np(), IsolationForest=if_mock):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._model = if_inst; d._trained = True
            procs = [{"pid": i, "name": f"p{i}"} for i in range(5)]
            r = d._predict(_arr(5), procs)
            assert len(r) == 2 and r[0][2] is True

    def test_no_model(self):
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store); d._model = None
            assert d._predict(_arr(5), [{"pid": 1}]) == []

    def test_empty_features(self):
        if_mock, if_inst = _if()
        with _patches(np=_np(), IsolationForest=if_mock):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._model = if_inst; d._trained = True
            assert d._predict(_arr(0), []) == []

    def test_error(self):
        if_mock, if_inst = _if()
        with _patches(np=_np(), IsolationForest=if_mock):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._model = if_inst; d._trained = True
            if_inst.score_samples.side_effect = RuntimeError("crash")
            assert d._predict(_arr(1), [{"pid": 1}]) == []


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------

class TestMLAnomalyLifecycle:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True, training_hours=0)
        self.store = AlertStore()

    def test_start_disabled(self):
        with _patches():
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            cfg = MLAnomalyConfig(enabled=False)
            d = MLAnomalyDetector(cfg, self.store)
            asyncio.run(d.start())
            assert d._running is False and d._trained is False

    def test_stop(self):
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._running = True; asyncio.run(d.stop())
            assert d._running is False

    def test_loads_model_and_loops(self):
        if_mock, if_inst = _if();  jb = MagicMock();  jb.load.return_value = if_inst
        with _patches(_JOBLIB_AVAILABLE=True, np=_np(), IsolationForest=if_mock, joblib=jb), \
             patch.object(Path, "is_file", return_value=True):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            pm = MagicMock()
            pm.latest_snapshot = [
                {"pid": 1, "name": "a", "cpu_percent": 10, "memory_percent": 5,
                 "num_threads": 2, "has_network_connections": False, "ppid": 100},
                {"pid": 2, "name": "b", "cpu_percent": 20, "memory_percent": 10,
                 "num_threads": 4, "has_network_connections": True, "ppid": 0}]
            d.set_process_monitor(pm)
            with patch("asyncio.sleep", SleepStopper(d)):
                asyncio.run(d.start())
            assert d._trained and d._model is if_inst

    def test_trains_model(self):
        if_mock, if_inst = _if();  jb = MagicMock()
        with _patches(_JOBLIB_AVAILABLE=True, np=_np(preserve_data=True),
                      IsolationForest=if_mock, joblib=jb), \
             patch.object(Path, "is_file", return_value=False):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            pm = MagicMock()
            pm.latest_snapshot = [
                {"pid": i, "name": f"p{i}", "cpu_percent": 10 + i,
                 "memory_percent": 5 + i, "num_threads": 2,
                 "has_network_connections": False, "ppid": 100}
                for i in range(12)]
            d.set_process_monitor(pm)
            with patch("asyncio.sleep", SleepStopper(d)):
                asyncio.run(d.start())
            assert d._trained;  if_inst.fit.assert_called_once()


# ---------------------------------------------------------------------------
# _cycle
# ---------------------------------------------------------------------------

class TestMLAnomalyCycle:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True, training_hours=0)
        self.store = AlertStore()

    def test_no_monitor(self):
        with _patches(np=_np(), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            asyncio.run(d._cycle(training_seconds=3600, retrain_interval=14400))
            assert len(self.store.get_all()) == 0

    def test_training_buffer(self):
        with _patches(np=_np(preserve_data=True), IsolationForest=_if()[0]):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._trained = False; d._training_start = 0.0  # far past → huge elapsed
            pm = MagicMock()
            pm.latest_snapshot = [
                {"pid": i, "name": f"p{i}", "cpu_percent": 10, "memory_percent": 5,
                 "num_threads": 2, "has_network_connections": False, "ppid": 100}
                for i in range(3)]
            d.set_process_monitor(pm)
            asyncio.run(d._cycle(training_seconds=3600, retrain_interval=14400))
            assert len(d._training_buffer) > 0

    def test_fires_alerts(self):
        if_mock, if_inst = _if()
        # sort-by-mem: bad1(80)→idx0, bad2(75)→idx1
        if_inst.score_samples.return_value = [-0.2, -0.3, -0.1, -0.05, -0.15]
        if_inst.predict.return_value        = [-1,   -1,    1,    1,     1]
        with _patches(np=_np(preserve_data=True), IsolationForest=if_mock):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._model = if_inst; d._trained = True
            pm = MagicMock()
            pm.latest_snapshot = [
                {"pid": 1, "name": "ok1", "cpu_percent": 10, "memory_percent": 5,
                 "num_threads": 2, "has_network_connections": False, "ppid": 100},
                {"pid": 2, "name": "bad1", "cpu_percent": 99, "memory_percent": 80,
                 "num_threads": 500, "has_network_connections": True, "ppid": 0},
                {"pid": 3, "name": "ok2", "cpu_percent": 15, "memory_percent": 8,
                 "num_threads": 4, "has_network_connections": False, "ppid": 100},
                {"pid": 4, "name": "ok3", "cpu_percent": 12, "memory_percent": 6,
                 "num_threads": 3, "has_network_connections": False, "ppid": 4},
                {"pid": 5, "name": "bad2", "cpu_percent": 95, "memory_percent": 75,
                 "num_threads": 600, "has_network_connections": True, "ppid": 0}]
            d.set_process_monitor(pm)
            asyncio.run(d._cycle(training_seconds=3600, retrain_interval=14400))
            assert len(self.store.get_all()) == 2

    def test_alert_format(self):
        if_mock, if_inst = _if()
        if_inst.score_samples.return_value = [-0.5, -0.1]
        if_inst.predict.return_value        = [-1,    1]
        with _patches(np=_np(preserve_data=True), IsolationForest=if_mock):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            d._model = if_inst; d._trained = True
            pm = MagicMock()
            pm.latest_snapshot = [
                {"pid": 42, "name": "suspicious", "cpu_percent": 100, "memory_percent": 90,
                 "num_threads": 1000, "has_network_connections": True, "ppid": 0},
                {"pid": 1, "name": "normal", "cpu_percent": 10, "memory_percent": 5,
                 "num_threads": 2, "has_network_connections": False, "ppid": 100}]
            d.set_process_monitor(pm)
            asyncio.run(d._cycle(training_seconds=3600, retrain_interval=14400))
            a = self.store.get_all()[0]
            assert a.alert_type == AlertType.SYSTEM and a.severity == AlertSeverity.WARN
            assert a.group_key == "ml:suspicious" and "suspicious" in a.message
            assert a.details["pid"] == 42 and a.details["name"] == "suspicious"
            assert "anomaly_score" in a.details

    def test_callback(self):
        if_mock, if_inst = _if()
        if_inst.score_samples.return_value = [-0.7, -0.1]
        if_inst.predict.return_value        = [-1,    1]
        calls = []
        with _patches(np=_np(preserve_data=True), IsolationForest=if_mock):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store, callback=calls.append)
            d._model = if_inst; d._trained = True
            pm = MagicMock()
            pm.latest_snapshot = [
                {"pid": 99, "name": "cb", "cpu_percent": 100, "memory_percent": 100,
                 "num_threads": 100, "has_network_connections": True, "ppid": 0},
                {"pid": 1, "name": "ok", "cpu_percent": 10, "memory_percent": 5,
                 "num_threads": 2, "has_network_connections": False, "ppid": 100}]
            d.set_process_monitor(pm)
            asyncio.run(d._cycle(training_seconds=3600, retrain_interval=14400))
            assert len(calls) == 1 and calls[0]["pid"] == 99

    def test_callback_error(self):
        if_mock, if_inst = _if()
        if_inst.score_samples.return_value = [-0.7, -0.1]
        if_inst.predict.return_value        = [-1,    1]
        with _patches(np=_np(preserve_data=True), IsolationForest=if_mock):
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store, callback=lambda _: 1 / 0)
            d._model = if_inst; d._trained = True
            pm = MagicMock()
            pm.latest_snapshot = [
                {"pid": 1, "name": "x", "cpu_percent": 50, "memory_percent": 50,
                 "num_threads": 5, "has_network_connections": False, "ppid": 0},
                {"pid": 2, "name": "y", "cpu_percent": 10, "memory_percent": 5,
                 "num_threads": 2, "has_network_connections": False, "ppid": 100}]
            d.set_process_monitor(pm)
            asyncio.run(d._cycle(training_seconds=3600, retrain_interval=14400))


# ---------------------------------------------------------------------------
# set_callback / set_process_monitor
# ---------------------------------------------------------------------------

class TestMLAnomalyWiring:
    def setup_method(self):
        self.cfg = MLAnomalyConfig(enabled=True)
        self.store = AlertStore()

    def test_set_callback(self):
        with _patches():
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            cb = lambda _: None; d.set_callback(cb)
            assert d._callback is cb

    def test_set_process_monitor(self):
        with _patches():
            from agent.detectors.ml_anomaly import MLAnomalyDetector
            d = MLAnomalyDetector(self.cfg, self.store)
            pm = MagicMock(); d.set_process_monitor(pm)
            assert d._process_monitor is pm
