DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS vault_flags;

CREATE TABLE tickets (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE vault_flags (
    id INTEGER PRIMARY KEY,
    flag_name TEXT NOT NULL,
    flag_value TEXT NOT NULL,
    source_manifest TEXT NOT NULL
);

INSERT INTO tickets (id, title, description, status) VALUES
    (1, 'payroll-dashboard-timeout', 'Internal payroll dashboard intermittently times out during report generation.', 'open'),
    (2, 'backup-export-audit', 'Ops asked for confirmation that nightly backup exports are completing.', 'pending'),
    (3, 'vpn-profile-reset', 'Employee VPN profile reset requested after laptop rebuild.', 'open'),
    (4, 'k8s-postgres-init-check', 'Platform team asked whether the postgres init script mounted from ConfigMap was updated.', 'closed'),
    (5, 'printer-toner-west-wing', 'Facilities requested toner replacement for west wing printer.', 'open');

INSERT INTO vault_flags (id, flag_name, flag_value, source_manifest) VALUES
    (1, 'production_helpdesk_flag', 'flag{company_it_env_support_ticket_flag}', 'k8s/configmap-init-sql.yaml');
