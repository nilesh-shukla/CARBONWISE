package auth

import (
	"testing"
	"time"

	"github.com/carbonwise/go-service/internal/appconfig"
	"github.com/golang-jwt/jwt/v5"
)

func testManager() *Manager {
	return NewManager(appconfig.Config{JWTSecret: "0123456789abcdef0123456789abcdef", JWTIssuer: "issuer", JWTAudience: "audience", AccessTokenTTL: time.Minute})
}
func TestPasswordHashAndVerify(t *testing.T) {
	hash, e := HashPassword("correct horse battery staple")
	if e != nil {
		t.Fatal(e)
	}
	if !VerifyPassword(hash, "correct horse battery staple") {
		t.Fatal("valid password rejected")
	}
	if VerifyPassword(hash, "wrong password value") {
		t.Fatal("wrong password accepted")
	}
}
func TestAccessTokenClaimsAndTampering(t *testing.T) {
	m := testManager()
	token, e := m.Access("user-123")
	if e != nil {
		t.Fatal(e)
	}
	id, e := m.Parse(token)
	if e != nil || id != "user-123" {
		t.Fatalf("Parse() = %q, %v", id, e)
	}
	if _, e = m.Parse(token + "x"); e == nil {
		t.Fatal("tampered token accepted")
	}
}
func TestExpiredAccessTokenIsRejected(t *testing.T) {
	m := testManager()
	claims := jwt.RegisteredClaims{
		Issuer: m.cfg.JWTIssuer, Subject: "user-123", Audience: []string{m.cfg.JWTAudience}, ID: "expired-test",
		IssuedAt: jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)), NotBefore: jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(-time.Hour)),
	}
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(m.cfg.JWTSecret))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = m.Parse(token); err == nil {
		t.Fatal("expired access token was accepted")
	}
}
func TestRefreshTokenIsRandomAndStoredAsHash(t *testing.T) {
	a, ha, e := NewRefreshToken()
	if e != nil {
		t.Fatal(e)
	}
	b, hb, e := NewRefreshToken()
	if e != nil {
		t.Fatal(e)
	}
	if a == b || ha == hb {
		t.Fatal("refresh token collision")
	}
	if a == ha || ha != HashRefresh(a) {
		t.Fatal("unexpected refresh token hash")
	}
}
