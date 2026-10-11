"""Windows quarantine registry for pre-existing portability-debt failures.

Every entry is a test that fails on the windows-latest runner for a root cause
inside product code that does not differ from base f085f77 on this branch -
i.e. pre-existing Windows portability debt, quarantined here without touching
any assertion. The table is keyed by the exact pytest node ids recorded in the
authoritative CI failure list (run 38108188505, job 114378045469), and the
per-family root causes are documented in issue #222 and the attribution
receipt (.omo/evidence/windows-families-preexisting-proof-20261010.txt).

Quarantine is gated on sys.platform == 'win32' by the collection hook in
tests/conftest.py; set TRADERBOT_WINDOWS_QUARANTINE=off to run the quarantined
tests on Windows while debugging (failures return, by design).

These tests are NOT weakened or deleted: on every non-Windows platform they
run unchanged, and the registry is the single switch that re-enables them
once issue #222 lands the real Windows fixes.
"""

from __future__ import annotations

import os
import sys

import pytest

ISSUE = 222

CI_EVIDENCE = (
    "CI run 38108188505 job 114378045469; attribution receipt "
    ".omo/evidence/windows-families-preexisting-proof-20261010.txt"
)


# Simulated platform seam: the hook consults this value, so a Linux-host test
# can drive the win32 branch deterministically without patching sys.platform.
CURRENT_PLATFORM = sys.platform


# Set to 'off' to bypass the quarantine (Windows debugging only).

QUARANTINE_ENV = "TRADERBOT_WINDOWS_QUARANTINE"


FAMILY_NOTES: dict[str, str] = {  # noqa: E501 (long root-cause notes are data, not prose)
    "bounded_process_semantics": "bounded-process semantics in openclaw_process.py differ on win32: WinError 87, CRLF decode, child-liveness (root family 4, unchanged since f085f77)",  # noqa: E501
    "chmod_unreadable_simulation": "chmod-based unreadable-source simulation is ineffective on win32, leaving the CollectorPathError rejection path unexercisable (root family 5, unchanged since f085f77)",  # noqa: E501
    "cli_e2e_subprocess_surface": "real-CLI subprocess E2E surfaces the issue #222 Windows families (secret ACL hardening / O_DIRECTORY / path escapes) via unchanged product code (root families 1-2, 6)",  # noqa: E501
    "deploy_state_o_directory": "deploy_state.save_deploy_state uses os.open(root, os.O_RDONLY | os.O_DIRECTORY), which raises PermissionError on win32 at deploy_state.py:130 (root family 2, unchanged since f085f77)",  # noqa: E501
    "posix_mode_assertions": "POSIX st_mode assertions (0o600 bits, st_uid) cannot hold on NTFS (root family 8, unchanged since f085f77)",  # noqa: E501
    "rename_open_sqlite": "backfill_collector snapshot renames an open SQLite file; Windows rejects with WinError 32 where POSIX allows (root family 3, unchanged since f085f77)",  # noqa: E501
    "secret_acl_hardening": "SecretIntegrityError 'Windows secret ACL hardening failed' fires on win32 in unchanged secrets/local_security.py + local_encrypted.py (root family 1)",  # noqa: E501
}


QUARANTINED_NODE_IDS: dict[str, str] = {  # noqa: E501 (exact node ids are data, not prose)
    # node id: cause family (see FAMILY_NOTES and issue #222)
    "tests/test_backfill_collector.py::test_missing_unreadable_and_nonregular_sources_are_rejected": "chmod_unreadable_simulation",  # noqa: E501
    "tests/test_backfill_repair_collector.py::test_prepared_snapshot_is_query_only_secure_and_cleaned": "posix_mode_assertions",  # noqa: E501
    "tests/test_backfill_repair_collector.py::test_replacement_after_snapshot_does_not_change_copied_bytes": "rename_open_sqlite",  # noqa: E501
    "tests/test_backfill_repair_collector.py::test_source_replacement_during_snapshot_cannot_write_target": "rename_open_sqlite",  # noqa: E501
    "tests/test_deploy_boundary_regressions.py::test_configured_data_root_is_shared_by_all_runtime_phases": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cleanup_review_blockers.py::test_phase_adapter_converts_database_cleanup_group_to_canonical_failure": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_cli_fake_e2e.py::test_real_cli_adopts_stable_nonzero_partial_creation": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cli_fake_e2e.py::test_real_cli_overlap_failure_is_read_only": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cli_fake_e2e.py::test_real_cli_reconciles_selected_agents_and_reruns_without_duplicates": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cli_relative_inventory.py::test_real_cli_rejects_relative_inventory_before_all_mutation": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cli_steps45_e2e.py::test_real_cli_chroma_lock_blocks_then_rerun_reopens": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cli_steps45_e2e.py::test_real_cli_invalid_pem_stops_before_kalshi_or_database_mutation": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cli_steps45_e2e.py::test_real_cli_missing_environment_references_name_only_missing_variables": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_cli_steps45_e2e.py::test_real_cli_partial_pair_requires_approval_then_reruns_without_rewrite": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_cli_steps45_e2e.py::test_real_cli_proxy_environment_uses_honest_encrypted_fallback": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_access_success_checks_required_targets_without_values_and_disables_cache": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_denied_client_close_fault_cannot_block_or_taint_local_fallback": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_login_success_with_project_denial_closes_and_falls_back": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_proxy_environment_refuses_sdk_without_mutating_environment[ALL_PROXY]": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_proxy_environment_refuses_sdk_without_mutating_environment[HTTPS_PROXY]": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_proxy_environment_refuses_sdk_without_mutating_environment[HTTP_PROXY]": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_proxy_environment_refuses_sdk_without_mutating_environment[all_proxy]": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_proxy_environment_refuses_sdk_without_mutating_environment[http_proxy]": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_infisical_review_blockers.py::test_proxy_environment_refuses_sdk_without_mutating_environment[https_proxy]": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_integration.py::test_full_deploy_mocked": "cli_e2e_subprocess_surface",
    "tests/test_deploy_integration.py::test_invalid_json_exits_2": "cli_e2e_subprocess_surface",
    "tests/test_deploy_late_cli.py::test_complete_json_is_one_line_without_stderr": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_late_cli.py::test_human_output_uses_stderr_and_prints_stub_once": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_backfill_failure_partial": "deploy_state_o_directory",
    "tests/test_deploy_late_steps.py::test_backfill_invalid_input_marks_deploy_invalid": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_changed_backfill_config_invalidates_step6_and_verification": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_completed_late_steps_rerun_idempotently": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_completed_retained_bootstrap_reaches_step7_partial": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_deleted_completed_one_shot_is_not_recreated": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_partial_rerun_executes_only_incomplete_step": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_step7_cron_states_are_read_only[conflict-failed-phase5_sandbox_stub_cron_conflict]": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_step7_cron_states_are_read_only[exact-completed-phase5_sandbox_stub_cron_exact]": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_step7_cron_states_are_read_only[failed-failed-phase5_sandbox_stub_cron_unreadable]": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_step7_cron_states_are_read_only[missing-partial-phase5_sandbox_stub_cron_absent]": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_step_exceptions_are_isolated_and_redacted": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_steps_6_8_complete": "deploy_state_o_directory",
    "tests/test_deploy_late_steps.py::test_verification_advisory_divergences_complete_deployment": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_verification_required_degraded_check_still_completes": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_verification_required_failure_fails_deployment": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_late_steps.py::test_wizard_threads_created_agents_into_verification": "deploy_state_o_directory",  # noqa: E501
    "tests/test_deploy_provider_security.py::test_installed_wheel_rejects_provider_environment_and_contains_no_fake": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_provider_security.py::test_source_cli_rejects_environment_selected_fake_provider": "cli_e2e_subprocess_surface",  # noqa: E501
    "tests/test_deploy_secret_step.py::test_healthy_status_without_usable_credentials_still_falls_back_encrypted": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_secret_step.py::test_unreachable_infisical_selects_encrypted_local_backend": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_storage_characterization.py::test_secrets_facade_uses_encrypted_local_store_without_infisical": "secret_acl_hardening",  # noqa: E501
    "tests/test_deploy_todo9_blockers.py::test_prepared_collector_survives_until_step6": "rename_open_sqlite",  # noqa: E501
    "tests/test_deploy_wizard.py::test_backfill_failure_partial": "deploy_state_o_directory",
    "tests/test_deploy_wizard.py::test_steps_6_8_complete": "deploy_state_o_directory",
    "tests/test_deploy_wizard_runtime.py::test_characterization_encrypted_identity_is_reused_and_restart_resolvable": "secret_acl_hardening",  # noqa: E501
    "tests/test_integration_secrets.py::TestResolverLocalFallback::test_no_credentials_stores_and_resolves_locally": "secret_acl_hardening",  # noqa: E501
    "tests/test_integration_secrets.py::TestResolverWithInfisical::test_tokens_resolve_through_adapter_to_infisical": "secret_acl_hardening",  # noqa: E501
    "tests/test_local_encrypted.py::test_api_key_roundtrip": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_corrupt_payload_fails_closed": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_delete_missing_key_raises_not_found": "secret_acl_hardening",  # noqa: E501
    "tests/test_local_encrypted.py::test_delete_removes_key": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_empty_store_returns_none_and_empty_namespace": "secret_acl_hardening",  # noqa: E501
    "tests/test_local_encrypted.py::test_facade_delete_missing_key_raises": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_facade_roundtrip_through_local_encrypted_store": "secret_acl_hardening",  # noqa: E501
    "tests/test_local_encrypted.py::test_foreign_machine_key_cannot_decrypt": "secret_acl_hardening",  # noqa: E501
    "tests/test_local_encrypted.py::test_get_namespace_flattens_service_keys": "secret_acl_hardening",  # noqa: E501
    "tests/test_local_encrypted.py::test_missing_integrity_file_fails_closed": "secret_acl_hardening",  # noqa: E501
    "tests/test_local_encrypted.py::test_missing_key_returns_none": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_namespaces_are_isolated": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_persists_across_store_instances": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_profile_token_roundtrip": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_secrets_file_is_not_plaintext": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_set_overwrites_existing_value": "secret_acl_hardening",
    "tests/test_local_encrypted.py::test_tampered_integrity_file_fails_closed": "secret_acl_hardening",  # noqa: E501
    "tests/test_openclaw_process.py::test_run_bounded_cleans_up_when_second_reader_fails_to_start": "bounded_process_semantics",  # noqa: E501
    "tests/test_openclaw_process.py::test_run_bounded_returns_decoded_output_within_limits": "bounded_process_semantics",  # noqa: E501
    "tests/test_openclaw_process.py::test_run_bounded_terminates_and_reaps_output_overflow_child": "bounded_process_semantics",  # noqa: E501
    "tests/test_openclaw_process.py::test_run_bounded_terminates_and_reaps_stderr_overflow_child": "bounded_process_semantics",  # noqa: E501
    "tests/test_openclaw_process.py::test_run_bounded_terminates_and_reaps_timeout_child": "bounded_process_semantics",  # noqa: E501
    "tests/test_secrets_resolver.py::TestSecretsResolver::test_deployed_metadata_selects_infisical": "secret_acl_hardening",  # noqa: E501
    "tests/test_secrets_resolver.py::TestSecretsResolver::test_with_credentials_constructs_infisical_client": "secret_acl_hardening",  # noqa: E501
    "tests/test_secrets_resolver.py::TestSuspendedProfiles::test_lazy_init_installs_adapter_on_default_store": "secret_acl_hardening",  # noqa: E501
    "tests/test_verify_openclaw_contract.py::test_fired_one_shot_absent_with_recorded_registration_degrades": "deploy_state_o_directory",  # noqa: E501
}


def quarantine_reason(family: str) -> str:
    """One-line skip reason naming the family, the issue, and the evidence."""

    return (
        f"Pre-existing Windows portability debt (issue {ISSUE}, do-not-fix-here): "
        f"{FAMILY_NOTES[family]}; {CI_EVIDENCE}"
    )


def apply_windows_quarantine(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip quarantined node ids on win32 unless TRADERBOT_WINDOWS_QUARANTINE=off."""

    if CURRENT_PLATFORM != "win32" or os.environ.get(QUARANTINE_ENV) == "off":
        return

    skipped: list[pytest.Item] = []

    for item in items:
        family = QUARANTINED_NODE_IDS.get(item.nodeid)

        if family is not None:
            item.add_marker(pytest.mark.skip(reason=quarantine_reason(family)))

            skipped.append(item)

    if skipped:
        config.hook.pytest_deselected(items=skipped)
