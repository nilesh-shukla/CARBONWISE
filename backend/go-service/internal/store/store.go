package store

import (
	"context"
	"database/sql"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

//go:embed migrations/*.sql
var migrations embed.FS

type Store struct{ DB *sql.DB }

func New(db *sql.DB) *Store { return &Store{DB: db} }
func Migrate(ctx context.Context, db *sql.DB) error {
	conn, e := db.Conn(ctx)
	if e != nil {
		return e
	}
	defer conn.Close()
	if _, e = conn.ExecContext(ctx, `SELECT pg_advisory_lock(728436219005)`); e != nil {
		return e
	}
	defer func() {
		unlockCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_, _ = conn.ExecContext(unlockCtx, `SELECT pg_advisory_unlock(728436219005)`)
	}()
	if _, e := conn.ExecContext(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())`); e != nil {
		return e
	}
	files, e := fs.Glob(migrations, "migrations/*.sql")
	if e != nil {
		return e
	}
	sort.Strings(files)
	for _, name := range files {
		version := strings.TrimSuffix(strings.TrimPrefix(name, "migrations/"), ".sql")
		var exists bool
		if e = conn.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version=$1)`, version).Scan(&exists); e != nil {
			return e
		}
		if exists {
			continue
		}
		content, e := migrations.ReadFile(name)
		if e != nil {
			return e
		}
		tx, e := conn.BeginTx(ctx, nil)
		if e != nil {
			return e
		}
		for _, statement := range strings.Split(string(content), ";") {
			if statement = strings.TrimSpace(statement); statement != "" {
				if _, e = tx.ExecContext(ctx, statement); e != nil {
					break
				}
			}
		}
		if e == nil {
			_, e = tx.ExecContext(ctx, `INSERT INTO schema_migrations(version) VALUES($1)`, version)
		}
		if e != nil {
			_ = tx.Rollback()
			return fmt.Errorf("apply migration %s: %w", version, e)
		}
		if e = tx.Commit(); e != nil {
			return e
		}
	}
	return nil
}

type User struct {
	ID, Email, PasswordHash string
	CreatedAt               time.Time
}

func (s *Store) CreateUser(ctx context.Context, email, hash string) (User, error) {
	var u User
	e := s.DB.QueryRowContext(ctx, `INSERT INTO users(id,email,password_hash) VALUES($1,$2,$3) RETURNING id::text,email,password_hash,created_at`, uuid.NewString(), email, hash).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.CreatedAt)
	return u, e
}
func (s *Store) CreateUserWithRefresh(ctx context.Context, email, passwordHash, tokenHash, family string, expires time.Time) (User, error) {
	tx, e := s.DB.BeginTx(ctx, nil)
	if e != nil {
		return User{}, e
	}
	defer tx.Rollback()
	var u User
	e = tx.QueryRowContext(ctx, `INSERT INTO users(id,email,password_hash) VALUES($1,$2,$3) RETURNING id::text,email,password_hash,created_at`, uuid.NewString(), email, passwordHash).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.CreatedAt)
	if e != nil {
		return User{}, e
	}
	if _, e = tx.ExecContext(ctx, `INSERT INTO refresh_sessions(id,user_id,family_id,token_hash,expires_at) VALUES($1,$2,$3,$4,$5)`, uuid.NewString(), u.ID, family, tokenHash, expires); e != nil {
		return User{}, e
	}
	if e = tx.Commit(); e != nil {
		return User{}, e
	}
	return u, nil
}
func (s *Store) UserByEmail(ctx context.Context, email string) (User, error) {
	var u User
	e := s.DB.QueryRowContext(ctx, `SELECT id::text,email,password_hash,created_at FROM users WHERE email=$1`, email).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.CreatedAt)
	return u, e
}
func (s *Store) UserByID(ctx context.Context, id string) (User, error) {
	var u User
	e := s.DB.QueryRowContext(ctx, `SELECT id::text,email,password_hash,created_at FROM users WHERE id=$1`, id).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.CreatedAt)
	return u, e
}
func (s *Store) CreateRefresh(ctx context.Context, userID, tokenHash, family string, expires time.Time) error {
	_, e := s.DB.ExecContext(ctx, `INSERT INTO refresh_sessions(id,user_id,family_id,token_hash,expires_at) VALUES($1,$2,$3,$4,$5)`, uuid.NewString(), userID, family, tokenHash, expires)
	return e
}

var ErrRefreshInvalid = errors.New("invalid refresh session")

// Rotate locks the presented session. Reuse of any rotated/revoked token revokes its family.
func (s *Store) Rotate(ctx context.Context, tokenHash, newHash string, expires time.Time) (string, error) {
	tx, e := s.DB.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if e != nil {
		return "", e
	}
	defer tx.Rollback()
	var sessionID, userID, family string
	var oldExpiry time.Time
	var rotated, revoked sql.NullTime
	e = tx.QueryRowContext(ctx, `SELECT id::text,user_id::text,family_id::text,expires_at,rotated_at,revoked_at FROM refresh_sessions WHERE token_hash=$1 FOR UPDATE`, tokenHash).Scan(&sessionID, &userID, &family, &oldExpiry, &rotated, &revoked)
	if errors.Is(e, sql.ErrNoRows) {
		return "", ErrRefreshInvalid
	}
	if e != nil {
		return "", e
	}
	if rotated.Valid || revoked.Valid || time.Now().After(oldExpiry) {
		if _, e = tx.ExecContext(ctx, `UPDATE refresh_sessions SET revoked_at=COALESCE(revoked_at,now()) WHERE family_id=$1`, family); e != nil {
			return "", e
		}
		if e = tx.Commit(); e != nil {
			return "", e
		}
		return "", ErrRefreshInvalid
	}
	newID := uuid.NewString()
	if _, e = tx.ExecContext(ctx, `INSERT INTO refresh_sessions(id,user_id,family_id,token_hash,expires_at) VALUES($1,$2,$3,$4,$5)`, newID, userID, family, newHash, expires); e != nil {
		return "", e
	}
	if _, e = tx.ExecContext(ctx, `UPDATE refresh_sessions SET rotated_at=now(),replaced_by=$2 WHERE id=$1`, sessionID, newID); e != nil {
		return "", e
	}
	if e = tx.Commit(); e != nil {
		return "", e
	}
	return userID, nil
}
func (s *Store) RevokeRefresh(ctx context.Context, tokenHash string) error {
	_, e := s.DB.ExecContext(ctx, `UPDATE refresh_sessions SET revoked_at=COALESCE(revoked_at,now()) WHERE token_hash=$1`, tokenHash)
	return e
}
func (s *Store) RevokeFamily(ctx context.Context, tokenHash string) error {
	_, e := s.DB.ExecContext(ctx, `UPDATE refresh_sessions SET revoked_at=COALESCE(revoked_at,now()) WHERE family_id=(SELECT family_id FROM refresh_sessions WHERE token_hash=$1)`, tokenHash)
	return e
}
func (s *Store) CreateCalculation(ctx context.Context, userID string, input, result []byte, total float64) (string, time.Time, error) {
	id := uuid.NewString()
	var at time.Time
	e := s.DB.QueryRowContext(ctx, `INSERT INTO calculations(id,user_id,input_snapshot,result_snapshot,total_emissions_kg_co2) VALUES($1,$2,$3::jsonb,$4::jsonb,$5) RETURNING created_at`, id, userID, input, result, total).Scan(&at)
	return id, at, e
}

type Calculation struct {
	ID        string          `json:"id"`
	Input     json.RawMessage `json:"input"`
	Result    json.RawMessage `json:"result"`
	Total     float64         `json:"total_emissions_kg_co2"`
	CreatedAt time.Time       `json:"created_at"`
}

func (s *Store) ListCalculations(ctx context.Context, userID string, limit, offset int) ([]Calculation, error) {
	rows, e := s.DB.QueryContext(ctx, `SELECT id::text,input_snapshot,result_snapshot,total_emissions_kg_co2,created_at FROM calculations WHERE user_id=$1 ORDER BY created_at DESC,id DESC LIMIT $2 OFFSET $3`, userID, limit, offset)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	out := []Calculation{}
	for rows.Next() {
		var c Calculation
		if e = rows.Scan(&c.ID, &c.Input, &c.Result, &c.Total, &c.CreatedAt); e != nil {
			return nil, e
		}
		out = append(out, c)
	}
	return out, rows.Err()
}
func (s *Store) GetCalculation(ctx context.Context, userID, id string) (Calculation, error) {
	var c Calculation
	e := s.DB.QueryRowContext(ctx, `SELECT id::text,input_snapshot,result_snapshot,total_emissions_kg_co2,created_at FROM calculations WHERE user_id=$1 AND id=$2`, userID, id).Scan(&c.ID, &c.Input, &c.Result, &c.Total, &c.CreatedAt)
	return c, e
}
func IsUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}
