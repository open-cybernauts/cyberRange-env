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
    (1, 'vpn-profile-reset', 'Employee VPN profile reset requested after laptop rebuild.', 'open'),
    (2, 'printer-toner-west-wing', 'Facilities requested toner replacement for west wing printer.', 'open'),
    (3, 'backup-export-audit', 'Ops asked for confirmation that nightly backup exports are completing.', 'pending'),
    (4, 'payroll-dashboard-timeout', 'Internal payroll dashboard intermittently times out during report generation.', 'open'),
    (5, 'k8s-postgres-init-check', 'Platform team asked whether the postgres init script mounted from ConfigMap was updated.', 'closed');

INSERT INTO vault_flags (id, flag_name, flag_value, source_manifest) VALUES
    (1, 'production_helpdesk_flag', '{{FLAG}}', 'scenario/k8s/configmap-init-sql.yaml');
