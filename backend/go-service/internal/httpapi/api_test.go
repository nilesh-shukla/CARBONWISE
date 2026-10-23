package httpapi

import (
	"database/sql"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/carbonwise/go-service/internal/appconfig"
	"github.com/carbonwise/go-service/internal/auth"
	"github.com/carbonwise/go-service/internal/calculator"
	"github.com/carbonwise/go-service/internal/store"
	_ "github.com/jackc/pgx/v5/stdlib"
)

func testAPI() *API {
	cfg := appconfig.Config{Environment: "test", CookieName: "refresh", CookieSameSite: "lax", JWTSecret: "0123456789abcdef0123456789abcdef", JWTIssuer: "issuer", JWTAudience: "audience", AccessTokenTTL: time.Minute, AllowedOrigins: []string{"https://client.example"}}
	return New(cfg, slog.New(slog.NewTextHandler(&strings.Builder{}, nil)), &store.Store{}, auth.NewManager(cfg), calculator.New(cfg))
}
func TestHealthAndReady(t *testing.T) {
	api := testAPI()
	rr := httptest.NewRecorder()
	api.Handler().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/health", nil))
	if rr.Code != 200 || !strings.Contains(rr.Body.String(), `"status":"ok"`) {
		t.Fatalf("health: %d %s", rr.Code, rr.Body.String())
	}
	rr = httptest.NewRecorder()
	api.Handler().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rr.Code != 503 {
		t.Fatalf("ready status=%d", rr.Code)
	}
	db, err := sql.Open("pgx", "postgres://postgres@127.0.0.1:1/unavailable?sslmode=disable")
	if err != nil {
		t.Fatal(err)
	}
	if err = db.Close(); err != nil {
		t.Fatal(err)
	}
	api.db = store.New(db)
	rr = httptest.NewRecorder()
	api.Handler().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rr.Code != 503 {
		t.Fatalf("closed database readiness status=%d", rr.Code)
	}
}
func TestProtectedRouteRequiresBearer(t *testing.T) {
	api := testAPI()
	rr := httptest.NewRecorder()
	api.Handler().ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/api/auth/me", nil))
	if rr.Code != 401 {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}
func TestRefreshRejectsUntrustedOrigin(t *testing.T) {
	api := testAPI()
	req := httptest.NewRequest(http.MethodPost, "/api/auth/refresh", nil)
	req.Header.Set("Origin", "https://evil.example")
	rr := httptest.NewRecorder()
	api.Handler().ServeHTTP(rr, req)
	if rr.Code != 403 {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}
func TestCorsDoesNotReflectUntrustedOrigin(t *testing.T) {
	api := testAPI()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	req.Header.Set("Origin", "https://evil.example")
	rr := httptest.NewRecorder()
	api.Handler().ServeHTTP(rr, req)
	if rr.Header().Get("Access-Control-Allow-Origin") != "" {
		t.Fatal("untrusted origin was reflected")
	}
}

func TestRefreshCookieSecurityAttributes(t *testing.T) {
	api := testAPI()
	api.cfg.CookieSecure = true
	api.cfg.CookieSameSite = "none"
	rr := httptest.NewRecorder()
	api.setCookie(rr, "test-token-value", time.Now().Add(time.Hour))
	setCookie := rr.Header().Get("Set-Cookie")
	for _, required := range []string{"HttpOnly", "Secure", "SameSite=None", "Path=/api/auth"} {
		if !strings.Contains(setCookie, required) {
			t.Fatalf("Set-Cookie missing %q: %s", required, setCookie)
		}
	}
}

func TestCalculationUpstreamFailureLogsOnlySafeStatus(t *testing.T) {
	const secretActivity = "activity-value-should-not-be-logged-8123"
	const upstreamBody = "upstream detail containing " + secretActivity
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, upstreamBody, http.StatusBadGateway)
	}))
	defer upstream.Close()

	var logs strings.Builder
	api := testAPI()
	api.log = slog.New(slog.NewTextHandler(&logs, nil))
	api.calculator = calculator.New(appconfig.Config{FastAPIURL: upstream.URL})
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodPost, "/api/calculations", strings.NewReader(`{"electricity_kwh_per_month":8123}`))
	api.createCalculation(recorder, request)

	if recorder.Code != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502", recorder.Code)
	}
	var body map[string]map[string]string
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["error"]["code"] != "CALCULATOR_UNAVAILABLE" || strings.Contains(recorder.Body.String(), upstreamBody) {
		t.Fatalf("unexpected client error body: %s", recorder.Body.String())
	}
	logOutput := logs.String()
	if !strings.Contains(logOutput, "upstream_status=502") || strings.Contains(logOutput, upstreamBody) || strings.Contains(logOutput, secretActivity) || strings.Contains(logOutput, upstream.URL) {
		t.Fatalf("unsafe or missing upstream diagnostic: %s", logOutput)
	}
}
