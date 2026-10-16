package appconfig

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

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
		Environment: get("APP_ENV", "development"), ListenAddress: get("LISTEN_ADDRESS", ":8080"),
		DatabaseURL: os.Getenv("DATABASE_URL"), JWTSecret: os.Getenv("JWT_SECRET"),
		JWTIssuer: get("JWT_ISSUER", "carbonwise-go-api"), JWTAudience: get("JWT_AUDIENCE", "carbonwise-client"),
		FastAPIURL: get("FASTAPI_URL", "http://127.0.0.1:8000"), CookieName: get("REFRESH_COOKIE_NAME", "carbonwise_refresh"),
		CookieDomain: os.Getenv("COOKIE_DOMAIN"), CookieSameSite: get("COOKIE_SAME_SITE", "lax"),
		CookieSecure: get("COOKIE_SECURE", "true") == "true", DBMaxOpenConns: 20, DBMaxIdleConns: 5, DBConnMaxLifetime: 5 * time.Minute,
	}
	var err error
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
	if c.Environment == "production" && (!c.CookieSecure || len(c.AllowedOrigins) == 0) {
		return c, errors.New("production requires secure refresh cookies and ALLOWED_ORIGINS")
	}
	return c, nil
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
func split(v string) []string {
	var out []string
	for _, s := range strings.Split(v, ",") {
		if s = strings.TrimSpace(s); s != "" {
			out = append(out, s)
		}
	}
	return out
}
