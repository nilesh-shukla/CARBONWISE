package appconfig

import (
	"os"
	"strings"
	"testing"
)

func TestLoadProductionConfiguration(t *testing.T) {
	tests := []struct {
		name string
		env  map[string]string
		want string
	}{
		{
			name: "missing database URL",
			env:  productionEnv(""),
			want: "DATABASE_URL is required",
		},
		{
			name: "known development JWT secret",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "JWT_SECRET", "local-development-jwt-secret-change-me-before-sharing"),
			want: "non-development JWT_SECRET",
		},
		{
			name: "missing JWT secret",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "JWT_SECRET", ""),
			want: "at least 32 characters",
		},
		{
			name: "weak JWT secret",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "JWT_SECRET", strings.Repeat("a", 40)),
			want: "non-development JWT_SECRET",
		},
		{
			name: "insecure cookie",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "COOKIE_SECURE", "false"),
			want: "COOKIE_SECURE=true",
		},
		{
			name: "malformed cookie setting",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "COOKIE_SECURE", "sometimes"),
			want: "COOKIE_SECURE must be true or false",
		},
		{
			name: "invalid origin",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "ALLOWED_ORIGINS", "not-an-origin"),
			want: "exact HTTPS origins",
		},
		{
			name: "wildcard origin",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "ALLOWED_ORIGINS", "https://*.example.com"),
			want: "exact HTTPS origins",
		},
		{
			name: "missing origin",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "ALLOWED_ORIGINS", ""),
			want: "ALLOWED_ORIGINS",
		},
		{
			name: "excessive access token TTL",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "ACCESS_TOKEN_TTL", "16m"),
			want: "must not exceed",
		},
		{
			name: "invalid access token TTL",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=require"), "ACCESS_TOKEN_TTL", "not-a-duration"),
			want: "ACCESS_TOKEN_TTL",
		},
		{
			name: "development database credentials",
			env:  withEnv(productionEnv("postgres://carbonwise:local-development-only@db:5432/carbonwise?sslmode=require"), "DATABASE_URL", "postgres://carbonwise:prodpass@db:5432/carbonwise?sslmode=require"),
			want: "development database credentials",
		},
		{
			name: "insecure database transport",
			env:  withEnv(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=disable"), "DATABASE_URL", "postgres://produser:prodpass@db:5432/carbonwise?sslmode=disable"),
			want: "require PostgreSQL TLS",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			restore := setEnvironment(tt.env)
			defer restore()
			_, err := Load()
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Load() error = %v, want substring %q", err, tt.want)
			}
		})
	}
}

func TestLoadDevelopmentConfigurationRemainsConvenient(t *testing.T) {
	restore := setEnvironment(map[string]string{
		"APP_ENV":           "development",
		"DATABASE_URL":      "postgres://carbonwise:local-development-only@127.0.0.1:5433/carbonwise?sslmode=disable",
		"JWT_SECRET":        "local-development-jwt-secret-change-me-before-sharing",
		"COOKIE_SECURE":     "false",
		"ALLOWED_ORIGINS":   "http://localhost:3000",
		"ACCESS_TOKEN_TTL":  "15m",
		"REFRESH_TOKEN_TTL": "720h",
	})
	defer restore()
	if _, err := Load(); err != nil {
		t.Fatalf("Load() development error = %v", err)
	}
}

func TestLoadValidProductionConfiguration(t *testing.T) {
	restore := setEnvironment(productionEnv("postgres://produser:prodpass@db:5432/carbonwise?sslmode=verify-full"))
	defer restore()
	if _, err := Load(); err != nil {
		t.Fatalf("Load() valid production error = %v", err)
	}
}

func TestLoadUsesRenderPortWhenListenAddressIsUnset(t *testing.T) {
	restore := setEnvironment(map[string]string{
		"APP_ENV":           "development",
		"DATABASE_URL":      "postgres://127.0.0.1:5433/carbonwise?sslmode=disable",
		"JWT_SECRET":        "local-development-jwt-secret-change-me-before-sharing",
		"PORT":              "10000",
		"REFRESH_TOKEN_TTL": "720h",
	})
	defer restore()
	config, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if config.ListenAddress != ":10000" {
		t.Fatalf("ListenAddress = %q, want %q", config.ListenAddress, ":10000")
	}
}

func productionEnv(databaseURL string) map[string]string {
	return map[string]string{
		"APP_ENV":           "production",
		"DATABASE_URL":      databaseURL,
		"JWT_SECRET":        "production-test-secret-with-sufficient-entropy-123",
		"COOKIE_SECURE":     "true",
		"ALLOWED_ORIGINS":   "https://app.example.com",
		"ACCESS_TOKEN_TTL":  "15m",
		"REFRESH_TOKEN_TTL": "720h",
	}
}

func withEnv(env map[string]string, key, value string) map[string]string {
	env[key] = value
	return env
}

func setEnvironment(values map[string]string) func() {
	keys := []string{"APP_ENV", "DATABASE_URL", "JWT_SECRET", "COOKIE_SECURE", "ALLOWED_ORIGINS", "ACCESS_TOKEN_TTL", "REFRESH_TOKEN_TTL", "COOKIE_SAME_SITE", "DB_MAX_OPEN_CONNS", "DB_MAX_IDLE_CONNS", "LISTEN_ADDRESS", "PORT"}
	previous := make(map[string]string, len(keys))
	for _, key := range keys {
		previous[key] = os.Getenv(key)
		_ = os.Unsetenv(key)
	}
	for key, value := range values {
		_ = os.Setenv(key, value)
	}
	return func() {
		for _, key := range keys {
			if previous[key] == "" {
				_ = os.Unsetenv(key)
			} else {
				_ = os.Setenv(key, previous[key])
			}
		}
	}
}
