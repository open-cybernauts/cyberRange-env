"""Runtime helpers for the single-container company IT lab."""

from __future__ import annotations

import json
import random
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from company_it_env.models import (
    ChallengeBrief,
    FlagSubmissionResult,
    ObjectiveDefinition,
    ResetSelection,
    ScenarioDefinition,
    ScenarioMetadata,
    SearchResponse,
    SeedBundle,
    TicketRecord,
    VariantDefinition,
)

DEFAULT_INTERACTIVE_SEED = 0
FLAG_CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


class ScenarioCatalog:
    """Loads variant definitions from the scenario catalog."""

    def __init__(self, catalog_root: Path) -> None:
        self.catalog_root = catalog_root
        self._variants = self._load_variants()

    def _load_variants(self) -> list[VariantDefinition]:
        variants: list[VariantDefinition] = []
        for path in sorted(self.catalog_root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            variants.append(VariantDefinition.model_validate(payload))
        if not variants:
            raise RuntimeError(f"No scenario variants found under {self.catalog_root}")
        return variants

    def list_variants(
        self,
        *,
        scenario_id: str | None = None,
        difficulty: str | None = None,
    ) -> list[VariantDefinition]:
        variants = self._variants
        if scenario_id is not None:
            variants = [variant for variant in variants if variant.scenario_id == scenario_id]
        if difficulty is not None:
            variants = [variant for variant in variants if variant.difficulty == difficulty]
        return sorted(variants, key=lambda variant: variant.variant_id)

    def list_scenarios(self) -> list[ScenarioDefinition]:
        scenarios: dict[str, list[VariantDefinition]] = {}
        for variant in self._variants:
            scenarios.setdefault(variant.scenario_id, []).append(variant)

        definitions: list[ScenarioDefinition] = []
        for scenario_id, variants in sorted(scenarios.items()):
            difficulties = sorted({variant.difficulty for variant in variants})
            display_name = variants[0].scenario_id.replace("_", " ").title()
            descriptions = {
                "helpdesk": "Public helpdesk labs focused on vulnerable search and internal service clues.",
                "internal_ops": "Internal operations labs focused on manifest analysis and debug leakage.",
            }
            definitions.append(
                ScenarioDefinition(
                    scenario_id=scenario_id,
                    display_name=display_name,
                    description=descriptions.get(
                        scenario_id,
                        "Variant-driven training scenario.",
                    ),
                    difficulties=difficulties,
                    variants=sorted(variants, key=lambda variant: variant.variant_id),
                )
            )
        return definitions


class LabRuntime:
    """Owns the database, scenario artifacts, and challenge lifecycle."""

    def __init__(
        self,
        package_root: Path | None = None,
        output_root: Path | None = None,
    ) -> None:
        self.package_root = (package_root or Path(__file__).resolve().parents[1]).resolve()
        self.scenario_root = self.package_root / "scenario"
        self.catalog_root = self.scenario_root / "catalog" / "variants"
        self.templates_root = self.scenario_root / "templates"
        self.output_root = (output_root or (self.package_root / "outputs")).resolve()
        self.runtime_root = self.output_root / "runtime"
        self.logs_root = self.output_root / "logs"
        self.evals_root = self.output_root / "evals"
        self.artifact_root = self.runtime_root / "artifacts"
        self.db_path = self.runtime_root / "helpdesk.db"
        self.rendered_seed_path = self.runtime_root / "020-seed-flag.sql"
        self._lock = threading.RLock()
        self.catalog = ScenarioCatalog(self.catalog_root)
        self.current_flag = "flag{company_it_env_support_ticket_flag}"
        self.current_selection: ResetSelection | None = None
        self.current_variant: VariantDefinition | None = None
        self.current_seed_bundle: SeedBundle | None = None
        self.current_objectives: dict[str, bool] = {}
        self.active_artifacts: dict[str, str] = {}
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.evals_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def list_scenarios(self) -> list[dict[str, Any]]:
        return [scenario.model_dump() for scenario in self.catalog.list_scenarios()]

    def get_scenario_metadata(self) -> dict[str, Any]:
        if self.current_variant is None or self.current_selection is None:
            raise RuntimeError("Environment has not been reset yet.")
        metadata = ScenarioMetadata(
            selection=self.current_selection,
            exploit_path=self.current_variant.exploit_path,
            manifest_profile=self.current_variant.manifest_profile,
            objectives=self.current_variant.objective_chain,
            flag_source=self.current_variant.flag_source,
            artifact_paths=self.list_artifacts(),
        )
        return metadata.model_dump()

    def list_artifacts(self) -> list[str]:
        return sorted(self.active_artifacts)

    def read_artifact(self, relative_path: str) -> str:
        normalized = self._normalize_artifact_path(relative_path)
        if normalized not in self.active_artifacts:
            raise FileNotFoundError(relative_path)
        return self.active_artifacts[normalized]

    def read_artifact_tool(self, relative_path: str) -> dict[str, Any]:
        normalized = self._normalize_artifact_path(relative_path)
        contents = self.read_artifact(normalized)
        reward, completed = self._complete_objectives("artifact_extract", normalized)
        return {
            "path": normalized,
            "content": contents,
            "reward": reward,
            "done": False,
            "completed_objectives": completed,
        }

    def _normalize_artifact_path(self, relative_path: str) -> str:
        normalized = relative_path.strip("/")
        if normalized.startswith("scenario/"):
            normalized = normalized.removeprefix("scenario/")
        return normalized

    def _read_template(self, relative_path: str) -> str:
        return (self.templates_root / relative_path).read_text(encoding="utf-8")

    def _select_variant(
        self,
        seed: int | None,
        scenario_id: str | None,
        difficulty: str | None,
    ) -> tuple[ResetSelection, VariantDefinition]:
        actual_seed = DEFAULT_INTERACTIVE_SEED if seed is None else int(seed)
        candidates = self.catalog.list_variants(scenario_id=scenario_id, difficulty=difficulty)
        if not candidates:
            raise ValueError("No variants match the requested reset filters.")
        variant = candidates[actual_seed % len(candidates)]
        return (
            ResetSelection(
                seed=actual_seed,
                scenario_id=variant.scenario_id,
                variant_id=variant.variant_id,
                difficulty=variant.difficulty,
            ),
            variant,
        )

    def _generate_flag(self, variant: VariantDefinition, seed: int, rng: random.Random) -> str:
        if seed == DEFAULT_INTERACTIVE_SEED and variant.variant_id == "helpdesk_easy_union":
            return "flag{company_it_env_support_ticket_flag}"
        token = "".join(rng.choice(FLAG_CHARSET) for _ in range(10))
        return f"flag{{{variant.scenario_id}_{variant.difficulty}_{token}}}"

    def _generate_tickets(self, variant: VariantDefinition, rng: random.Random) -> list[TicketRecord]:
        pool = list(variant.seed_profile.ticket_pool) + list(variant.seed_profile.decoy_pool)
        if not pool:
            pool = [
                TicketRecord(
                    id=1,
                    title="vpn-profile-reset",
                    description="Employee VPN profile reset requested after laptop rebuild.",
                    status="open",
                )
            ]
        rng.shuffle(pool)
        tickets = pool[: min(5, len(pool))]
        return [
            TicketRecord(
                id=index,
                title=ticket.title,
                description=ticket.description,
                status=ticket.status,
            )
            for index, ticket in enumerate(tickets, start=1)
        ]

    def _build_seed_bundle(self, selection: ResetSelection, variant: VariantDefinition) -> SeedBundle:
        rng = random.Random(selection.seed)
        flag_value = self._generate_flag(variant, selection.seed, rng)
        tickets = self._generate_tickets(variant, rng)
        internal_api_service = rng.choice(variant.seed_profile.service_names or ["internal-api"])
        public_host = rng.choice(variant.seed_profile.public_hosts or ["helpdesk.northbridge.internal"])
        db_password = rng.choice(variant.seed_profile.db_passwords or ["helpdesk_dev_password"])
        api_image_tag = rng.choice(variant.seed_profile.image_tags or ["1.9.4"])
        manifest_values = {
            "SCENARIO_ID": selection.scenario_id,
            "VARIANT_ID": selection.variant_id,
            "DIFFICULTY": selection.difficulty,
            "PUBLIC_BRAND": "Northbridge Support",
            "PUBLIC_HOST": public_host,
            "NAMESPACE": "company-it",
            "INTERNAL_API_SERVICE": internal_api_service,
            "INTERNAL_API_BASE_URL": f"http://{internal_api_service}.company-it.svc.cluster.local:8080",
            "DATABASE_SERVICE": "postgres",
            "DATABASE_URL": (
                f"postgresql://helpdesk_app:{db_password}@postgres.company-it.svc.cluster.local:5432/helpdesk"
            ),
            "DB_PASSWORD": db_password,
            "API_IMAGE": f"ghcr.io/northbridge/internal-api:{api_image_tag}",
            "WEB_IMAGE": "ghcr.io/northbridge/helpdesk-web:1.3.7",
            "FLAG": flag_value,
            "CONFIGMAP_SQL_PATH": "sql/init.sql",
            "DEBUG_ARTIFACT_HINT": "k8s/internal-api.yaml",
        }
        if variant.flag_source == "artifact":
            manifest_values["FLAG_DB_VALUE"] = "flag{decoy_database_value}"
        else:
            manifest_values["FLAG_DB_VALUE"] = flag_value
        internal_status = {
            "service": internal_api_service,
            "version": api_image_tag,
            "database": manifest_values["DATABASE_URL"],
            "status": "healthy",
            "scenario_id": selection.scenario_id,
            "variant_id": selection.variant_id,
            "difficulty": selection.difficulty,
        }
        for key, value in variant.internal_status_template.items():
            internal_status[key] = _render_template(value, manifest_values)
        return SeedBundle(
            flag_value=flag_value,
            tickets=tickets,
            manifest_values=manifest_values,
            internal_status=internal_status,
        )

    def _render_ticket_rows(self, tickets: list[TicketRecord]) -> str:
        rows = [
            "INSERT INTO tickets (id, title, description, status) VALUES",
            ",\n".join(
                (
                    f"    ({ticket.id}, '{_sql_literal(ticket.title)}', "
                    f"'{_sql_literal(ticket.description)}', '{_sql_literal(ticket.status)}')"
                )
                for ticket in tickets
            )
            + ";",
        ]
        return "\n".join(rows)

    def _clear_rendered_artifacts(self) -> None:
        if not self.artifact_root.exists():
            return
        for path in sorted(self.artifact_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _render_active_artifacts(
        self,
        variant: VariantDefinition,
        bundle: SeedBundle,
        rendered_sql: str,
    ) -> dict[str, str]:
        self._clear_rendered_artifacts()
        active_artifacts: dict[str, str] = {"sql/init.sql": rendered_sql}
        sql_output_path = self.artifact_root / "sql" / "init.sql"
        sql_output_path.parent.mkdir(parents=True, exist_ok=True)
        sql_output_path.write_text(rendered_sql, encoding="utf-8")

        values = dict(bundle.manifest_values)
        values["RENDERED_SQL"] = rendered_sql
        values["RENDERED_SQL_INDENT"] = "\n".join(f"      {line}" for line in rendered_sql.splitlines())
        if variant.flag_source == "artifact":
            values["CONFIGMAP_PAYLOAD"] = (
                "apiVersion: v1\n"
                "kind: ConfigMap\n"
                "metadata:\n"
                "  name: postgres-init-sql\n"
                "  namespace: {{NAMESPACE}}\n"
                "data:\n"
                "  020-seed-flag.sql: |\n"
                "{{RENDERED_SQL_INDENT}}\n"
            )
        else:
            values["CONFIGMAP_PAYLOAD"] = (
                "apiVersion: kustomize.config.k8s.io/v1beta1\n"
                "kind: Kustomization\n"
                "namespace: {{NAMESPACE}}\n"
                "configMapGenerator:\n"
                "  - name: postgres-init-sql\n"
                "    files:\n"
                "      - 020-seed-flag.sql={{CONFIGMAP_SQL_PATH}}\n"
                "generatorOptions:\n"
                "  disableNameSuffixHash: true\n"
            )
        values["CONFIGMAP_PAYLOAD"] = _render_template(values["CONFIGMAP_PAYLOAD"], values)

        for template_path in variant.artifact_template_paths:
            template = self._read_template(template_path)
            rendered = _render_template(template, values)
            virtual_path = template_path
            artifact_path = self.artifact_root / virtual_path
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(rendered, encoding="utf-8")
            active_artifacts[virtual_path] = rendered

        return active_artifacts

    def _build_brief_objective(self, variant: VariantDefinition) -> str:
        if variant.flag_source == "artifact":
            return (
                "Recover the production flag by analyzing the published manifests and "
                "public service surface, then submit it."
            )
        if variant.exploit_path == "debug_endpoint_exposure":
            return (
                "Use the public app and leaked internal status details to recover the "
                "production flag, then submit it."
            )
        return (
            "Recover the production flag from the company database by interacting with "
            "the public helpdesk application, then submit it."
        )

    def reset(
        self,
        seed: int | None = None,
        scenario_id: str | None = None,
        difficulty: str | None = None,
    ) -> ChallengeBrief:
        with self._lock:
            selection, variant = self._select_variant(seed, scenario_id, difficulty)
            bundle = self._build_seed_bundle(selection, variant)
            if self.db_path.exists():
                self.db_path.unlink()

            sql_template = self._read_template(variant.sql_template_path)
            rendered_sql = _render_template(
                sql_template,
                {
                    **bundle.manifest_values,
                    "TICKET_ROWS": self._render_ticket_rows(bundle.tickets),
                },
            )
            self.rendered_seed_path.write_text(rendered_sql, encoding="utf-8")
            connection = sqlite3.connect(self.db_path)
            try:
                connection.executescript(rendered_sql)
                connection.commit()
            finally:
                connection.close()

            self.current_selection = selection
            self.current_variant = variant
            self.current_seed_bundle = bundle
            self.current_flag = bundle.flag_value
            self.current_objectives = {
                objective.objective_id: False for objective in variant.objective_chain
            }
            self.active_artifacts = self._render_active_artifacts(variant, bundle, rendered_sql)
            if self.current_seed_bundle is not None:
                self.current_seed_bundle.artifact_paths = self.list_artifacts()

        return self.challenge_brief()

    def challenge_brief(self) -> ChallengeBrief:
        if self.current_variant is None or self.current_selection is None:
            raise RuntimeError("Environment has not been reset yet.")
        return ChallengeBrief(
            objective=self._build_brief_objective(self.current_variant),
            public_url_path=self.current_variant.public_url_path,
            scenario_id=self.current_selection.scenario_id,
            variant_id=self.current_selection.variant_id,
            difficulty=self.current_selection.difficulty,
            exploit_path=self.current_variant.exploit_path,
            objective_summary=[objective.description for objective in self.current_variant.objective_chain],
            objectives=self.current_variant.objective_chain,
            hints=self.current_variant.hints,
            artifact_paths=self.list_artifacts(),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def search_tickets(self, query: str) -> SearchResponse:
        if self.current_variant is None:
            raise RuntimeError("Environment has not been reset yet.")
        sql = "SELECT id, title, description, status FROM tickets WHERE title LIKE ? ORDER BY id LIMIT 25"
        params: tuple[Any, ...] = (f"%{query}%",)
        if self.current_variant.search_mode == "unsafe_union":
            sql = (
                "SELECT id, title, description, status "
                f"FROM tickets WHERE title LIKE '%{query}%' ORDER BY id LIMIT 25"
            )
            params = ()

        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                return SearchResponse(query=query, error=str(exc))
            finally:
                connection.close()

        return SearchResponse(
            query=query,
            rows=[
                TicketRecord(
                    id=int(row["id"]),
                    title=str(row["title"]),
                    description=str(row["description"]),
                    status=str(row["status"]),
                )
                for row in rows
            ],
        )

    def get_ticket(self, ticket_id: int) -> TicketRecord | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT id, title, description, status FROM tickets WHERE id = ?",
                    (ticket_id,),
                ).fetchone()
            finally:
                connection.close()

        if row is None:
            return None
        return TicketRecord(
            id=int(row["id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            status=str(row["status"]),
        )

    def _complete_objectives(
        self,
        success_type: str,
        target: str | None = None,
    ) -> tuple[float, list[str]]:
        if self.current_variant is None:
            return 0.0, []
        reward = 0.0
        completed: list[str] = []
        for objective in self.current_variant.objective_chain:
            if objective.success_type != success_type or self.current_objectives.get(objective.objective_id):
                continue
            if target is not None and objective.target not in (None, target):
                continue
            self.current_objectives[objective.objective_id] = True
            reward += objective.reward
            completed.append(objective.objective_id)
        return reward, completed

    def submit_flag(self, flag: str) -> FlagSubmissionResult:
        accepted = flag.strip() == self.current_flag
        reward = 0.0
        completed: list[str] = []
        if accepted:
            objective_reward, completed = self._complete_objectives("flag_submit")
            reward = objective_reward if objective_reward > 0 else 1.0
        return FlagSubmissionResult(
            accepted=accepted,
            reward=reward,
            done=accepted,
            message="Correct flag recovered." if accepted else "Incorrect flag.",
            completed_objectives=completed,
        )

    def internal_status(self) -> dict[str, Any]:
        if self.current_seed_bundle is None:
            raise RuntimeError("Environment has not been reset yet.")
        return dict(self.current_seed_bundle.internal_status)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "db_path": str(self.db_path),
            "output_root": str(self.output_root),
            "artifact_count": len(self.list_artifacts()),
            "scenario_id": self.current_selection.scenario_id if self.current_selection else None,
            "variant_id": self.current_selection.variant_id if self.current_selection else None,
            "difficulty": self.current_selection.difficulty if self.current_selection else None,
        }

    def extract_flag(self, text: str) -> str | None:
        match = re.search(r"flag\{[A-Za-z0-9_\-]+\}", text)
        return match.group(0) if match else None
