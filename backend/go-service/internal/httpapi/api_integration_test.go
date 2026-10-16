package httpapi

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/carbonwise/go-service/internal/appconfig"
	"github.com/carbonwise/go-service/internal/auth"
	"github.com/carbonwise/go-service/internal/calculator"
	"github.com/carbonwise/go-service/internal/store"
	_ "github.com/jackc/pgx/v5/stdlib"
)

// Runs the API and PostgreSQL-backed flow when a dedicated test DB is configured.
func TestPostgresAuthenticatedCalculationFlow(t *testing.T) {
	dsn := os.Getenv("CARBONWISE_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("CARBONWISE_TEST_DATABASE_URL is not set; see backend/go-service/README.md")
	}
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	db.SetMaxOpenConns(4)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err = db.PingContext(ctx); err != nil {
		t.Fatal(err)
	}
	if err = store.Migrate(ctx, db); err != nil {
		t.Fatal(err)
	}

	var upstreamFailure atomic.Bool
	fastAPI := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if upstreamFailure.Load() {
			http.Error(w, "unavailable", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"reporting_period":"monthly","gas_scope":"CO2","unit":"kgCO2/month","calculation_status":"complete_for_provided_inputs","total_is_partial":false,"calculated_categories":["electricity","lpg"],"excluded_categories":{},"not_provided_categories":["petrol","diesel"],"footprint_scope_note":"scope","total_emissions_kg_co2":113.9817,"direct_emissions_kg_co2":42.3817,"indirect_emissions_kg_co2":71.6,"categories":{"electricity":{"status":"calculated"},"lpg":{"status":"calculated"},"petrol":{"status":"not_provided"},"diesel":{"status":"not_provided"}},"factor_ids":["electricity-test","lpg-test"],"sources":["test"],"assumptions":["monthly"]}`)
	}))
	defer fastAPI.Close()
	cfg := appconfig.Config{Environment: "test", CookieName: "carbonwise_refresh", CookieSameSite: "lax", JWTSecret: "integration-test-secret-with-more-than-32-bytes", JWTIssuer: "issuer", JWTAudience: "audience", AccessTokenTTL: time.Minute, RefreshTokenTTL: time.Hour, FastAPIURL: fastAPI.URL, DBMaxOpenConns: 4, DBMaxIdleConns: 2}
	api := New(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), store.New(db), auth.NewManager(cfg), calculator.New(cfg))
	server := httptest.NewServer(api.Handler())
	defer server.Close()
	client := server.Client()
	register := func(email string) (string, *http.Cookie) {
		t.Helper()
		resp, b := request(t, client, http.MethodPost, server.URL+"/api/auth/register", `{"email":"`+email+`","password":"a-long-integration-password"}`, nil)
		defer resp.Body.Close()
		if resp.StatusCode != 201 {
			data, _ := io.ReadAll(b)
			t.Fatalf("register status=%d: %s", resp.StatusCode, data)
		}
		var body map[string]any
		if err = json.NewDecoder(resp.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		token, _ := body["access_token"].(string)
		var cookie *http.Cookie
		for _, c := range resp.Cookies() {
			if c.Name == cfg.CookieName {
				cookie = c
			}
		}
		if token == "" || cookie == nil {
			t.Fatal("registration did not issue access and refresh tokens")
		}
		return token, cookie
	}
	email1 := "api-test-" + time.Now().Format("150405.000000000") + "@example.test"
	access1, refresh1 := register(email1)
	defer func() { _, _ = db.ExecContext(context.Background(), `DELETE FROM users WHERE email=$1`, email1) }()
	resp, _ := request(t, client, http.MethodGet, server.URL+"/api/auth/me", "", map[string]string{"Authorization": "Bearer " + access1})
	if resp.StatusCode != 200 {
		t.Fatalf("me status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	resp, _ = request(t, client, http.MethodPost, server.URL+"/api/calculations", `{"electricity_kwh_per_month":150,"lpg_kg_per_month":14.2}`, map[string]string{"Authorization": "Bearer " + access1})
	if resp.StatusCode != 201 {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("calculation status=%d: %s", resp.StatusCode, body)
	}
	var saved map[string]any
	if err = json.NewDecoder(resp.Body).Decode(&saved); err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if saved["total_emissions_kg_co2"] != 113.9817 {
		t.Fatalf("calculator response not preserved: %#v", saved)
	}
	calculationID, _ := saved["id"].(string)
	resp, _ = request(t, client, http.MethodGet, server.URL+"/api/calculations/"+calculationID, "", map[string]string{"Authorization": "Bearer " + access1})
	if resp.StatusCode != 200 {
		t.Fatalf("owner read status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	email2 := "other-" + time.Now().Format("150405.000000000") + "@example.test"
	access2, _ := register(email2)
	defer func() { _, _ = db.ExecContext(context.Background(), `DELETE FROM users WHERE email=$1`, email2) }()
	resp, _ = request(t, client, http.MethodGet, server.URL+"/api/calculations/"+calculationID, "", map[string]string{"Authorization": "Bearer " + access2})
	if resp.StatusCode != 404 {
		t.Fatalf("cross-user calculation read status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	resp, _ = request(t, client, http.MethodPost, server.URL+"/api/calculations", `{"electricity_kwh_per_month":-1}`, map[string]string{"Authorization": "Bearer " + access1})
	if resp.StatusCode != 422 {
		t.Fatalf("invalid input status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	upstreamFailure.Store(true)
	resp, _ = request(t, client, http.MethodPost, server.URL+"/api/calculations", `{"electricity_kwh_per_month":11}`, map[string]string{"Authorization": "Bearer " + access1})
	if resp.StatusCode != 502 {
		t.Fatalf("upstream error status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	upstreamFailure.Store(false)
	items, err := store.New(db).ListCalculations(ctx, findUserID(t, db, email1), 100, 0)
	if err != nil || len(items) != 1 {
		t.Fatalf("failed request was persisted: count=%d err=%v", len(items), err)
	}
	resp, _ = requestCookie(t, client, server.URL+"/api/auth/refresh", refresh1, nil)
	if resp.StatusCode != 200 {
		t.Fatalf("refresh status=%d", resp.StatusCode)
	}
	var rotated *http.Cookie
	for _, c := range resp.Cookies() {
		if c.Name == cfg.CookieName {
			rotated = c
		}
	}
	resp.Body.Close()
	if rotated == nil {
		t.Fatal("refresh did not rotate cookie")
	}
	resp, _ = requestCookie(t, client, server.URL+"/api/auth/refresh", refresh1, nil)
	if resp.StatusCode != 401 {
		t.Fatalf("reused refresh token status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	resp, _ = requestCookie(t, client, server.URL+"/api/auth/refresh", rotated, nil)
	if resp.StatusCode != 401 {
		t.Fatalf("reuse did not revoke token family: status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	loginBody, _ := json.Marshal(map[string]string{"email": email1, "password": "a-long-integration-password"})
	resp, _ = request(t, client, http.MethodPost, server.URL+"/api/auth/login", string(loginBody), nil)
	if resp.StatusCode != 200 {
		t.Fatalf("login status=%d", resp.StatusCode)
	}
	var loginCookie *http.Cookie
	for _, c := range resp.Cookies() {
		if c.Name == cfg.CookieName {
			loginCookie = c
		}
	}
	resp.Body.Close()
	if loginCookie == nil {
		t.Fatal("login did not issue refresh cookie")
	}
	resp, _ = requestCookie(t, client, server.URL+"/api/auth/logout", loginCookie, nil)
	if resp.StatusCode != 204 {
		t.Fatalf("logout status=%d", resp.StatusCode)
	}
	resp.Body.Close()
	resp, _ = requestCookie(t, client, server.URL+"/api/auth/refresh", loginCookie, nil)
	if resp.StatusCode != 401 {
		t.Fatalf("revoked refresh token status=%d", resp.StatusCode)
	}
	resp.Body.Close()
}

func request(t *testing.T, c *http.Client, method, url, body string, headers map[string]string) (*http.Response, io.Reader) {
	t.Helper()
	req, err := http.NewRequest(method, url, strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := c.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	return resp, bytes.NewReader(nil)
}
func requestCookie(t *testing.T, c *http.Client, url string, cookie *http.Cookie, headers map[string]string) (*http.Response, io.Reader) {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, url, nil)
	if err != nil {
		t.Fatal(err)
	}
	req.AddCookie(cookie)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := c.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	return resp, bytes.NewReader(nil)
}
func findUserID(t *testing.T, db *sql.DB, email string) string {
	t.Helper()
	var id string
	if err := db.QueryRow(`SELECT id::text FROM users WHERE email=$1`, email).Scan(&id); err != nil {
		t.Fatal(err)
	}
	return id
}
