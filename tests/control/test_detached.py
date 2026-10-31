"""Real processes and sockets, with only the native-agent boundary replaced."""

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from shipyard.application.context import ExecutionContext
from shipyard.control.client import ControlClient
from shipyard.control.queue import QueueStore
from shipyard.domain import RunContract
from tests.application.test_run_execution import capture


def eventually[T](read: Callable[[], T], done: Callable[[T], bool]) -> T:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            value = read()
            if done(value):
                return value
        except ValueError:
            pass
        time.sleep(0.05)
    raise AssertionError("Background service did not reach expected state")


def launch(root: Path) -> subprocess.Popen[bytes]:
    script = """
import sys, time
from pathlib import Path
from shipyard.control.queue import QueueStore
from shipyard.control.service import ControlService
from tests.application.test_run_execution import FakeAgent
root = Path(sys.argv[1])
class Agent(FakeAgent):
    def execute(self, request):
        (root / 'entered').touch()
        while not (root / 'release').exists():
            time.sleep(0.02)
        return super().execute(request)
ControlService(QueueStore(root), agent=Agent(), history_root=root / "runs").serve()
"""
    return subprocess.Popen(
        [sys.executable, "-c", script, str(root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def test_client_exit_does_not_stop_canonical_execution(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    ExecutionContext(
        version=1,
        run_id=contract.run_id,
        repository=repo.checkout_root(),
        runs_root=store.directory(contract.run_id).parent,
    ).save()
    with TemporaryDirectory(prefix="sy-", dir="/tmp") as directory:
        root = Path(directory)
        client = ControlClient(root)
        process = launch(root)
        try:
            eventually(
                lambda: client.request("GET", "/health"),
                lambda value: value["version"] == 1,
            )
            submitted = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "shipyard",
                    "run",
                    str(contract.run_id),
                    "--runs-dir",
                    str(store.directory(contract.run_id).parent),
                    "--control-dir",
                    str(root),
                    "--json",
                ],
                capture_output=True,
                check=False,
                timeout=10,
            )
            assert submitted.returncode == 0, submitted.stderr.decode()
            eventually(lambda: (root / "entered").exists(), bool)
            assert process.poll() is None
            assert (
                client.request("GET", f"/runs/{contract.run_id}")["state"] == "RUNNING"
            )
            duplicate = client.request(
                "POST",
                "/runs",
                QueueStore(root)
                .get(contract.run_id)
                .submission.model_dump(mode="json"),
            )
            assert duplicate["state"] == "RUNNING"
            (root / "release").touch()
            completed = eventually(
                lambda: client.request("GET", f"/runs/{contract.run_id}"),
                lambda value: value["state"] == "FINISHED",
            )
            assert completed["package_available"]
            run = store.load_state(contract.run_id)
            assert run.outcome == "VERIFIED"
            assert run.verification is not None
            assert (
                run.verification.candidate.candidate_sha
                in (store.directory(contract.run_id) / "evidence.json").read_text()
            )
            client.request("POST", "/stop")
            assert process.wait(10) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(5)
            if process.stderr:
                process.stderr.close()


def test_killed_service_marks_active_claim_interrupted_on_restart(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    from shipyard.control.queue import Submission

    with TemporaryDirectory(prefix="sy-", dir="/tmp") as directory:
        root = Path(directory)
        queue = QueueStore(root)
        queue.submit(
            Submission(
                run_id=contract.run_id,
                repository=repo.checkout_root(),
                runs_root=store.directory(contract.run_id).parent,
            )
        )
        client = ControlClient(root)
        process = launch(root)
        try:
            eventually(lambda: (root / "entered").exists(), bool)
            process.kill()
            process.wait(5)
            assert store.load_state(contract.run_id).lifecycle == "RUNNING"
            (root / "entered").unlink()
            (root / "release").touch()
            if process.stderr:
                process.stderr.close()
            process = launch(root)
            eventually(
                lambda: client.request("GET", "/health"),
                lambda value: value["version"] == 1,
            )
            assert (
                client.request("GET", f"/runs/{contract.run_id}")["state"]
                == "INTERRUPTED"
            )
            assert not (root / "entered").exists()
            assert not (store.directory(contract.run_id) / "evidence.json").exists()
            client.request("POST", "/stop")
            assert process.wait(10) == 0
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(5)
            if process.stderr:
                process.stderr.close()


def test_service_start_detaches_and_stop_shuts_down() -> None:
    with TemporaryDirectory(prefix="sy-", dir="/tmp") as directory:
        root = Path(directory)
        arguments = [sys.executable, "-m", "shipyard", "service"]
        client = ControlClient(root)
        try:
            for _ in range(2):
                started = subprocess.run(
                    [*arguments, "start", "--control-dir", str(root)],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                assert started.returncode == 0, started.stderr.decode()
            assert client.request("GET", "/health")["stopping"] is False
            stopped = subprocess.run(
                [*arguments, "stop", "--control-dir", str(root)],
                capture_output=True,
                timeout=10,
                check=False,
            )
            assert stopped.returncode == 0, stopped.stderr.decode()
            eventually(lambda: not (root / "service.sock").exists(), bool)
        finally:
            try:
                client.request("POST", "/stop")
            except ValueError:
                pass
            eventually(lambda: not (root / "service.sock").exists(), bool)
