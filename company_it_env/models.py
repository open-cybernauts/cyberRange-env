"""Shared data models for the company IT lab."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DifficultyLevel = Literal["easy", "medium", "hard"]
ExploitPath = Literal[
    "sqli_union",
    "debug_endpoint_exposure",
    "credential_leak_from_manifest",
]
ObjectiveSuccessType = Literal["flag_submit", "artifact_extract", "endpoint_query", "multi_step"]
SearchMode = Literal["unsafe_union", "safe_like"]
FlagSource = Literal["database", "artifact"]
EpisodeState = Literal["provisioning", "ready", "completed", "terminated", "failed"]
ServiceExposure = Literal["public", "external_only", "cluster_internal"]
ServiceProtocol = Literal["http", "https", "tcp"]
AttackerAccessType = Literal["simulated_shell", "ssh", "web_terminal"]
ControllerMode = Literal["simulated", "http", "provisioner"]
DeploymentRole = Literal["redteam", "target"]
NetworkZone = Literal["attacker", "dmz", "internal"]


class ObjectiveDefinition(BaseModel):
    objective_id: str
    description: str
    success_type: ObjectiveSuccessType
    reward: float = 0.0
    target: str | None = None


class TicketRecord(BaseModel):
    id: int
    title: str
    description: str
    status: str


class VariantSeedProfile(BaseModel):
    ticket_pool: list[TicketRecord] = Field(default_factory=list)
    decoy_pool: list[TicketRecord] = Field(default_factory=list)
    service_names: list[str] = Field(default_factory=list)
    public_hosts: list[str] = Field(default_factory=list)
    image_tags: list[str] = Field(default_factory=list)
    db_passwords: list[str] = Field(default_factory=list)


class VariantDefinition(BaseModel):
    variant_id: str
    scenario_id: str
    display_name: str
    difficulty: DifficultyLevel
    exploit_path: ExploitPath
    manifest_profile: str
    search_mode: SearchMode
    flag_source: FlagSource = "database"
    objective_chain: list[ObjectiveDefinition] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    sql_template_path: str
    artifact_template_paths: list[str] = Field(default_factory=list)
    seed_profile: VariantSeedProfile = Field(default_factory=VariantSeedProfile)
    internal_status_template: dict[str, str] = Field(default_factory=dict)
    public_url_path: str = "/helpdesk"


class ScenarioDefinition(BaseModel):
    scenario_id: str
    display_name: str
    description: str
    difficulties: list[DifficultyLevel] = Field(default_factory=list)
    variants: list[VariantDefinition] = Field(default_factory=list)


class ResetSelection(BaseModel):
    seed: int
    scenario_id: str
    variant_id: str
    difficulty: DifficultyLevel


class ScenarioMetadata(BaseModel):
    selection: ResetSelection
    exploit_path: ExploitPath
    manifest_profile: str
    objectives: list[ObjectiveDefinition] = Field(default_factory=list)
    flag_source: FlagSource
    artifact_paths: list[str] = Field(default_factory=list)


class SeedBundle(BaseModel):
    flag_value: str
    tickets: list[TicketRecord] = Field(default_factory=list)
    manifest_values: dict[str, str] = Field(default_factory=dict)
    artifact_paths: list[str] = Field(default_factory=list)
    internal_status: dict[str, str] = Field(default_factory=dict)


class ChallengeBrief(BaseModel):
    company_name: str = "Northbridge Support"
    objective: str
    public_url_path: str | None = None
    scenario_id: str | None = None
    variant_id: str | None = None
    difficulty: DifficultyLevel | None = None
    exploit_path: ExploitPath | None = None
    objective_summary: list[str] = Field(default_factory=list)
    objectives: list[ObjectiveDefinition] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    attack_surface_summary: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    rows: list[TicketRecord] = Field(default_factory=list)
    error: str | None = None


class FlagSubmission(BaseModel):
    flag: str


class EpisodeFlagSubmission(FlagSubmission):
    episode_id: str


class EpisodeCreateRequest(BaseModel):
    seed: int | None = None
    scenario_id: str | None = None
    difficulty: DifficultyLevel | None = None
    controller_episode_id: str | None = None


class FlagSubmissionResult(BaseModel):
    accepted: bool
    reward: float
    done: bool
    message: str
    completed_objectives: list[str] = Field(default_factory=list)


class RemoteServiceEndpoint(BaseModel):
    service_id: str
    display_name: str
    host: str
    port: int
    protocol: ServiceProtocol = "http"
    exposure: ServiceExposure = "public"
    entrypoint_path: str | None = None
    notes: str | None = None


class AttackerAccess(BaseModel):
    connection_type: AttackerAccessType = "simulated_shell"
    workspace_label: str
    host: str
    username: str = "operator"
    port: int | None = None
    bootstrap_commands: list[str] = Field(default_factory=list)
    reachable_hosts: list[str] = Field(default_factory=list)
    target_services: list[RemoteServiceEndpoint] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class EpisodeStatus(BaseModel):
    controller_episode_id: str
    state: EpisodeState = "ready"
    scenario_id: str
    variant_id: str
    difficulty: DifficultyLevel
    namespace: str
    attacker_ready: bool = True
    target_services: list[RemoteServiceEndpoint] = Field(default_factory=list)
    active_flag_source: FlagSource | None = None


class EpisodeProvisioningResult(BaseModel):
    controller_episode_id: str
    brief: ChallengeBrief
    attacker_access: AttackerAccess
    status: EpisodeStatus


class ControllerHealth(BaseModel):
    controller_mode: ControllerMode
    status: str = "ok"
    active_episodes: int = 0
    remote_url: str | None = None


class RemoteDeploymentSpec(BaseModel):
    deployment_id: str
    role: DeploymentRole
    namespace: str
    image: str
    network_zone: NetworkZone
    exposed_services: list[RemoteServiceEndpoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RemoteClusterLayout(BaseModel):
    namespace: str
    redteam: RemoteDeploymentSpec
    targets: list[RemoteDeploymentSpec] = Field(default_factory=list)


class ProvisioningRequest(BaseModel):
    controller_episode_id: str
    selection: ResetSelection
    variant: VariantDefinition
    seed_bundle: SeedBundle
    layout: RemoteClusterLayout
    rendered_artifacts: dict[str, str] = Field(default_factory=dict)


class ProvisioningResult(BaseModel):
    attacker_access: AttackerAccess
    status: EpisodeStatus
