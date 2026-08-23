from pathlib import Path

from app.services import vidat_server as service


def test_status_reports_stopped_when_no_state_or_url(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setattr(service, "_is_ready", lambda _url: False)
    status = service.get_vidat_service_status()
    assert status["status"] == "stopped"
    assert status["controlled"] is False


def test_stop_does_not_kill_uncontrolled_port(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_state_path", lambda: tmp_path / "state.json")
    monkeypatch.setattr(service, "_is_ready", lambda _url: True)
    called = False

    def fail_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("uncontrolled service must not be stopped")

    monkeypatch.setattr(service.subprocess, "run", fail_run)
    result = service.stop_vidat_service()
    assert result["status"] == "uncontrolled"
    assert called is False


def test_stop_controlled_service_waits_until_unavailable(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"service":"pickleball-vidat","pid":123,"config_path":"/tmp/nginx.conf","url":"http://localhost:8888"}',
        encoding="utf-8",
    )
    nginx = tmp_path / "nginx"
    nginx.write_text("", encoding="utf-8")
    monkeypatch.setattr(service, "_state_path", lambda: state_path)
    monkeypatch.setattr(service, "_controlled_state", lambda *_args: True)
    ready = iter([True, False])
    monkeypatch.setattr(service, "_is_ready", lambda _url: next(ready))
    monkeypatch.setattr(service.os, "getenv", lambda key, default=None: str(nginx) if key == "PICKLEBALL_VIDAT_NGINX_BIN" else default)
    monkeypatch.setattr(service.subprocess, "run", lambda *_args, **_kwargs: type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})())
    result = service.stop_vidat_service()
    assert result["status"] == "stopped"
    assert result["stopped"] is True
    assert not state_path.exists()


def test_status_marks_dead_recorded_pid_as_unknown(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"service":"pickleball-vidat","pid":123,"config_path":"/tmp/nginx.conf"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "_state_path", lambda: state_path)
    monkeypatch.setattr(service, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(service, "_is_ready", lambda _url: False)
    assert service.get_vidat_service_status()["status"] == "unknown"


def test_pid_reuse_is_not_treated_as_controlled(monkeypatch, tmp_path):
    state = {"service": "pickleball-vidat", "pid": 123, "config_path": "/tmp/nginx.conf"}
    monkeypatch.setattr(service, "_pid_alive", lambda _pid: True)
    monkeypatch.setattr(service.subprocess, "check_output", lambda *_args, **_kwargs: "python worker")
    assert service._controlled_state(state) is False


def test_ensure_does_not_start_second_server_or_take_uncontrolled_port(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_vidat_service_status",
        lambda: {"status": "running", "running": True, "controlled": True},
    )
    monkeypatch.setattr(service.subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    assert service.ensure_vidat_service()["started"] is False

    monkeypatch.setattr(
        service,
        "get_vidat_service_status",
        lambda: {"status": "uncontrolled", "running": True, "controlled": False},
    )
    assert service.ensure_vidat_service()["started"] is False
