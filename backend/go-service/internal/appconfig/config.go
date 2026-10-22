package appconfig

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const maxProductionAccessTokenTTL = 15 * time.Minute

type Config struct {
	Environment, ListenAddress, DatabaseURL  string
	JWTSecret, JWTIssuer, JWTAudience        string
	AccessTokenTTL, RefreshTokenTTL          time.Duration
	FastAPIURL                               string
	CookieName, CookieDomain, CookieSameSite string
	CookieSecure                             bool
	AllowedOrigins                           []string
	DBMaxOpenConns, DBMaxIdleConns           int
	DBConnMaxLifetime                        time.Duration
}

func Load() (Config, error) {
	c := Config{
		Environment: get("APP_ENV", "development"), ListenAddress: listenAddress(),
		DatabaseURL: os.Getenv("DATABASE_URL"), JWTSecret: os.Getenv("JWT_SECRET"),
		JWTIssuer: get("JWT_ISSUER", "carbonwise-go-api"), JWTAudience: get("JWT_AUDIENCE", "carbonwise-client"),
		FastAPIURL: get("FASTAPI_URL", "http://127.0.0.1:8000"), CookieName: get("REFRESH_COOKIE_NAME", "carbonwise_refresh"),
		CookieDomain: os.Getenv("COOKIE_DOMAIN"), CookieSameSite: get("COOKIE_SAME_SITE", "lax"),
		DBMaxOpenConns: 20, DBMaxIdleConns: 5, DBConnMaxLifetime: 5 * time.Minute,
	}
	var err error
	if c.CookieSecure, err = boolean("COOKIE_SECURE", true); err != nil {
		return c, err
	}
	if c.AccessTokenTTL, err = duration("ACCESS_TOKEN_TTL", "15m"); err != nil {
		return c, err
	}
	if c.RefreshTokenTTL, err = duration("REFRESH_TOKEN_TTL", "720h"); err != nil {
		return c, err
	}
	if c.DBMaxOpenConns, err = integer("DB_MAX_OPEN_CONNS", 20); err != nil {
		return c, err
	}
	if c.DBMaxIdleConns, err = integer("DB_MAX_IDLE_CONNS", 5); err != nil {
		return c, err
	}
	c.AllowedOrigins = split(os.Getenv("ALLOWED_ORIGINS"))
	if c.DatabaseURL == "" {
		return c, errors.New("DATABASE_URL is required")
	}
	if len(c.JWTSecret) < 32 {
		return c, errors.New("JWT_SECRET must contain at least 32 characters")
	}
	if c.AccessTokenTTL <= 0 || c.RefreshTokenTTL <= c.AccessTokenTTL {
		return c, errors.New("refresh token lifetime must exceed a positive access token lifetime")
	}
	if c.CookieSameSite != "lax" && c.CookieSameSite != "strict" && c.CookieSameSite != "none" {
		return c, errors.New("COOKIE_SAME_SITE must be lax, strict, or none")
	}
	if c.CookieSameSite == "none" && !c.CookieSecure {
		return c, errors.New("COOKIE_SECURE must be true when COOKIE_SAME_SITE=none")
	}
	if c.DBMaxOpenConns < 1 || c.DBMaxIdleConns < 0 || c.DBMaxIdleConns > c.DBMaxOpenConns {
		return c, errors.New("invalid database pool limits")
	}
	if c.Environment == "production" {
		if err = validateProduction(c); err != nil {
			return c, err
		}
	}
	return c, nil
}

func listenAddress() string {
	if address := os.Getenv("LISTEN_ADDRESS"); address != "" {
		return address
	}
	if port := os.Getenv("PORT"); port != "" {
		return ":" + port
	}
	return ":8080"
}

func validateProduction(c Config) error {
	if weakProductionSecret(c.JWTSecret) {
		return errors.New("production requires a non-development JWT_SECRET")
	}
	if c.AccessTokenTTL > maxProductionAccessTokenTTL {
		return fmt.Errorf("production ACCESS_TOKEN_TTL must not exceed %s", maxProductionAccessTokenTTL)
	}
	if !c.CookieSecure {
		return errors.New("production requires COOKIE_SECURE=true")
	}
	if len(c.AllowedOrigins) == 0 {
		return errors.New("production requires ALLOWED_ORIGINS")
	}
	for _, origin := range c.AllowedOrigins {
		parsed, err := url.Parse(origin)
		if err != nil || parsed.Scheme != "https" || parsed.Host == "" || strings.Contains(parsed.Host, "*") || parsed.User != nil || parsed.Path != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
			return errors.New("production ALLOWED_ORIGINS must contain exact HTTPS origins")
		}
	}
	parsed, err := url.Parse(c.DatabaseURL)
	if err != nil || (parsed.Scheme != "postgres" && parsed.Scheme != "postgresql") || parsed.User == nil || parsed.Host == "" {
		return errors.New("production DATABASE_URL must be an explicit PostgreSQL URL")
	}
	if parsed.User.Username() == "carbonwise" || parsed.User.Username() == "" {
		return errors.New("production DATABASE_URL must not use development database credentials")
	}
	if password, ok := parsed.User.Password(); !ok || password == "" || password == "local-development-only" {
		return errors.New("production DATABASE_URL must use explicit non-development database credentials")
	}
	sslmode := parsed.Query().Get("sslmode")
	if sslmode != "require" && sslmode != "verify-ca" && sslmode != "verify-full" {
		return errors.New("production DATABASE_URL must require PostgreSQL TLS")
	}
	return nil
}

func weakProductionSecret(secret string) bool {
	lower := strings.ToLower(secret)
	if secret == "local-development-jwt-secret-change-me-before-sharing" || strings.Contains(lower, "replace-with") || strings.Contains(lower, "local-development") {
		return true
	}
	unique := map[rune]struct{}{}
	for _, r := range secret {
		unique[r] = struct{}{}
	}
	return len(unique) < 8
}

func get(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}
func duration(k, d string) (time.Duration, error) {
	v := get(k, d)
	out, e := time.ParseDuration(v)
	if e != nil {
		return 0, fmt.Errorf("%s: %w", k, e)
	}
	return out, nil
}
func integer(k string, d int) (int, error) {
	v := get(k, strconv.Itoa(d))
	out, e := strconv.Atoi(v)
	if e != nil {
		return 0, fmt.Errorf("%s: %w", k, e)
	}
	return out, nil
}
func boolean(k string, d bool) (bool, error) {
	v := get(k, strconv.FormatBool(d))
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "true":
		return true, nil
	case "false":
		return false, nil
	default:
		return false, fmt.Errorf("%s must be true or false", k)
	}
}
func split(v string) []string {
	var out []string
	for _, s := range strings.Split(v, ",") {
		if s = strings.TrimSpace(s); s != "" {
			out = append(out, s)
		}
	}
	return out
}
