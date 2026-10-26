#!/usr/bin/env python3
"""
DeskAI Layer 1 Mutation Testing Harness.
Automates 24 security and architectural mutation checks against the real test suite.
Reports kill rate, killing tests, and mutation outcomes.
"""

import subprocess
import sys
from pathlib import Path

MUTATIONS = [
    {
        "id": 1,
        "name": "Host Check on /auth/redeem",
        "file": "src/deskai/server/supervisor.py",
        "target": "if not is_valid_loopback_host(host, self.port):",
        "mutant": "if False and not is_valid_loopback_host(host, self.port):",
        "test": (
            "tests.test_task7_security_headers."
            "TestSecurityHeadersAndHardening.test_auth_redeem_host_mismatch_returns_403"
        ),
    },
    {
        "id": 2,
        "name": "Host Check on /ws",
        "file": "src/deskai/server/supervisor.py",
        "target": 'host = ws.headers.get("host", "")\n            if not is_valid_loopback_host(host, self.port):',
        "mutant": (
            'host = ws.headers.get("host", "")\n'
            "            if False and not is_valid_loopback_host(host, self.port):"
        ),
        "test": "tests.test_runtime.TestDeskAIRuntimeServer.test_desktop_supervisor_runtime_lifecycle",
    },
    {
        "id": 3,
        "name": "Origin Check on /ws",
        "file": "src/deskai/server/supervisor.py",
        "target": 'if origin != f"http://127.0.0.1:{self.port}":',
        "mutant": 'if False and origin != f"http://127.0.0.1:{self.port}":',
        "test": "tests.test_runtime.TestDeskAIRuntimeServer.test_desktop_supervisor_runtime_lifecycle",
    },
    {
        "id": 4,
        "name": "Session Cookie Check on /ws",
        "file": "src/deskai/server/supervisor.py",
        "target": "if not self.security.is_valid_session(cookie):",
        "mutant": "if False and not self.security.is_valid_session(cookie):",
        "test": "tests.test_runtime.TestDeskAIRuntimeServer.test_desktop_supervisor_runtime_lifecycle",
    },
    {
        "id": 5,
        "name": "Launch Token Single-Use (Replay Guard)",
        "file": "src/deskai/server/security.py",
        "target": "self.launch_token = None",
        "mutant": "pass  # self.launch_token = None",
        "test": "tests.test_runtime.TestDeskAIRuntimeServer.test_desktop_supervisor_runtime_lifecycle",
    },
    {
        "id": 6,
        "name": "Commonpath Sandbox Boundary Check",
        "file": "src/deskai/utils/path.py",
        "target": "return posixpath.commonpath([real_target, real_root]) == real_root",
        "mutant": "return True",
        "test": "tests.test_task8_path_sandbox.TestPathSandboxAndFileOperations.test_workspace_path_sandbox_guards",
    },
    {
        "id": 7,
        "name": "Disallowed System Roots on select_folder",
        "file": "src/deskai/bridge/api.py",
        "target": "if is_disallowed_workspace_root(folder_path):",
        "mutant": "if False and is_disallowed_workspace_root(folder_path):",
        "test": (
            "tests.test_task8_path_sandbox."
            "TestPathSandboxAndFileOperations.test_select_folder_rejects_disallowed_system_root"
        ),
    },
    {
        "id": 8,
        "name": "DOMPurify Sanitization on Stream Output",
        "file": "src/deskai/static/js/stream.js",
        "target": "const cleanHtml = window.DOMPurify.sanitize(window.marked.parse(this.accumulatedText)",
        "mutant": (
            "const cleanHtml = this.accumulatedText; "
            "// window.DOMPurify.sanitize(window.marked.parse(this.accumulatedText)"
        ),
        "test": (
            "tests.test_task2_security_injection."
            "TestSecurityInjectionHardening.test_stream_purify_strips_script_and_event_handlers"
        ),
    },
    {
        "id": 9,
        "name": "WebSocket Frame Size 64KB Enforcement",
        "file": "src/deskai/server/supervisor.py",
        "target": "ws_max_size=65536,",
        "mutant": "ws_max_size=1048576,",
        "test": (
            "tests.test_task5_websocket_abuse." "TestWebSocketAbuseProtection.test_oversized_payload_rejected_with_1009"
        ),
    },
    {
        "id": 10,
        "name": "Session Frame Rate Limiting (30 msgs/s)",
        "file": "src/deskai/server/supervisor.py",
        "target": "if tokens < 1.0:",
        "mutant": "if False and tokens < 1.0:",
        "test": (
            "tests.test_task5_websocket_abuse."
            "TestWebSocketAbuseProtection.test_rate_limiter_terminates_flooding_socket"
        ),
    },
    {
        "id": 11,
        "name": "Duplicate uec.approve Idempotency / State Guard",
        "file": "src/deskai/server/supervisor.py",
        "target": "if next_state in allowed:",
        "mutant": "if True:  # bypass transition table",
        "test": (
            "tests.test_task4_uec_state_machine."
            "TestUECStateMachineServer.test_server_rejects_invalid_fsm_transition_from_idle"
        ),
    },
    {
        "id": 12,
        "name": "Socket Concurrency Limit (Max 4 per Session)",
        "file": "src/deskai/server/supervisor.py",
        "target": "if len(self.security.get_session_sockets(cookie)) >= 4:",
        "mutant": "if False and len(self.security.get_session_sockets(cookie)) >= 4:",
        "test": (
            "tests.test_task5_websocket_abuse." "TestWebSocketAbuseProtection.test_session_socket_concurrency_limit"
        ),
    },
    {
        "id": 13,
        "name": "FSM Invalid State Transition Guard",
        "file": "src/deskai/server/supervisor.py",
        "target": "if target_state in allowed:",
        "mutant": "if False:  # bypass transition guard",
        "test": "tests.test_task4_uec_state_machine.TestUECStateMachineServer.test_valid_transition_to_planning",
    },
    {
        "id": 14,
        "name": "X-Frame-Options: DENY Header",
        "file": "src/deskai/server/security.py",
        "target": 'response.headers["X-Frame-Options"] = "DENY"',
        "mutant": "pass  # drop X-Frame-Options header",
        "test": (
            "tests.test_task7_security_headers."
            "TestSecurityHeadersAndHardening.test_http_security_headers_present_on_root_and_redeem"
        ),
    },
    {
        "id": 15,
        "name": "Content-Security-Policy Strict Header",
        "file": "src/deskai/server/security.py",
        "target": 'response.headers["Content-Security-Policy"] = self.get_content_security_policy()',
        "mutant": "pass  # drop CSP header",
        "test": "tests.test_contracts.TestDeskAILayer1Contracts.test_runtime_server_token_and_csp_headers",
    },
    {
        "id": 16,
        "name": "Ensure unsafe-eval is present in CSP for PyWebView Bridge",
        "file": "src/deskai/server/security.py",
        "target": "f\"script-src 'self' 'unsafe-eval'; \"",
        "mutant": "f\"script-src 'self'; \"",
        "test": (
            "tests.test_task7_security_headers."
            "TestSecurityHeadersAndHardening.test_csp_strictly_drops_unsafe_eval_and_includes_frame_ancestors"
        ),
    },
    {
        "id": 17,
        "name": "SO_EXCLUSIVEADDRUSE on Windows Bind",
        "file": "src/deskai/utils/net.py",
        "target": "sock.setsockopt(socket.SOL_SOCKET, so_exclusive, 1)",
        "mutant": "sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)",
        "test": (
            "tests.test_task7_security_headers."
            "TestSecurityHeadersAndHardening.test_windows_bind_uses_so_exclusiveaddruse"
        ),
    },
    {
        "id": 18,
        "name": "Stream Throttle Trailing-Edge Render",
        "file": "src/deskai/static/js/stream.js",
        "target": "this.trailingTimer = setTimeout(() => {",
        "mutant": "this.trailingTimer = null; // setTimeout",
        "test": "tests.test_task10_theme_a11y.TestThemeAndAccessibility.test_stream_throttle_trailing_edge",
    },
    {
        "id": 19,
        "name": "_exit_confirmed Single Confirmation Flag",
        "file": "src/deskai/bridge/lifecycle.py",
        "target": "if result:\n                self._exit_confirmed = True",
        "mutant": "if result:\n                pass  # self._exit_confirmed = True",
        "test": (
            "tests.test_task6_frameless_lifecycle."
            "TestFramelessWindowAndLifecycle.test_exit_confirmed_prevents_double_prompt"
        ),
    },
    {
        "id": 20,
        "name": "Perimeter Resize Handles >= 6px",
        "file": "src/deskai/static/css/layout.css",
        "target": (
            "height: 6px;\n"
            "  cursor: ns-resize;\n"
            "}\n\n"
            ".resize-handle.bottom {\n"
            "  bottom: 0;\n"
            "  left: 8px;\n"
            "  right: 8px;\n"
            "  height: 6px;"
        ),
        "mutant": (
            "height: 2px;\n"
            "  cursor: ns-resize;\n"
            "}\n\n"
            ".resize-handle.bottom {\n"
            "  bottom: 0;\n"
            "  left: 8px;\n"
            "  right: 8px;\n"
            "  height: 2px;"
        ),
        "test": "tests.test_task10_theme_a11y.TestThemeAndAccessibility.test_resize_handles_size_at_least_6px",
    },
    {
        "id": 21,
        "name": "External URL Navigation Interception",
        "file": "src/deskai/static/js/events.js",
        "target": ('if (url.startsWith("http://") || ' 'url.startsWith("https://") || ' 'url.startsWith("mailto:")) {'),
        "mutant": (
            'if (false && (url.startsWith("http://") || '
            'url.startsWith("https://") || '
            'url.startsWith("mailto:"))) {'
        ),
        "test": (
            "tests.test_task2_security_injection."
            "TestSecurityInjectionHardening.test_events_js_external_link_interceptor"
        ),
    },
    {
        "id": 22,
        "name": "DesktopBridgeAPI Origin Guard",
        "file": "src/deskai/bridge/api.py",
        "target": (
            "def select_folder(self) -> dict:\n"
            '        """Opens native OS folder selection dialog."""\n'
            "        if not self._is_origin_allowed():"
        ),
        "mutant": (
            "def select_folder(self) -> dict:\n"
            '        """Opens native OS folder selection dialog."""\n'
            "        if False and not self._is_origin_allowed():"
        ),
        "test": (
            "tests.test_task2_security_injection."
            "TestSecurityInjectionHardening.test_origin_guard_blocks_unauthorized_origin"
        ),
    },
    {
        "id": 23,
        "name": "read_file 10 MB Size Limit",
        "file": "src/deskai/bridge/api.py",
        "target": "if os.path.getsize(canonical) > 10 * 1024 * 1024:",
        "mutant": "if False and os.path.getsize(canonical) > 10 * 1024 * 1024:",
        "test": (
            "tests.test_task8_path_sandbox." "TestPathSandboxAndFileOperations.test_bridge_read_write_list_operations"
        ),
    },
    {
        "id": 24,
        "name": "write_file Atomic Replacement",
        "file": "src/deskai/bridge/api.py",
        "target": "os.replace(temp_name, canonical)",
        "mutant": "pass  # bypass os.replace",
        "test": (
            "tests.test_task8_path_sandbox." "TestPathSandboxAndFileOperations.test_bridge_read_write_list_operations"
        ),
    },
]


def run_mutation_check():
    print("=" * 80)
    print(" DeskAI Layer 1 Automated Mutation Testing Harness (24 Mutants)")
    print("=" * 80)

    killed_count = 0
    results = []

    for item in MUTATIONS:
        m_id = item["id"]
        name = item["name"]
        file_path = Path(item["file"])
        target = item["target"]
        mutant = item["mutant"]
        test_cmd = item["test"]

        if not file_path.exists():
            results.append((m_id, name, item["file"], test_cmd, "ERROR", f"File {file_path} not found"))
            continue

        original_content = file_path.read_text(encoding="utf-8")
        if target not in original_content:
            results.append((m_id, name, item["file"], test_cmd, "ERROR", "Target string not found"))
            continue

        # Apply mutation
        mutated_content = original_content.replace(target, mutant, 1)
        file_path.write_text(mutated_content, encoding="utf-8")

        try:
            # Execute target test with -B to prevent stale bytecode
            proc = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", test_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )

            if proc.returncode != 0:
                # Test failed -> Mutant was caught and killed!
                killed_count += 1
                status = "KILLED"
                reason = "Test failed on mutation as expected"
            else:
                status = "SURVIVED"
                reason = "Test unexpectedly passed despite mutation"
        except subprocess.TimeoutExpired:
            # Timeout also counts as killed
            killed_count += 1
            status = "KILLED"
            reason = "Test timed out on mutation"
        except Exception as e:
            status = "ERROR"
            reason = str(e)
        finally:
            # Always restore original content
            file_path.write_text(original_content, encoding="utf-8")

        results.append((m_id, name, item["file"], test_cmd, status, reason))
        print(f"[{m_id:02d}/24] {status:8s} | {name:<48} | {test_cmd.split('.')[-1]}")

    print("\n" + "=" * 80)
    print(" MUTATION TESTING REPORT SUMMARY")
    print("=" * 80)
    print(f"Total Mutants Evaluated : {len(MUTATIONS)}")
    print(f"Mutants Killed          : {killed_count}")
    print(f"Mutants Survived        : {len(MUTATIONS) - killed_count}")
    kill_rate = (killed_count / len(MUTATIONS)) * 100
    print(f"Final Mutation Kill Rate: {kill_rate:.1f}%")
    print("=" * 80)

    # Print markdown table
    print("\n| # | Mutant Description | Target File | Killing Test | Result |")
    print("|---|---|---|---|---|")
    for r in results:
        print(f"| {r[0]} | {r[1]} | `{r[2]}` | `{r[3].split('.')[-1]}` | **{r[4]}** |")

    return kill_rate >= 95.0


if __name__ == "__main__":
    success = run_mutation_check()
    sys.exit(0 if success else 1)
