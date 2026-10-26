BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 3d40e7401453

CREATE TABLE configuration (
    key VARCHAR(60) NOT NULL, 
    value JSON NOT NULL, 
    PRIMARY KEY (key)
);

CREATE TABLE institutions (
    code VARCHAR(40) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    state VARCHAR(80) NOT NULL, 
    ownership VARCHAR(40) NOT NULL, 
    land_arrangement VARCHAR(40) NOT NULL, 
    approval_year INTEGER NOT NULL, 
    contact_email VARCHAR(200) NOT NULL, 
    address TEXT NOT NULL, 
    fictional BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE INDEX ix_institutions_created_at ON institutions (created_at);

CREATE TABLE mock_bank_records (
    number VARCHAR(100) NOT NULL, 
    fields JSON NOT NULL, 
    available BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (number)
);

CREATE INDEX ix_mock_bank_records_created_at ON mock_bank_records (created_at);

CREATE TABLE regulatory_rules (
    code VARCHAR(60) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE INDEX ix_regulatory_rules_created_at ON regulatory_rules (created_at);

CREATE TABLE roles (
    name VARCHAR(30) NOT NULL, 
    permissions JSON NOT NULL, 
    PRIMARY KEY (name)
);

CREATE TABLE institution_programmes (
    institution_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    level VARCHAR(30) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(institution_id) REFERENCES institutions (id), 
    UNIQUE (institution_id, name, level)
);

CREATE INDEX ix_institution_programmes_created_at ON institution_programmes (created_at);

CREATE INDEX ix_institution_programmes_institution_id ON institution_programmes (institution_id);

CREATE TABLE users (
    email VARCHAR(200) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    password_hash VARCHAR(300) NOT NULL, 
    role VARCHAR(30) NOT NULL, 
    institution_id UUID, 
    clearance_cell VARCHAR(60), 
    active BOOLEAN NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(institution_id) REFERENCES institutions (id), 
    FOREIGN KEY(role) REFERENCES roles (name), 
    UNIQUE (email)
);

CREATE INDEX ix_users_created_at ON users (created_at);

CREATE INDEX ix_users_institution_id ON users (institution_id);

CREATE TABLE audit_logs (
    actor_id UUID, 
    institution_id UUID, 
    entity_id VARCHAR(80) NOT NULL, 
    action VARCHAR(80) NOT NULL, 
    before JSON NOT NULL, 
    after JSON NOT NULL, 
    previous_hash VARCHAR(64) NOT NULL, 
    event_hash VARCHAR(64) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(institution_id) REFERENCES institutions (id)
);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX ix_audit_logs_entity_id ON audit_logs (entity_id);

CREATE INDEX ix_audit_logs_institution_id ON audit_logs (institution_id);

CREATE TABLE auth_sessions (
    user_id UUID NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    csrf_token VARCHAR(100) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (token_hash)
);

CREATE INDEX ix_auth_sessions_created_at ON auth_sessions (created_at);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE rule_versions (
    rule_id UUID NOT NULL, 
    version INTEGER NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    effective_from DATE NOT NULL, 
    effective_to DATE NOT NULL, 
    config JSON NOT NULL, 
    source_reference TEXT NOT NULL, 
    illustrative BOOLEAN NOT NULL, 
    proposed_by UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (effective_to >= effective_from), 
    FOREIGN KEY(proposed_by) REFERENCES users (id), 
    FOREIGN KEY(rule_id) REFERENCES regulatory_rules (id), 
    UNIQUE (rule_id, version)
);

CREATE INDEX ix_rule_versions_created_at ON rule_versions (created_at);

CREATE TABLE rule_change_approvals (
    version_id UUID NOT NULL, 
    approved_by UUID NOT NULL, 
    notes TEXT NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(approved_by) REFERENCES users (id), 
    FOREIGN KEY(version_id) REFERENCES rule_versions (id), 
    UNIQUE (version_id)
);

CREATE INDEX ix_rule_change_approvals_created_at ON rule_change_approvals (created_at);

CREATE TABLE security_deposits (
    institution_id UUID NOT NULL, 
    programme_id UUID NOT NULL, 
    reference VARCHAR(40) NOT NULL, 
    rule_version_id UUID, 
    requirement_snapshot JSON NOT NULL, 
    required_amount NUMERIC(16, 2), 
    regulatory_end_date DATE, 
    renewal_due_date DATE, 
    status VARCHAR(40) NOT NULL, 
    assigned_officer_id UUID, 
    submitted_by UUID NOT NULL, 
    submitted_at TIMESTAMP WITH TIME ZONE, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(assigned_officer_id) REFERENCES users (id), 
    FOREIGN KEY(institution_id) REFERENCES institutions (id), 
    FOREIGN KEY(programme_id) REFERENCES institution_programmes (id), 
    FOREIGN KEY(rule_version_id) REFERENCES rule_versions (id), 
    FOREIGN KEY(submitted_by) REFERENCES users (id), 
    UNIQUE (reference)
);

CREATE INDEX ix_security_deposits_created_at ON security_deposits (created_at);

CREATE INDEX ix_security_deposits_institution_id ON security_deposits (institution_id);

CREATE INDEX ix_security_deposits_status ON security_deposits (status);

CREATE TABLE deposit_instruments (
    deposit_id UUID NOT NULL, 
    instrument_type VARCHAR(30) NOT NULL, 
    bank VARCHAR(150) NOT NULL, 
    branch VARCHAR(150) NOT NULL, 
    number VARCHAR(100) NOT NULL, 
    depositor_name VARCHAR(200) NOT NULL, 
    amount NUMERIC(16, 2) NOT NULL, 
    issue_date DATE NOT NULL, 
    maturity_date DATE NOT NULL, 
    validity_date DATE, 
    lien_details TEXT NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    verification_status VARCHAR(40) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (amount > 0), 
    CHECK (maturity_date > issue_date), 
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id), 
    UNIQUE (bank, number)
);

CREATE INDEX ix_deposit_instruments_created_at ON deposit_instruments (created_at);

CREATE INDEX ix_deposit_instruments_deposit_id ON deposit_instruments (deposit_id);

CREATE INDEX ix_deposit_instruments_maturity_date ON deposit_instruments (maturity_date);

CREATE TABLE notifications (
    institution_id UUID NOT NULL, 
    deposit_id UUID NOT NULL, 
    dedupe_key VARCHAR(200) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    body TEXT NOT NULL, 
    email_status VARCHAR(40) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id), 
    FOREIGN KEY(institution_id) REFERENCES institutions (id), 
    UNIQUE (dedupe_key)
);

CREATE INDEX ix_notifications_created_at ON notifications (created_at);

CREATE INDEX ix_notifications_institution_id ON notifications (institution_id);

CREATE TABLE release_requests (
    deposit_id UUID NOT NULL, 
    requested_by UUID NOT NULL, 
    kind VARCHAR(30) NOT NULL, 
    reason TEXT NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    workflow_snapshot JSON NOT NULL, 
    decision_notes TEXT NOT NULL, 
    authorised_by UUID, 
    completion_reference VARCHAR(150) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(authorised_by) REFERENCES users (id), 
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id), 
    FOREIGN KEY(requested_by) REFERENCES users (id), 
    UNIQUE (deposit_id)
);

CREATE INDEX ix_release_requests_created_at ON release_requests (created_at);

CREATE TABLE discrepancy_cases (
    deposit_id UUID NOT NULL, 
    instrument_id UUID, 
    code VARCHAR(100) NOT NULL, 
    severity VARCHAR(20) NOT NULL, 
    description TEXT NOT NULL, 
    fields JSON NOT NULL, 
    evidence_source VARCHAR(150) NOT NULL, 
    next_step TEXT NOT NULL, 
    assigned_officer_id UUID, 
    status VARCHAR(30) NOT NULL, 
    response TEXT NOT NULL, 
    resolution TEXT NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(assigned_officer_id) REFERENCES users (id), 
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id), 
    FOREIGN KEY(instrument_id) REFERENCES deposit_instruments (id), 
    UNIQUE (deposit_id, code)
);

CREATE INDEX ix_discrepancy_cases_created_at ON discrepancy_cases (created_at);

CREATE INDEX ix_discrepancy_cases_deposit_id ON discrepancy_cases (deposit_id);

CREATE TABLE documents (
    deposit_id UUID NOT NULL, 
    instrument_id UUID, 
    filename VARCHAR(200) NOT NULL, 
    content_type VARCHAR(80) NOT NULL, 
    size INTEGER NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    storage_key VARCHAR(200) NOT NULL, 
    category VARCHAR(40) NOT NULL, 
    scan_status VARCHAR(40) NOT NULL, 
    processing_status VARCHAR(40) NOT NULL, 
    processing_error TEXT, 
    uploaded_by UUID NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id), 
    FOREIGN KEY(instrument_id) REFERENCES deposit_instruments (id), 
    FOREIGN KEY(uploaded_by) REFERENCES users (id), 
    UNIQUE (storage_key)
);

CREATE INDEX ix_documents_created_at ON documents (created_at);

CREATE INDEX ix_documents_deposit_id ON documents (deposit_id);

CREATE INDEX ix_documents_sha256 ON documents (sha256);

CREATE TABLE instrument_replacements (
    deposit_id UUID NOT NULL, 
    previous_id UUID NOT NULL, 
    replacement_id UUID NOT NULL, 
    reason TEXT NOT NULL, 
    actor_id UUID NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id), 
    FOREIGN KEY(previous_id) REFERENCES deposit_instruments (id), 
    FOREIGN KEY(replacement_id) REFERENCES deposit_instruments (id), 
    UNIQUE (previous_id), 
    UNIQUE (replacement_id)
);

CREATE INDEX ix_instrument_replacements_created_at ON instrument_replacements (created_at);

CREATE TABLE notification_reads (
    notification_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    PRIMARY KEY (notification_id, user_id), 
    FOREIGN KEY(notification_id) REFERENCES notifications (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE release_clearances (
    release_id UUID NOT NULL, 
    cell VARCHAR(60) NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    notes TEXT NOT NULL, 
    officer_id UUID, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(officer_id) REFERENCES users (id), 
    FOREIGN KEY(release_id) REFERENCES release_requests (id), 
    UNIQUE (release_id, cell)
);

CREATE INDEX ix_release_clearances_created_at ON release_clearances (created_at);

CREATE INDEX ix_release_clearances_release_id ON release_clearances (release_id);

CREATE TABLE verification_requests (
    deposit_id UUID NOT NULL, 
    instrument_id UUID NOT NULL, 
    channel VARCHAR(100) NOT NULL, 
    requested_by UUID NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id), 
    FOREIGN KEY(instrument_id) REFERENCES deposit_instruments (id), 
    FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE INDEX ix_verification_requests_created_at ON verification_requests (created_at);

CREATE INDEX ix_verification_requests_deposit_id ON verification_requests (deposit_id);

CREATE TABLE document_extractions (
    document_id UUID NOT NULL, 
    method VARCHAR(40) NOT NULL, 
    original_text TEXT NOT NULL, 
    fields JSON NOT NULL, 
    confidences JSON NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id), 
    UNIQUE (document_id)
);

CREATE INDEX ix_document_extractions_created_at ON document_extractions (created_at);

CREATE TABLE verification_evidence (
    request_id UUID NOT NULL, 
    document_id UUID, 
    source VARCHAR(200) NOT NULL, 
    reference VARCHAR(150) NOT NULL, 
    finding VARCHAR(30) NOT NULL, 
    observations TEXT NOT NULL, 
    confirmed_fields JSON NOT NULL, 
    simulated BOOLEAN NOT NULL, 
    verified_on DATE NOT NULL, 
    recorded_by UUID NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id), 
    FOREIGN KEY(recorded_by) REFERENCES users (id), 
    FOREIGN KEY(request_id) REFERENCES verification_requests (id), 
    UNIQUE (request_id)
);

CREATE INDEX ix_verification_evidence_created_at ON verification_evidence (created_at);

CREATE TABLE field_corrections (
    extraction_id UUID NOT NULL, 
    field VARCHAR(60) NOT NULL, 
    original_value TEXT NOT NULL, 
    corrected_value TEXT NOT NULL, 
    reason TEXT NOT NULL, 
    actor_id UUID NOT NULL, 
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(extraction_id) REFERENCES document_extractions (id)
);

CREATE INDEX ix_field_corrections_created_at ON field_corrections (created_at);

CREATE INDEX ix_field_corrections_extraction_id ON field_corrections (extraction_id);

INSERT INTO alembic_version (version_num) VALUES ('3d40e7401453') RETURNING alembic_version.version_num;

-- Running upgrade 3d40e7401453 -> audit_append_only

CREATE FUNCTION depositflow_protect_audit() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION depositflow_protect_audit();

UPDATE alembic_version SET version_num='audit_append_only' WHERE alembic_version.version_num = '3d40e7401453';

-- Running upgrade audit_append_only -> extraction_provenance

ALTER TABLE documents ADD COLUMN processing_token VARCHAR(64);

ALTER TABLE documents ADD COLUMN processing_started_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE documents ADD COLUMN processing_attempts INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE documents ADD COLUMN next_attempt_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE document_extractions ADD COLUMN provider VARCHAR(30) DEFAULT 'ocr' NOT NULL;

ALTER TABLE document_extractions ADD COLUMN model_name VARCHAR(150);

ALTER TABLE document_extractions ADD COLUMN model_version VARCHAR(100);

ALTER TABLE document_extractions ADD COLUMN document_sha256 VARCHAR(64);

ALTER TABLE document_extractions ADD COLUMN warnings JSON DEFAULT '[]' NOT NULL;

CREATE TABLE audit_chain_heads (
    entity_id VARCHAR(80) NOT NULL, 
    event_hash VARCHAR(64) NOT NULL, 
    last_created_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (entity_id)
);

INSERT INTO audit_chain_heads(entity_id, event_hash, last_created_at)
        SELECT entity_id, event_hash, created_at FROM (
            SELECT entity_id, event_hash, created_at,
                   ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY created_at DESC, id DESC) AS rank
            FROM audit_logs
        ) latest WHERE rank = 1;

UPDATE document_extractions SET document_sha256 =
        (SELECT sha256 FROM documents WHERE documents.id = document_extractions.document_id);

UPDATE alembic_version SET version_num='extraction_provenance' WHERE alembic_version.version_num = 'audit_append_only';

-- Running upgrade extraction_provenance -> risk_safeguards

ALTER TABLE discrepancy_cases ADD COLUMN resolution_kind VARCHAR(20);

ALTER TABLE discrepancy_cases ADD COLUMN resolved_by UUID;

ALTER TABLE discrepancy_cases ADD COLUMN confirmed_by UUID;

ALTER TABLE discrepancy_cases ADD COLUMN condition_active BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE discrepancy_cases ADD CONSTRAINT fk_discrepancy_resolved_by FOREIGN KEY(resolved_by) REFERENCES users (id);

ALTER TABLE discrepancy_cases ADD CONSTRAINT fk_discrepancy_confirmed_by FOREIGN KEY(confirmed_by) REFERENCES users (id);

ALTER TABLE documents ADD COLUMN forensics JSON DEFAULT '{}' NOT NULL;

UPDATE discrepancy_cases SET resolution_kind = 'officer' WHERE status = 'resolved';

UPDATE alembic_version SET version_num='risk_safeguards' WHERE alembic_version.version_num = 'extraction_provenance';

-- Running upgrade risk_safeguards -> risk_engine

CREATE TABLE risk_weight_versions (
    version INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    weights JSON NOT NULL,
    category_caps JSON NOT NULL,
    thresholds JSON NOT NULL,
    notes TEXT NOT NULL,
    proposed_by UUID NOT NULL,
    approved_by UUID,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(proposed_by) REFERENCES users (id),
    FOREIGN KEY(approved_by) REFERENCES users (id),
    UNIQUE (version)
);

CREATE INDEX ix_risk_weight_versions_created_at ON risk_weight_versions (created_at);

CREATE TABLE risk_assessments (
    deposit_id UUID NOT NULL,
    instrument_id UUID,
    score NUMERIC(4, 1) NOT NULL,
    level VARCHAR(10) NOT NULL,
    signals JSON NOT NULL,
    engine_version VARCHAR(20) NOT NULL,
    weights_version INTEGER NOT NULL,
    inputs_digest VARCHAR(64) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CHECK (score >= 0 AND score <= 100),
    FOREIGN KEY(deposit_id) REFERENCES security_deposits (id),
    FOREIGN KEY(instrument_id) REFERENCES deposit_instruments (id)
);

CREATE INDEX ix_risk_assessments_created_at ON risk_assessments (created_at);

CREATE INDEX ix_risk_assessments_deposit_id ON risk_assessments (deposit_id);

CREATE INDEX ix_risk_assessments_level ON risk_assessments (level);

UPDATE alembic_version SET version_num='risk_engine' WHERE alembic_version.version_num = 'risk_safeguards';

-- Running upgrade risk_engine -> comparison_keys

ALTER TABLE deposit_instruments ADD COLUMN number_key VARCHAR(100);

ALTER TABLE deposit_instruments ADD COLUMN bank_key VARCHAR(150);

ALTER TABLE document_extractions ADD COLUMN text_fingerprint VARCHAR(64);

CREATE INDEX ix_deposit_instruments_number_key ON deposit_instruments (number_key);

CREATE INDEX ix_document_extractions_text_fingerprint ON document_extractions (text_fingerprint);

UPDATE alembic_version SET version_num='comparison_keys' WHERE alembic_version.version_num = 'risk_engine';

-- Running upgrade comparison_keys -> verification_gate

ALTER TABLE security_deposits ADD COLUMN verified_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE security_deposits ADD COLUMN verified_by UUID;

ALTER TABLE security_deposits ADD COLUMN escalated_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE security_deposits ADD COLUMN vigilance_cleared_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE security_deposits ADD COLUMN vigilance_cleared_by UUID;

ALTER TABLE security_deposits ADD CONSTRAINT fk_deposit_verified_by FOREIGN KEY(verified_by) REFERENCES users (id);

ALTER TABLE security_deposits ADD CONSTRAINT fk_deposit_vigilance_cleared_by FOREIGN KEY(vigilance_cleared_by) REFERENCES users (id);

UPDATE alembic_version SET version_num='verification_gate' WHERE alembic_version.version_num = 'comparison_keys';

COMMIT;

