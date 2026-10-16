package auth

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/carbonwise/go-service/internal/appconfig"
	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/argon2"
)

type Manager struct{ cfg appconfig.Config }
type Claims struct{ jwt.RegisteredClaims }

func NewManager(c appconfig.Config) *Manager { return &Manager{cfg: c} }

func HashPassword(password string) (string, error) {
	if len(password) < 12 || len(password) > 128 {
		return "", errors.New("password must be between 12 and 128 bytes")
	}
	salt := make([]byte, 16)
	if _, e := rand.Read(salt); e != nil {
		return "", e
	}
	const memory = 64 * 1024
	const iterations = 3
	const parallelism = 2
	const keyLen = 32
	hash := argon2.IDKey([]byte(password), salt, iterations, memory, parallelism, keyLen)
	return fmt.Sprintf("$argon2id$v=19$m=%d,t=%d,p=%d$%s$%s", memory, iterations, parallelism, base64.RawStdEncoding.EncodeToString(salt), base64.RawStdEncoding.EncodeToString(hash)), nil
}
func VerifyPassword(encoded, password string) bool {
	parts := strings.Split(encoded, "$")
	if len(parts) != 6 || parts[1] != "argon2id" {
		return false
	}
	var memory uint32
	var iterations uint32
	var parallelism uint8
	if _, e := fmt.Sscanf(parts[3], "m=%d,t=%d,p=%d", &memory, &iterations, &parallelism); e != nil || memory < 8*1024 || memory > 256*1024 || iterations < 1 || iterations > 10 || parallelism < 1 || parallelism > 8 {
		return false
	}
	salt, e := base64.RawStdEncoding.DecodeString(parts[4])
	if e != nil || len(salt) < 8 || len(salt) > 64 {
		return false
	}
	want, e := base64.RawStdEncoding.DecodeString(parts[5])
	if e != nil || len(want) < 16 || len(want) > 64 {
		return false
	}
	got := argon2.IDKey([]byte(password), salt, iterations, memory, parallelism, uint32(len(want)))
	return subtleEqual(got, want)
}
func subtleEqual(a, b []byte) bool { return subtle.ConstantTimeCompare(a, b) == 1 }
func (m *Manager) Access(userID string) (string, error) {
	now := time.Now().UTC()
	id, err := randomID()
	if err != nil {
		return "", err
	}
	claims := Claims{RegisteredClaims: jwt.RegisteredClaims{Issuer: m.cfg.JWTIssuer, Subject: userID, Audience: []string{m.cfg.JWTAudience}, ID: id, IssuedAt: jwt.NewNumericDate(now), NotBefore: jwt.NewNumericDate(now.Add(-time.Second)), ExpiresAt: jwt.NewNumericDate(now.Add(m.cfg.AccessTokenTTL))}}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(m.cfg.JWTSecret))
}
func (m *Manager) Parse(token string) (string, error) {
	claims := &Claims{}
	parsed, e := jwt.ParseWithClaims(token, claims, func(t *jwt.Token) (any, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, errors.New("unexpected signing algorithm")
		}
		return []byte(m.cfg.JWTSecret), nil
	}, jwt.WithIssuer(m.cfg.JWTIssuer), jwt.WithAudience(m.cfg.JWTAudience), jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}))
	if e != nil || !parsed.Valid || claims.Subject == "" || claims.ID == "" || claims.ExpiresAt == nil || claims.IssuedAt == nil || claims.NotBefore == nil {
		return "", errors.New("invalid access token")
	}
	return claims.Subject, nil
}
func NewRefreshToken() (string, string, error) {
	raw := make([]byte, 32)
	if _, e := rand.Read(raw); e != nil {
		return "", "", e
	}
	token := base64.RawURLEncoding.EncodeToString(raw)
	return token, HashRefresh(token), nil
}
func HashRefresh(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}
func randomID() (string, error) {
	b := make([]byte, 16)
	if _, e := rand.Read(b); e != nil {
		return "", e
	}
	return hex.EncodeToString(b), nil
}
