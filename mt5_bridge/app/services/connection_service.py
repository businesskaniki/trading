from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from contextlib import suppress
from pathlib import Path
from threading import RLock
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.broker.mt5_client import MT5Client
from app.core.config import settings

logger = logging.getLogger("mt5_bridge.connection_service")


class ConnectionService:
    """Own the intended MT5 account session for the bridge.

    The bridge owns connection monitoring and transient recovery. The MT5
    password is held only in memory; after a bridge-process restart, the
    service reloads the non-secret account identity and retrieves fresh
    credentials from AQE through the authenticated internal endpoint.
    """

    INTERNET_PROBES = (
        "https://www.google.com/generate_204",
        "https://www.msftconnecttest.com/connecttest.txt",
    )
    INTERNET_PROBE_TIMEOUT = 1.5
    INTERNET_PROBE_INTERVAL = 15.0
    MAX_RECONNECT_DELAY = 60.0
    MAX_AUTH_FAILURE_ATTEMPTS = 3

    def __init__(
        self,
        client: MT5Client | None = None,
        internet_probe: Callable[[], bool] | None = None,
    ) -> None:
        self.client = client or MT5Client()
        self._internet_probe = internet_probe or self._probe_public_internet

        self.login: int | None = None
        self.server: str | None = None
        self.name: str | None = None
        self.last_error: str | None = None

        # The password is intentionally process-memory only.
        self._password: str | None = None
        self._auto_reconnect = False
        self._auth_blocked = False
        self._auth_failure_attempts = 0

        # Serializes connection state transitions and calls into MT5Client.
        self._lock = RLock()
        self._session_generation = 0

        self._monitor_task: asyncio.Task[None] | None = None
        self._stopping = False

        self._internet_connected: bool | None = None
        self._last_internet_check_at: float | None = None
        self._next_internet_probe_at = 0.0

        self._last_connect_attempt_at: float | None = None
        self._last_recovery_action: str | None = None

        self._reconnect_attempts = 0
        self._next_retry_at = 0.0
        self._recovery_state = "DISCONNECTED"

        self._target_file = Path(settings.MT5_RECOVERY_TARGET_FILE)
        self._load_recovery_target()

    # =========================================================
    # PERSISTENT RECOVERY TARGET
    # =========================================================

    def _write_target_state_locked(self, data: dict[str, Any]) -> None:
        """Atomically persist non-secret recovery state."""
        self._target_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = self._target_file.with_suffix(
            self._target_file.suffix + ".tmp"
        )

        temporary_file.write_text(
            json.dumps(data, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary_file, self._target_file)

    def _persist_recovery_target_locked(self) -> None:
        """Persist account identity only, never the MT5 password."""
        if self.login is None or not self.server:
            return

        try:
            self._write_target_state_locked(
                {
                    "auto_reconnect": True,
                    "login": self.login,
                    "server": self.server,
                }
            )
        except Exception:
            logger.exception(
                "Could not persist the MT5 recovery target. "
                "Recovery after a bridge restart may require a new connection request."
            )

    def _clear_recovery_target_locked(self) -> None:
        """Clear recovery intent, falling back to a disabled marker."""
        try:
            self._target_file.unlink(missing_ok=True)
            return
        except OSError:
            logger.exception("Could not remove the MT5 recovery target file.")

        try:
            # If deletion is blocked, overwrite the existing state so a restart
            # does not interpret the previous identity as reconnect permission.
            self._write_target_state_locked({"auto_reconnect": False})
        except Exception:
            logger.critical(
                "Could not persist the manual-disconnect marker. "
                "Check recovery-state file permissions."
            )

    def _load_recovery_target(self) -> None:
        """Load the account identity after process startup, without a password."""
        try:
            if not self._target_file.exists():
                return

            data = json.loads(self._target_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Recovery state must be a JSON object.")

            if data.get("auto_reconnect", True) is not True:
                logger.info("Persisted MT5 recovery target is disabled.")
                return

            login = int(data["login"])
            server = str(data["server"]).strip()
            if login <= 0 or not server:
                raise ValueError("Invalid recovery account identity.")

        except FileNotFoundError:
            return
        except Exception:
            logger.exception("Persisted MT5 recovery target is invalid.")
            self._clear_recovery_target_locked()
            return

        self.login = login
        self.server = server
        self._auto_reconnect = True
        self._password = None
        self._recovery_state = "CREDENTIALS_REQUIRED"
        self._last_recovery_action = (
            "Restored account identity after bridge startup. "
            "Credentials will be requested securely from AQE."
        )

        logger.info(
            "Loaded MT5 recovery target for login=%s server=%s.",
            login,
            server,
        )

    # =========================================================
    # INTERNET MONITORING
    # =========================================================

    @classmethod
    def _probe_public_internet(cls) -> bool:
        """Check outbound HTTPS connectivity for diagnostics only."""
        for url in cls.INTERNET_PROBES:
            try:
                request = Request(
                    url,
                    headers={"User-Agent": "AQE-MT5-Bridge/1.0"},
                )
                try:
                    with urlopen(
                        request,
                        timeout=cls.INTERNET_PROBE_TIMEOUT,
                    ) as response:
                        status_code = response.status
                        body = response.read(256)
                except HTTPError as response:
                    # An HTTP error still indicates that DNS/TCP/TLS worked,
                    # but it does not satisfy either expected connectivity probe.
                    status_code = response.code
                    body = b""

                if url.endswith("/generate_204") and status_code == 204:
                    return True
                if (
                    url.endswith("/connecttest.txt")
                    and status_code == 200
                    and b"Microsoft Connect Test" in body
                ):
                    return True
            except Exception:
                continue

        return False

    # =========================================================
    # INTERNAL STATE HELPERS
    # =========================================================

    @staticmethod
    def _is_auth_failure(error: str) -> bool:
        """Recognize likely credential or authorization failures."""
        message = (error or "").casefold()
        indicators = (
            "authorization failed",
            "authentication failed",
            "invalid password",
            "wrong password",
            "incorrect password",
            "invalid login",
            "invalid credentials",
            "account disabled",
            "account blocked",
            "not authorized",
        )
        return any(term in message for term in indicators)

    @staticmethod
    def _account_matches(
        account: object | dict[str, Any] | None,
        login: int,
        server: str,
    ) -> bool:
        """Compare account identity for MT5 objects or AQE JSON dictionaries."""
        if account is None:
            return False

        if isinstance(account, dict):
            actual_login = account.get("login")
            actual_server = account.get("server")
        else:
            actual_login = getattr(account, "login", None)
            actual_server = getattr(account, "server", None)

        if actual_login is None or actual_server is None:
            return False

        return (
            str(actual_login).strip() == str(login).strip()
            and str(actual_server).strip().casefold() == str(server).strip().casefold()
        )

    def _read_client_error_locked(self) -> str:
        """Read the MT5 client's error without masking useful diagnostics."""
        message = getattr(self.client, "last_error_message", None)
        if message:
            return str(message)

        try:
            error = self.client.last_error()
        except Exception:
            return "MT5 connection attempt failed."

        if error in (None, (0, ""), (0, "No error")):
            return "MT5 connection attempt failed without an MT5 error detail."
        return str(error)

    def _reset_retry_state_locked(self) -> None:
        self._reconnect_attempts = 0
        self._next_retry_at = 0.0
        self._auth_failure_attempts = 0
        self._auth_blocked = False

    def _schedule_retry_locked(self) -> float:
        """Schedule the next retry with capped exponential backoff and jitter."""
        self._reconnect_attempts += 1
        base_delay = max(float(settings.MT5_RECONNECT_INTERVAL), 1.0)
        exponent = min(self._reconnect_attempts - 1, 6)
        delay = min(base_delay * (2**exponent), self.MAX_RECONNECT_DELAY)
        delay *= random.uniform(0.85, 1.15)
        self._next_retry_at = time.monotonic() + delay

        logger.warning(
            "MT5 recovery retry scheduled in %.1f seconds.",
            delay,
        )
        return delay

    def _record_failed_attempt_locked(self, error: str) -> None:
        """Record failed MT5 connection and schedule retry or auth blocking."""
        self.last_error = (error or "MT5 connection attempt failed.").strip()

        if self._is_auth_failure(self.last_error):
            self._auth_failure_attempts += 1
            if self._auth_failure_attempts >= self.MAX_AUTH_FAILURE_ATTEMPTS:
                self._auth_blocked = True
                self._auto_reconnect = False
                self._password = None
                self._next_retry_at = 0.0
                self._recovery_state = "AUTH_REQUIRED"
                self._last_recovery_action = (
                    "Automatic recovery stopped after repeated authentication "
                    "failures. Verify the account credentials and server."
                )
                self._clear_recovery_target_locked()
                logger.error("%s", self._last_recovery_action)
                return
        else:
            self._auth_failure_attempts = 0

        if not self._auto_reconnect:
            self._recovery_state = "DISCONNECTED"
            return

        if self._password is None:
            self._recovery_state = "CREDENTIALS_REQUIRED"
            return

        delay = self._schedule_retry_locked()
        self._recovery_state = (
            "INTERNET_UNAVAILABLE"
            if self._internet_connected is False
            else "RECONNECTING"
        )
        self._last_recovery_action = (
            f"Connection attempt failed; retry scheduled in {delay:.1f} seconds."
        )

    def _record_credential_fetch_failure_locked(self, error: str) -> None:
        """Back off when AQE cannot supply credentials."""
        self.last_error = error
        delay = self._schedule_retry_locked()
        self._recovery_state = "CREDENTIALS_UNAVAILABLE"
        self._last_recovery_action = (
            "Unable to reacquire MT5 credentials from AQE; "
            f"retry scheduled in {delay:.1f} seconds."
        )

    # =========================================================
    # CONNECTION HEALTH
    # =========================================================

    def _is_connected_locked(self) -> bool:
        """Verify the intended account without overwriting credential errors."""
        if self.login is None or self.server is None:
            return False

        # After a bridge restart there is a saved identity but no password yet.
        # Do not probe MT5's empty last_error() and overwrite the more useful
        # credential-recovery status. The monitor will fetch credentials.
        if self._password is None:
            return False

        try:
            if not self.client.is_connected():
                error = self._read_client_error_locked()
                if "without an MT5 error detail" not in error:
                    self.last_error = error
                return False

            account = self.client.account_info()
            if not self._account_matches(account, self.login, self.server):
                self.last_error = (
                    "The active MT5 account does not match the intended account."
                )
                return False

            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("MT5 connection health check failed: %s", exc)
            return False

    def is_connected(self) -> bool:
        with self._lock:
            connected = self._is_connected_locked()
            if connected:
                self._recovery_state = "ONLINE"
            return connected

    # =========================================================
    # AQE CREDENTIAL RECOVERY
    # =========================================================

    def _fetch_credentials_from_aqe(
        self,
        login: int,
        server: str,
    ) -> dict[str, Any]:
        """Fetch account credentials over the authenticated AQE API."""
        payload = json.dumps({"login": login, "server": server}).encode("utf-8")

        request = Request(
            settings.AQE_CREDENTIAL_RECOVERY_URL,
            data=payload,
            method="POST",
            headers={
                "X-Bridge-Token": settings.MT5_BRIDGE_TOKEN,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(
                request,
                timeout=settings.AQE_CREDENTIAL_RECOVERY_TIMEOUT,
            ) as response:
                response_body = response.read()
        except HTTPError as exc:
            # Do not include response body in logs; it may contain sensitive data.
            raise RuntimeError(
                f"AQE credential recovery returned HTTP {exc.code}."
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                "AQE credential recovery endpoint is unavailable."
            ) from exc

        try:
            result = json.loads(response_body.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "AQE credential recovery returned invalid JSON."
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError("AQE credential recovery returned an invalid response.")
        return result

    async def _restore_credentials_from_aqe(
        self,
        expected_generation: int,
        login: int,
        server: str,
    ) -> None:
        """Restore an in-memory password for the saved intended account."""
        try:
            result = await asyncio.to_thread(
                self._fetch_credentials_from_aqe,
                login,
                server,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            with self._lock:
                if (
                    expected_generation != self._session_generation
                    or not self._auto_reconnect
                    or self._stopping
                ):
                    return
                self._record_credential_fetch_failure_locked(str(exc))
            return

        try:
            recovered_login = int(result["login"])
            recovered_server = str(result["server"]).strip()
            recovered_password = result["password"]

            if not isinstance(recovered_password, str) or not recovered_password:
                raise ValueError("AQE returned no MT5 password.")

            # _account_matches explicitly supports the JSON dictionary response.
            if not self._account_matches(
                {"login": recovered_login, "server": recovered_server},
                login,
                server,
            ):
                raise ValueError("AQE returned credentials for a different account.")
        except (KeyError, TypeError, ValueError) as exc:
            with self._lock:
                if (
                    expected_generation != self._session_generation
                    or not self._auto_reconnect
                    or self._stopping
                ):
                    return
                self._record_credential_fetch_failure_locked(str(exc))
            return

        with self._lock:
            # Manual disconnect or a newer connection request supersedes fetch.
            if (
                expected_generation != self._session_generation
                or not self._auto_reconnect
                or self._stopping
                or self.login != login
                or self.server != server
                or self._auth_blocked
            ):
                return

            self._password = recovered_password
            self.last_error = None
            self._next_retry_at = 0.0
            self._recovery_state = "RECONNECTING"
            self._last_recovery_action = (
                "Credentials reacquired from AQE; reconnecting to MT5."
            )

        await asyncio.to_thread(
            self._attempt_reconnect,
            expected_generation,
        )

    # =========================================================
    # CONNECT
    # =========================================================

    def connect(self, login: int, password: str, server: str) -> bool:
        """Connect an account and establish bridge-owned recovery intent."""
        try:
            normalized_login = int(login)
            normalized_password = str(password)
            normalized_server = str(server).strip()

            if normalized_login <= 0:
                raise ValueError("MT5 login must be greater than zero.")
            if not normalized_password:
                raise ValueError("MT5 password cannot be empty.")
            if not normalized_server:
                raise ValueError("MT5 server cannot be empty.")
        except (TypeError, ValueError) as exc:
            with self._lock:
                self.last_error = str(exc)
            return False

        with self._lock:
            self._session_generation += 1
            self.login = normalized_login
            self.server = normalized_server
            self.name = None
            self._password = normalized_password
            self._auto_reconnect = True
            self._auth_blocked = False
            self._reset_retry_state_locked()

            # Persist before connecting so an interrupted first attempt can
            # recover following a bridge restart. This file never has a password.
            self._persist_recovery_target_locked()

            self.last_error = None
            self._last_connect_attempt_at = time.time()
            self._last_recovery_action = "Connecting to MT5."
            self._recovery_state = "CONNECTING"

            try:
                connected = self.client.connect(
                    login=normalized_login,
                    password=normalized_password,
                    server=normalized_server,
                )
                if not connected:
                    self._record_failed_attempt_locked(self._read_client_error_locked())
                    return False
                account = self.client.account_info()
            except Exception as exc:
                logger.exception("MT5 connection request failed.")
                self._record_failed_attempt_locked(str(exc))
                return False

            if not self._account_matches(
                account,
                normalized_login,
                normalized_server,
            ):
                self._record_failed_attempt_locked(
                    "MT5 connected, but the requested account identity "
                    "could not be verified."
                )
                return False

            self.login = int(account.login)
            self.server = str(account.server)
            self.name = getattr(account, "name", None)
            self.last_error = None
            self._reset_retry_state_locked()
            self._persist_recovery_target_locked()
            self._recovery_state = "ONLINE"
            self._last_recovery_action = (
                "MT5 connection established and account verified."
            )

            logger.info(
                "MT5 connection verified for login=%s server=%s.",
                self.login,
                self.server,
            )
            return True

    # =========================================================
    # DISCONNECT
    # =========================================================

    def disconnect(self) -> dict[str, Any]:
        """Deliberately disconnect and clear automatic recovery intent."""
        with self._lock:
            self._session_generation += 1
            self._auto_reconnect = False
            self._auth_blocked = False
            self._password = None
            self._reset_retry_state_locked()

            try:
                self.client.disconnect()
            finally:
                self.login = None
                self.server = None
                self.name = None
                self.last_error = None
                self._clear_recovery_target_locked()
                self._recovery_state = "MANUAL_DISCONNECTED"
                self._last_recovery_action = "Disconnected by an explicit request."

        logger.info("MT5 disconnected by request.")
        return {"success": True, "message": "Disconnected successfully."}

    # =========================================================
    # STATUS
    # =========================================================

    def status(self) -> dict[str, Any]:
        """Return connection and recovery diagnostics, excluding credentials."""
        with self._lock:
            connected = self._is_connected_locked()
            try:
                terminal = self.client.terminal_info()
            except Exception:
                terminal = None

            if connected:
                self._recovery_state = "ONLINE"

            return {
                "connected": connected,
                "login": self.login,
                "server": self.server,
                "name": self.name,
                "last_error": self.last_error,
                "internet_connected": self._internet_connected,
                "terminal_running": terminal is not None,
                "terminal_connected": (
                    bool(getattr(terminal, "connected", False))
                    if terminal is not None
                    else False
                ),
                "recovery_state": self._recovery_state,
                "reconnect_attempts": self._reconnect_attempts,
                "last_connect_attempt_at": self._last_connect_attempt_at,
                "last_internet_check_at": self._last_internet_check_at,
                "last_recovery_action": self._last_recovery_action,
            }

    # =========================================================
    # RECONNECT
    # =========================================================

    def _attempt_reconnect(self, expected_generation: int) -> bool:
        """Reconnect and verify the target account using the in-memory password."""
        with self._lock:
            if self._stopping:
                return False
            if expected_generation != self._session_generation:
                return False
            if (
                not self._auto_reconnect
                or self._auth_blocked
                or self.login is None
                or self.server is None
                or self._password is None
            ):
                return False
            if time.monotonic() < self._next_retry_at:
                return False

            login = self.login
            server = self.server
            password = self._password
            self._last_connect_attempt_at = time.time()
            self._recovery_state = "RECONNECTING"
            self._last_recovery_action = (
                "Attempting to restore the MT5 terminal connection."
            )

            logger.warning(
                "Attempting MT5 recovery for login=%s server=%s.",
                login,
                server,
            )

            try:
                connected = self.client.connect(
                    login=login,
                    password=password,
                    server=server,
                )
                if not connected:
                    self._record_failed_attempt_locked(self._read_client_error_locked())
                    return False
                account = self.client.account_info()
            except Exception as exc:
                logger.exception("Automatic MT5 reconnection failed.")
                self._record_failed_attempt_locked(str(exc))
                return False

            if self._stopping or expected_generation != self._session_generation:
                return False

            if not self._account_matches(account, login, server):
                self._record_failed_attempt_locked(
                    "Recovered MT5 session failed account verification."
                )
                return False

            self.login = int(account.login)
            self.server = str(account.server)
            self.name = getattr(account, "name", None)
            self.last_error = None
            self._reset_retry_state_locked()
            self._persist_recovery_target_locked()
            self._recovery_state = "ONLINE"
            self._last_recovery_action = "MT5 connection restored and account verified."

            logger.info(
                "MT5 connection recovered for login=%s server=%s.",
                self.login,
                self.server,
            )
            return True

    # =========================================================
    # BACKGROUND MONITOR
    # =========================================================

    async def _monitor(self) -> None:
        """Monitor MT5 and recover credentials/session with bounded retries."""
        interval = max(float(settings.MT5_RECONNECT_INTERVAL), 1.0)
        logger.info(
            "MT5 connection monitor started; interval=%.1f seconds.",
            interval,
        )

        while not self._stopping:
            try:
                now = time.monotonic()
                with self._lock:
                    should_probe = now >= self._next_internet_probe_at
                    if should_probe:
                        self._next_internet_probe_at = (
                            now + self.INTERNET_PROBE_INTERVAL
                        )

                # Public internet probing is diagnostic, not a recovery gate.
                if should_probe:
                    try:
                        internet = await asyncio.to_thread(self._internet_probe)
                    except Exception:
                        internet = False
                        logger.warning(
                            "Public internet probe failed.",
                            exc_info=True,
                        )
                    with self._lock:
                        self._internet_connected = bool(internet)
                        self._last_internet_check_at = time.time()

                with self._lock:
                    generation = self._session_generation
                    has_target = (
                        self._auto_reconnect
                        and not self._auth_blocked
                        and self.login is not None
                        and self.server is not None
                    )
                    target_login = self.login
                    target_server = self.server

                if has_target:
                    connected = await asyncio.to_thread(self.is_connected)
                    action = "none"
                    with self._lock:
                        if generation == self._session_generation:
                            if connected:
                                self._reset_retry_state_locked()
                                self._recovery_state = "ONLINE"
                                self._last_recovery_action = "MT5 connection healthy."
                            elif self._auth_blocked:
                                self._recovery_state = "AUTH_REQUIRED"
                            elif time.monotonic() >= self._next_retry_at:
                                action = (
                                    "credentials"
                                    if self._password is None
                                    else "reconnect"
                                )

                    if action == "credentials":
                        await self._restore_credentials_from_aqe(
                            generation,
                            int(target_login),
                            str(target_server),
                        )
                    elif action == "reconnect":
                        await asyncio.to_thread(
                            self._attempt_reconnect,
                            generation,
                        )

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error in MT5 connection monitor.")
                with self._lock:
                    if self._auto_reconnect and not self._auth_blocked:
                        self._recovery_state = "DEGRADED"

            if self._stopping:
                break
            await asyncio.sleep(interval)

        logger.info("MT5 connection monitor stopped.")

    # =========================================================
    # MONITOR LIFECYCLE
    # =========================================================

    async def start_monitor(self) -> None:
        """Start the bridge-owned connection monitor."""
        task = self._monitor_task
        if task is not None and not task.done():
            return

        self._stopping = False
        self._monitor_task = asyncio.create_task(
            self._monitor(),
            name="mt5-connection-monitor",
        )
        logger.info("MT5 connection monitor scheduled.")

    async def stop_monitor(self) -> None:
        """Stop monitoring without deleting the persisted recovery target."""
        self._stopping = True
        task = self._monitor_task
        self._monitor_task = None

        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        logger.info("MT5 connection monitor stopped.")

    # =========================================================
    # TERMINAL HELPERS
    # =========================================================

    def version(self):
        with self._lock:
            return self.client.version()


connection_service = ConnectionService()
