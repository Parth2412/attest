"""Import-light Typer command tree and root process boundary."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Annotated, Any, Final

import typer
from typer.core import TyperGroup

_PACKAGE_VERSION = metadata.version("attest-cli")
COMMAND_EXIT_CODES: Final[dict[str, tuple[int, ...]]] = {
    "init": (0, 1, 2),
    "collect": (0, 1, 2, 6),
    "build": (0, 1, 2),
    "sign": (0, 1, 2, 6),
    "push": (0, 1, 2, 6),
    "verify": (0, 1, 2, 4, 5),
    "gate": (0, 1, 2, 3, 4, 5),
    "run": (0, 1, 2, 3, 4, 5, 6),
    "inspect": (0, 1, 2, 5),
    "config-show": (0, 1, 2),
    "doctor": (0, 1, 2),
    "version": (0, 1),
}


def _leaf_name(arguments: Sequence[str]) -> str:
    commands = {
        "init",
        "collect",
        "build",
        "sign",
        "push",
        "verify",
        "gate",
        "run",
        "inspect",
        "doctor",
        "version",
    }
    for index, argument in enumerate(arguments):
        if argument == "config" and index + 1 < len(arguments) and arguments[index + 1] == "show":
            return "config-show"
        if argument in commands:
            return argument
        if not argument.startswith("-"):
            return "attest"
    return "attest"


def _boundary_report(arguments: Sequence[str], *, internal: bool) -> int:
    from attest_cli.errors import cli_error
    from attest_cli.models import CliDiagnostic, make_report
    from attest_cli.output import emit_report

    error = cli_error("ERR-INTERNAL-001" if internal else "ERR-CONFIG-001")
    diagnostic = CliDiagnostic(
        code=error.code,
        message=error.message,
        remediation=error.remediation,
    )
    report = make_report(
        _leaf_name(arguments),
        "failed",
        int(error.exit_code),
        None,
        error=diagnostic,
    )
    emit_report(
        report,
        json_output="--json" in arguments,
        no_color="--no-color" in arguments,
        stdout=sys.stdout,
        stderr=sys.stderr,
        is_tty=sys.stderr.isatty(),
        no_color_environment="NO_COLOR" in os.environ,
    )
    return int(error.exit_code)


class BoundaryGroup(TyperGroup):
    """Convert framework and unexpected failures into the stable report contract."""

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        arguments = list(sys.argv[1:] if args is None else args)
        try:
            result = super().main(
                args=arguments,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except Exception as error:
            usage = type(error).__module__.startswith("typer._click.exceptions")
            exit_code = _boundary_report(arguments, internal=not usage)
            if standalone_mode:
                raise SystemExit(exit_code) from None
            return exit_code
        if standalone_mode:
            raise SystemExit(result if isinstance(result, int) else 0)
        return result


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"attest {_PACKAGE_VERSION}")
        raise typer.Exit()


app = typer.Typer(
    name="attest",
    cls=BoundaryGroup,
    help="Create, sign, store, verify, and gate AI-authorship attestations.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    suggest_commands=False,
)
config_app = typer.Typer(
    name="config",
    help="Inspect resolved configuration.",
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)
app.add_typer(config_app, name="config")

ConfigOption = Annotated[
    Path | None, typer.Option("--config", help="Use exactly this config file.")
]
JsonOption = Annotated[bool, typer.Option("--json", help="Emit one machine-readable report.")]
NoColorOption = Annotated[bool, typer.Option("--no-color", help="Disable terminal colour.")]
RepositoryOption = Annotated[Path | None, typer.Option("--repository", help="Git repository path.")]
BackendOption = Annotated[
    str | None,
    typer.Option("--git-backend", help="Git backend: auto, pygit2, or subprocess."),
]
InputOption = Annotated[Path, typer.Option("--input", help="Input artifact path.")]
OutputOption = Annotated[Path, typer.Option("--output", help="Output artifact path.")]
OverwriteOption = Annotated[bool, typer.Option("--overwrite", help="Replace a regular file.")]
BaseOption = Annotated[str | None, typer.Option("--base", help="Full base commit OID.")]
HeadOption = Annotated[str | None, typer.Option("--head", help="Full head commit OID.")]
TargetOption = Annotated[str | None, typer.Option("--target-branch", help="Target branch name.")]
IdentityOption = Annotated[str | None, typer.Option("--identity", help="Required signer identity.")]
IssuerOption = Annotated[str | None, typer.Option("--issuer", help="Required certificate issuer.")]
VerifyEnvironmentOption = Annotated[
    str | None,
    typer.Option("--verify-environment", help="Verification service environment."),
]
OfflineOption = Annotated[
    bool | None,
    typer.Option("--offline/--online", help="Disable or allow trust refresh."),
]
TrustOption = Annotated[
    Path | None,
    typer.Option("--trust-config-file", help="Supplied offline trust configuration."),
]
PolicyOption = Annotated[Path | None, typer.Option("--policy", help="Policy file path.")]


def _dispatch(command: str, values: Mapping[str, object]) -> None:
    from attest_cli.commands import execute

    raise typer.Exit(execute(command, values))


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Dispatch the selected attest operation."""


@app.command("init")
def init_command(
    checkout_ref: Annotated[str, typer.Option("--checkout-ref")],
    action_ref: Annotated[str, typer.Option("--action-ref")],
    repository: Annotated[Path, typer.Option("--repository")] = Path(),
    github_repository: Annotated[str | None, typer.Option("--github-repository")] = None,
    default_branch: Annotated[str | None, typer.Option("--default-branch")] = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Create config, policy, and a secure GitHub workflow."""
    _dispatch("init", locals())


@app.command("collect")
def collect_command(
    output: OutputOption,
    repository: RepositoryOption = None,
    overwrite: OverwriteOption = False,
    claim: Annotated[list[str] | None, typer.Option("--claim")] = None,
    base: BaseOption = None,
    head: HeadOption = None,
    target_branch: TargetOption = None,
    github_repository: Annotated[str | None, typer.Option("--github-repository")] = None,
    pr: Annotated[int | None, typer.Option("--pr")] = None,
    github_event: Annotated[Path | None, typer.Option("--github-event")] = None,
    git_backend: BackendOption = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Collect one exact ChangeSet and its evidence."""
    _dispatch("collect", locals())


@app.command("build")
def build_command(
    input_path: InputOption,
    output: OutputOption,
    overwrite: OverwriteOption = False,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Build a canonical Statement from a Collection Artifact."""
    _dispatch("build", locals())


@app.command("sign")
def sign_command(
    input_path: InputOption,
    output: OutputOption,
    overwrite: OverwriteOption = False,
    signing_environment: Annotated[str | None, typer.Option("--signing-environment")] = None,
    signing_timeout_seconds: Annotated[
        int | None, typer.Option("--signing-timeout-seconds")
    ] = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Sign a Statement with ambient keyless Sigstore identity."""
    _dispatch("sign", locals())


@app.command("push")
def push_command(
    input_path: InputOption,
    change_set_digest: Annotated[str, typer.Option("--change-set-digest")],
    repository: RepositoryOption = None,
    git_backend: BackendOption = None,
    store_backend: Annotated[str | None, typer.Option("--store-backend")] = None,
    store_directory: Annotated[Path | None, typer.Option("--store-directory")] = None,
    fallback_directory: Annotated[Path | None, typer.Option("--fallback-directory")] = None,
    git_remote: Annotated[str | None, typer.Option("--git-remote")] = None,
    git_timeout_seconds: Annotated[int | None, typer.Option("--git-timeout-seconds")] = None,
    oci_repository: Annotated[str | None, typer.Option("--oci-repository")] = None,
    oci_subject_media_type: Annotated[str | None, typer.Option("--oci-subject-media-type")] = None,
    oci_subject_digest: Annotated[str | None, typer.Option("--oci-subject-digest")] = None,
    oci_subject_size: Annotated[int | None, typer.Option("--oci-subject-size")] = None,
    oci_staging_directory: Annotated[Path | None, typer.Option("--oci-staging-directory")] = None,
    oci_insecure: Annotated[bool | None, typer.Option("--oci-insecure")] = None,
    oci_tls_verify: Annotated[bool | None, typer.Option("--oci-tls-verify")] = None,
    oci_timeout_seconds: Annotated[int | None, typer.Option("--oci-timeout-seconds")] = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Store exact Bundle bytes under a ChangeSet Digest."""
    _dispatch("push", locals())


@app.command("verify")
def verify_command(
    input_path: InputOption,
    repository: RepositoryOption = None,
    base: BaseOption = None,
    head: HeadOption = None,
    identity: IdentityOption = None,
    issuer: IssuerOption = None,
    verify_environment: VerifyEnvironmentOption = None,
    offline: OfflineOption = None,
    trust_config_file: TrustOption = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Verify a Bundle against mandatory identity and issuer."""
    _dispatch("verify", locals())


@app.command("gate")
def gate_command(
    input_path: InputOption,
    repository: Annotated[Path, typer.Option("--repository")],
    base: Annotated[str, typer.Option("--base")],
    head: Annotated[str, typer.Option("--head")],
    target_branch: Annotated[str, typer.Option("--target-branch")],
    policy: PolicyOption = None,
    git_backend: BackendOption = None,
    identity: IdentityOption = None,
    issuer: IssuerOption = None,
    verify_environment: VerifyEnvironmentOption = None,
    offline: OfflineOption = None,
    trust_config_file: TrustOption = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Verify a Bundle and evaluate policy."""
    _dispatch("gate", locals())


@app.command("run")
def run_command(
    output: OutputOption,
    repository: RepositoryOption = None,
    overwrite: OverwriteOption = False,
    work_directory: Annotated[Path | None, typer.Option("--work-directory")] = None,
    policy: PolicyOption = None,
    claim: Annotated[list[str] | None, typer.Option("--claim")] = None,
    base: BaseOption = None,
    head: HeadOption = None,
    target_branch: TargetOption = None,
    github_repository: Annotated[str | None, typer.Option("--github-repository")] = None,
    pr: Annotated[int | None, typer.Option("--pr")] = None,
    github_event: Annotated[Path | None, typer.Option("--github-event")] = None,
    git_backend: BackendOption = None,
    signing_environment: Annotated[str | None, typer.Option("--signing-environment")] = None,
    signing_timeout_seconds: Annotated[
        int | None, typer.Option("--signing-timeout-seconds")
    ] = None,
    identity: IdentityOption = None,
    issuer: IssuerOption = None,
    verify_environment: VerifyEnvironmentOption = None,
    offline: OfflineOption = None,
    trust_config_file: TrustOption = None,
    store_backend: Annotated[str | None, typer.Option("--store-backend")] = None,
    store_directory: Annotated[Path | None, typer.Option("--store-directory")] = None,
    fallback_directory: Annotated[Path | None, typer.Option("--fallback-directory")] = None,
    git_remote: Annotated[str | None, typer.Option("--git-remote")] = None,
    git_timeout_seconds: Annotated[int | None, typer.Option("--git-timeout-seconds")] = None,
    oci_repository: Annotated[str | None, typer.Option("--oci-repository")] = None,
    oci_subject_media_type: Annotated[str | None, typer.Option("--oci-subject-media-type")] = None,
    oci_subject_digest: Annotated[str | None, typer.Option("--oci-subject-digest")] = None,
    oci_subject_size: Annotated[int | None, typer.Option("--oci-subject-size")] = None,
    oci_staging_directory: Annotated[Path | None, typer.Option("--oci-staging-directory")] = None,
    oci_insecure: Annotated[bool | None, typer.Option("--oci-insecure")] = None,
    oci_tls_verify: Annotated[bool | None, typer.Option("--oci-tls-verify")] = None,
    oci_timeout_seconds: Annotated[int | None, typer.Option("--oci-timeout-seconds")] = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Execute collect, build, sign, push, verify, and gate in order."""
    _dispatch("run", locals())


@app.command("inspect")
def inspect_command(
    input_path: InputOption,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Parse a Bundle without verifying its identity or signature."""
    _dispatch("inspect", locals())


@config_app.command("show")
def config_show_command(
    resolved: Annotated[bool, typer.Option("--resolved")],
    repository: RepositoryOption = None,
    git_backend: BackendOption = None,
    github_event: Annotated[Path | None, typer.Option("--github-event")] = None,
    signing_environment: Annotated[str | None, typer.Option("--signing-environment")] = None,
    signing_timeout_seconds: Annotated[
        int | None, typer.Option("--signing-timeout-seconds")
    ] = None,
    identity: IdentityOption = None,
    issuer: IssuerOption = None,
    verify_environment: VerifyEnvironmentOption = None,
    offline: OfflineOption = None,
    trust_config_file: TrustOption = None,
    policy: PolicyOption = None,
    store_backend: Annotated[str | None, typer.Option("--store-backend")] = None,
    store_directory: Annotated[Path | None, typer.Option("--store-directory")] = None,
    fallback_directory: Annotated[Path | None, typer.Option("--fallback-directory")] = None,
    git_remote: Annotated[str | None, typer.Option("--git-remote")] = None,
    git_timeout_seconds: Annotated[int | None, typer.Option("--git-timeout-seconds")] = None,
    oci_repository: Annotated[str | None, typer.Option("--oci-repository")] = None,
    oci_subject_media_type: Annotated[str | None, typer.Option("--oci-subject-media-type")] = None,
    oci_subject_digest: Annotated[str | None, typer.Option("--oci-subject-digest")] = None,
    oci_subject_size: Annotated[int | None, typer.Option("--oci-subject-size")] = None,
    oci_staging_directory: Annotated[Path | None, typer.Option("--oci-staging-directory")] = None,
    oci_insecure: Annotated[bool | None, typer.Option("--oci-insecure")] = None,
    oci_tls_verify: Annotated[bool | None, typer.Option("--oci-tls-verify")] = None,
    oci_timeout_seconds: Annotated[int | None, typer.Option("--oci-timeout-seconds")] = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Show resolved non-secret values and provenance."""
    _dispatch("config-show", locals())


@app.command("doctor")
def doctor_command(
    probe_network: Annotated[bool, typer.Option("--probe-network")] = False,
    repository: RepositoryOption = None,
    git_backend: BackendOption = None,
    signing_environment: Annotated[str | None, typer.Option("--signing-environment")] = None,
    verify_environment: VerifyEnvironmentOption = None,
    offline: OfflineOption = None,
    trust_config_file: TrustOption = None,
    policy: PolicyOption = None,
    store_backend: Annotated[str | None, typer.Option("--store-backend")] = None,
    config: ConfigOption = None,
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Diagnose local capabilities; network probes are explicit."""
    _dispatch("doctor", locals())


@app.command("version")
def version_command(
    json_output: JsonOption = False,
    no_color: NoColorOption = False,
) -> None:
    """Show CLI, Python, and immutable build metadata."""
    _dispatch("version", locals())
