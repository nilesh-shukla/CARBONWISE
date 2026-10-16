package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"os"
	"reflect"
	"testing"
	"time"

	"github.com/google/uuid"
	_ "github.com/jackc/pgx/v5/stdlib"
)

// Set CARBONWISE_TEST_DATABASE_URL to a dedicated PostgreSQL database to run this test.
func TestPostgresMigrationsOwnershipAndSnapshots(t *testing.T) {
	dsn := os.Getenv("CARBONWISE_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("CARBONWISE_TEST_DATABASE_URL is not set; see backend/go-service/README.md")
	}
	db, e := sql.Open("pgx", dsn)
	if e != nil {
		t.Fatal(e)
	}
	defer db.Close()
	db.SetMaxOpenConns(1)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if e = db.PingContext(ctx); e != nil {
		t.Fatal(e)
	}
	if e = Migrate(ctx, db); e != nil {
		t.Fatal(e)
	}
	if e = Migrate(ctx, db); e != nil {
		t.Fatalf("second migration run was not idempotent: %v", e)
	}
	var migrationCount int
	if e = db.QueryRowContext(ctx, `SELECT count(*) FROM schema_migrations WHERE version='001_initial'`).Scan(&migrationCount); e != nil || migrationCount != 1 {
		t.Fatalf("migration ledger count=%d err=%v, want one applied migration", migrationCount, e)
	}
	s := New(db)
	email := "integration-" + uuid.NewString() + "@example.test"
	u, e := s.CreateUser(ctx, email, "argon2id-test-placeholder")
	if e != nil {
		t.Fatal(e)
	}
	defer func() { _, _ = db.ExecContext(context.Background(), `DELETE FROM users WHERE id=$1`, u.ID) }()
	other, e := s.CreateUser(ctx, "integration-"+uuid.NewString()+"@example.test", "argon2id-test-placeholder")
	if e != nil {
		t.Fatal(e)
	}
	defer func() { _, _ = db.ExecContext(context.Background(), `DELETE FROM users WHERE id=$1`, other.ID) }()
	if e = s.CreateRefresh(ctx, u.ID, "hash-"+uuid.NewString(), uuid.NewString(), time.Now().Add(time.Hour)); e != nil {
		t.Fatal(e)
	}
	input := []byte(`{"electricity_kwh_per_month":42}`)
	result := []byte(`{"total_emissions_kg_co2":30.072,"calculation_status":"complete_for_provided_inputs"}`)
	id, _, e := s.CreateCalculation(ctx, u.ID, input, result, 30.072)
	if e != nil {
		t.Fatal(e)
	}
	items, e := s.ListCalculations(ctx, u.ID, 10, 0)
	if e != nil || len(items) != 1 {
		t.Fatalf("owner history: items=%d err=%v", len(items), e)
	}
	var savedInput, expectedInput, savedResult, expectedResult any
	if e = json.Unmarshal(items[0].Input, &savedInput); e != nil {
		t.Fatal(e)
	}
	if e = json.Unmarshal(input, &expectedInput); e != nil {
		t.Fatal(e)
	}
	if e = json.Unmarshal(items[0].Result, &savedResult); e != nil {
		t.Fatal(e)
	}
	if e = json.Unmarshal(result, &expectedResult); e != nil {
		t.Fatal(e)
	}
	if !reflect.DeepEqual(savedInput, expectedInput) || !reflect.DeepEqual(savedResult, expectedResult) {
		t.Fatal("saved JSON snapshots differ semantically")
	}
	if _, e = s.GetCalculation(ctx, other.ID, id); e != sql.ErrNoRows {
		t.Fatalf("other user lookup error=%v, want sql.ErrNoRows", e)
	}
}
