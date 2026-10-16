CREATE TABLE users (
    id uuid PRIMARY KEY,
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_normalized CHECK (email = lower(email))
);

CREATE TABLE refresh_sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id uuid NOT NULL,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    rotated_at timestamptz,
    revoked_at timestamptz,
    replaced_by uuid REFERENCES refresh_sessions(id),
    CONSTRAINT refresh_expiry_after_create CHECK (expires_at > created_at)
);
CREATE INDEX refresh_sessions_user_idx ON refresh_sessions(user_id);
CREATE INDEX refresh_sessions_family_idx ON refresh_sessions(family_id);

CREATE TABLE calculations (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    input_snapshot jsonb NOT NULL,
    result_snapshot jsonb NOT NULL,
    total_emissions_kg_co2 numeric(18,4) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX calculations_user_created_idx ON calculations(user_id, created_at DESC, id DESC);
