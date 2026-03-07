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

{{TICKET_ROWS}}

INSERT INTO vault_flags (id, flag_name, flag_value, source_manifest) VALUES
    (1, 'production_helpdesk_flag', '{{FLAG_DB_VALUE}}', 'k8s/configmap-init-sql.yaml');
