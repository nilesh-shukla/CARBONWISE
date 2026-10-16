package httpapi

import (
	"context"
	"crypto/subtle"
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/mail"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/carbonwise/go-service/internal/appconfig"
	"github.com/carbonwise/go-service/internal/auth"
	"github.com/carbonwise/go-service/internal/calculator"
	"github.com/carbonwise/go-service/internal/store"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
)

type API struct {
	cfg        appconfig.Config
	log        *slog.Logger
	db         *store.Store
	tokens     *auth.Manager
	calculator *calculator.Client
	limits     *limiter
}

func New(c appconfig.Config, l *slog.Logger, s *store.Store, t *auth.Manager, calc *calculator.Client) *API {
	return &API{cfg: c, log: l, db: s, tokens: t, calculator: calc, limits: newLimiter()}
}
func (a *API) Handler() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID, middleware.Recoverer, middleware.Timeout(20*time.Second), a.cors)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	r.Get("/readyz", func(w http.ResponseWriter, r *http.Request) {
		if a.db == nil || a.db.DB == nil {
			writeError(w, 503, "DATABASE_UNAVAILABLE", "Database is not ready.")
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if e := a.db.DB.PingContext(ctx); e != nil {
			writeError(w, 503, "DATABASE_UNAVAILABLE", "Database is not ready.")
			return
		}
		writeJSON(w, 200, map[string]string{"status": "ready"})
	})
	r.Route("/api", func(r chi.Router) {
		r.Route("/auth", func(r chi.Router) {
			r.Post("/register", a.rateLimit("register", 5, time.Minute, a.register))
			r.Post("/login", a.rateLimit("login", 10, time.Minute, a.login))
			r.Post("/refresh", a.refresh)
			r.Post("/logout", a.logout)
			r.Group(func(r chi.Router) { r.Use(a.authenticate); r.Get("/me", a.me) })
		})
		r.Group(func(r chi.Router) {
			r.Use(a.authenticate)
			r.Post("/calculations", a.createCalculation)
			r.Get("/calculations", a.listCalculations)
			r.Get("/calculations/{id}", a.getCalculation)
		})
	})
	return r
}

type authPayload struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (a *API) register(w http.ResponseWriter, r *http.Request) {
	var p authPayload
	if !decode(w, r, &p) {
		return
	}
	email, e := normalizeEmail(p.Email)
	if e != nil {
		writeError(w, 400, "INVALID_EMAIL", "Enter a valid email address.")
		return
	}
	hash, e := auth.HashPassword(p.Password)
	if e != nil {
		writeError(w, 400, "INVALID_PASSWORD", e.Error())
		return
	}
	refresh, refreshHash, e := auth.NewRefreshToken()
	if e != nil {
		a.internal(w, r, e)
		return
	}
	expires := time.Now().Add(a.cfg.RefreshTokenTTL)
	u, e := a.db.CreateUserWithRefresh(r.Context(), email, hash, refreshHash, uuid.NewString(), expires)
	if e != nil {
		if store.IsUniqueViolation(e) {
			writeError(w, 409, "EMAIL_EXISTS", "An account with this email already exists.")
		} else {
			a.internal(w, r, e)
		}
		return
	}
	access, e := a.tokens.Access(u.ID)
	if e != nil {
		a.internal(w, r, e)
		return
	}
	a.setCookie(w, refresh, expires)
	writeJSON(w, 201, map[string]any{"access_token": access, "token_type": "Bearer", "expires_in": int(a.cfg.AccessTokenTTL.Seconds()), "user": publicUser(u)})
}
func (a *API) login(w http.ResponseWriter, r *http.Request) {
	var p authPayload
	if !decode(w, r, &p) {
		return
	}
	email, e := normalizeEmail(p.Email)
	if e != nil {
		writeError(w, 401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
		return
	}
	u, e := a.db.UserByEmail(r.Context(), email)
	if e != nil || !auth.VerifyPassword(u.PasswordHash, p.Password) {
		writeError(w, 401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
		return
	}
	tokens, e := a.issue(w, u.ID)
	if e != nil {
		a.internal(w, r, e)
		return
	}
	tokens["user"] = publicUser(u)
	writeJSON(w, 200, tokens)
}
func (a *API) issue(w http.ResponseWriter, userID string) (map[string]any, error) {
	access, e := a.tokens.Access(userID)
	if e != nil {
		return nil, e
	}
	raw, hash, e := auth.NewRefreshToken()
	if e != nil {
		return nil, e
	}
	family := uuid.NewString()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	expires := time.Now().Add(a.cfg.RefreshTokenTTL)
	if e = a.db.CreateRefresh(ctx, userID, hash, family, expires); e != nil {
		return nil, e
	}
	a.setCookie(w, raw, expires)
	return map[string]any{"access_token": access, "token_type": "Bearer", "expires_in": int(a.cfg.AccessTokenTTL.Seconds())}, nil
}
func (a *API) refresh(w http.ResponseWriter, r *http.Request) {
	if !a.checkOrigin(w, r) {
		return
	}
	cookie, e := r.Cookie(a.cfg.CookieName)
	if e != nil {
		writeError(w, 401, "INVALID_SESSION", "Refresh session is missing.")
		return
	}
	raw, hash, e := auth.NewRefreshToken()
	if e != nil {
		writeError(w, 500, "TOKEN_ERROR", "Could not rotate refresh session.")
		return
	}
	userID, e := a.db.Rotate(r.Context(), auth.HashRefresh(cookie.Value), hash, time.Now().Add(a.cfg.RefreshTokenTTL))
	if e != nil {
		if errors.Is(e, store.ErrRefreshInvalid) {
			a.clearCookie(w)
			writeError(w, 401, "INVALID_SESSION", "Refresh session is invalid or expired.")
		} else {
			a.internal(w, r, e)
		}
		return
	}
	access, e := a.tokens.Access(userID)
	if e != nil {
		writeError(w, 500, "TOKEN_ERROR", "Could not issue access token.")
		return
	}
	a.setCookie(w, raw, time.Now().Add(a.cfg.RefreshTokenTTL))
	writeJSON(w, 200, map[string]any{"access_token": access, "token_type": "Bearer", "expires_in": int(a.cfg.AccessTokenTTL.Seconds())})
}
func (a *API) logout(w http.ResponseWriter, r *http.Request) {
	if !a.checkOrigin(w, r) {
		return
	}
	if cookie, e := r.Cookie(a.cfg.CookieName); e == nil {
		ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
		defer cancel()
		if e = a.db.RevokeFamily(ctx, auth.HashRefresh(cookie.Value)); e != nil {
			a.clearCookie(w)
			a.internal(w, r, e)
			return
		}
	}
	a.clearCookie(w)
	w.WriteHeader(http.StatusNoContent)
}
func (a *API) me(w http.ResponseWriter, r *http.Request) {
	u, e := a.db.UserByID(r.Context(), userID(r))
	if e != nil {
		if errors.Is(e, sql.ErrNoRows) {
			writeError(w, 401, "UNAUTHORIZED", "Account is unavailable.")
		} else {
			a.internal(w, r, e)
		}
		return
	}
	writeJSON(w, 200, map[string]any{"user": publicUser(u)})
}
func (a *API) createCalculation(w http.ResponseWriter, r *http.Request) {
	raw, e := readJSON(r, 1<<20)
	if e != nil {
		writeError(w, 400, "INVALID_JSON", "Request body must be a JSON object no larger than 1 MiB.")
		return
	}
	if _, e = calculator.ValidateRequest(raw); e != nil {
		writeError(w, 422, "VALIDATION_ERROR", e.Error())
		return
	}
	result, body, e := a.calculator.Calculate(r.Context(), raw)
	if e != nil {
		a.log.Warn("calculation upstream failed", "request_id", middleware.GetReqID(r.Context()), "error", e)
		writeError(w, 502, "CALCULATOR_UNAVAILABLE", "Calculation service failed or returned an invalid response.")
		return
	}
	id, created, e := a.db.CreateCalculation(r.Context(), userID(r), raw, body, result.Total)
	if e != nil {
		a.internal(w, r, e)
		return
	}
	writeJSON(w, 201, map[string]any{"id": id, "input": json.RawMessage(raw), "result": json.RawMessage(body), "total_emissions_kg_co2": result.Total, "created_at": created})
}
func (a *API) listCalculations(w http.ResponseWriter, r *http.Request) {
	limit := 20
	offset := 0
	var e error
	if v := r.URL.Query().Get("limit"); v != "" {
		limit, e = strconv.Atoi(v)
		if e != nil || limit < 1 || limit > 100 {
			writeError(w, 400, "INVALID_PAGINATION", "limit must be between 1 and 100.")
			return
		}
	}
	if v := r.URL.Query().Get("offset"); v != "" {
		offset, e = strconv.Atoi(v)
		if e != nil || offset < 0 {
			writeError(w, 400, "INVALID_PAGINATION", "offset must be zero or greater.")
			return
		}
	}
	items, e := a.db.ListCalculations(r.Context(), userID(r), limit, offset)
	if e != nil {
		a.internal(w, r, e)
		return
	}
	writeJSON(w, 200, map[string]any{"items": items, "limit": limit, "offset": offset})
}
func (a *API) getCalculation(w http.ResponseWriter, r *http.Request) {
	if _, e := uuid.Parse(chi.URLParam(r, "id")); e != nil {
		writeError(w, 400, "INVALID_ID", "Calculation ID must be a UUID.")
		return
	}
	item, e := a.db.GetCalculation(r.Context(), userID(r), chi.URLParam(r, "id"))
	if errors.Is(e, sql.ErrNoRows) {
		writeError(w, 404, "NOT_FOUND", "Calculation was not found.")
		return
	}
	if e != nil {
		a.internal(w, r, e)
		return
	}
	writeJSON(w, 200, item)
}
func (a *API) authenticate(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		parts := strings.Fields(r.Header.Get("Authorization"))
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
			writeError(w, 401, "UNAUTHORIZED", "A bearer access token is required.")
			return
		}
		id, e := a.tokens.Parse(parts[1])
		if e != nil {
			writeError(w, 401, "UNAUTHORIZED", "Access token is invalid or expired.")
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), userIDKey{}, id)))
	})
}

type userIDKey struct{}

func userID(r *http.Request) string { id, _ := r.Context().Value(userIDKey{}).(string); return id }
func (a *API) cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" {
			for _, allowed := range a.cfg.AllowedOrigins {
				if subtle.ConstantTimeCompare([]byte(origin), []byte(allowed)) == 1 {
					w.Header().Set("Access-Control-Allow-Origin", origin)
					w.Header().Set("Vary", "Origin")
					w.Header().Set("Access-Control-Allow-Credentials", "true")
					w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
					w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
					break
				}
			}
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(204)
			return
		}
		next.ServeHTTP(w, r)
	})
}
func (a *API) checkOrigin(w http.ResponseWriter, r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" && a.cfg.Environment != "production" {
		return true
	}
	for _, allowed := range a.cfg.AllowedOrigins {
		if subtle.ConstantTimeCompare([]byte(origin), []byte(allowed)) == 1 {
			return true
		}
	}
	writeError(w, 403, "ORIGIN_FORBIDDEN", "Request origin is not allowed.")
	return false
}
func (a *API) setCookie(w http.ResponseWriter, value string, expires time.Time) {
	http.SetCookie(w, &http.Cookie{Name: a.cfg.CookieName, Value: value, Path: "/api/auth", Domain: a.cfg.CookieDomain, Expires: expires, MaxAge: int(time.Until(expires).Seconds()), HttpOnly: true, Secure: a.cfg.CookieSecure, SameSite: a.sameSite()})
}
func (a *API) clearCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{Name: a.cfg.CookieName, Value: "", Path: "/api/auth", Domain: a.cfg.CookieDomain, MaxAge: -1, HttpOnly: true, Secure: a.cfg.CookieSecure, SameSite: a.sameSite()})
}
func (a *API) sameSite() http.SameSite {
	switch a.cfg.CookieSameSite {
	case "strict":
		return http.SameSiteStrictMode
	case "none":
		return http.SameSiteNoneMode
	default:
		return http.SameSiteLaxMode
	}
}
func (a *API) internal(w http.ResponseWriter, r *http.Request, e error) {
	a.log.Error("request failed", "request_id", middleware.GetReqID(r.Context()), "error", e)
	writeError(w, 500, "INTERNAL_ERROR", "An unexpected server error occurred.")
}
func (a *API) rateLimit(action string, max int, window time.Duration, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ip, _, _ := net.SplitHostPort(r.RemoteAddr)
		if ip == "" {
			ip = r.RemoteAddr
		}
		if !a.limits.allow(action+ip, max, window) {
			w.Header().Set("Retry-After", strconv.Itoa(int(window.Seconds())))
			writeError(w, 429, "RATE_LIMITED", "Too many attempts. Try again later.")
			return
		}
		next(w, r)
	}
}

type limiter struct {
	mu   sync.Mutex
	hits map[string][]time.Time
}

func newLimiter() *limiter { return &limiter{hits: map[string][]time.Time{}} }
func (l *limiter) allow(k string, max int, window time.Duration) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	if len(l.hits) > 4096 {
		for key, times := range l.hits {
			if len(times) == 0 || now.Sub(times[len(times)-1]) >= window {
				delete(l.hits, key)
			}
		}
	}
	if _, exists := l.hits[k]; !exists && len(l.hits) >= 8192 {
		return false
	}
	hits := l.hits[k][:0]
	for _, t := range l.hits[k] {
		if now.Sub(t) < window {
			hits = append(hits, t)
		}
	}
	if len(hits) >= max {
		l.hits[k] = hits
		return false
	}
	l.hits[k] = append(hits, now)
	return true
}
func normalizeEmail(raw string) (string, error) {
	raw = strings.TrimSpace(strings.ToLower(raw))
	if len(raw) > 254 {
		return "", errors.New("invalid")
	}
	addr, e := mail.ParseAddress(raw)
	if e != nil || addr.Address != raw || !strings.Contains(raw, ".") {
		return "", errors.New("invalid")
	}
	return raw, nil
}
func publicUser(u store.User) map[string]any {
	return map[string]any{"id": u.ID, "email": u.Email, "created_at": u.CreatedAt}
}
func decode(w http.ResponseWriter, r *http.Request, v any) bool {
	raw, e := readJSON(r, 16<<10)
	if e != nil {
		writeError(w, 400, "INVALID_JSON", "Request body must be valid JSON no larger than 16 KiB.")
		return false
	}
	d := json.NewDecoder(strings.NewReader(string(raw)))
	d.DisallowUnknownFields()
	if e = d.Decode(v); e != nil {
		writeError(w, 400, "INVALID_REQUEST", "Request body contains invalid fields.")
		return false
	}
	return true
}
func readJSON(r *http.Request, max int64) (json.RawMessage, error) {
	d := json.NewDecoder(http.MaxBytesReader(nil, r.Body, max))
	var raw json.RawMessage
	if e := d.Decode(&raw); e != nil {
		return nil, e
	}
	if len(raw) == 0 || raw[0] != '{' {
		return nil, errors.New("JSON object required")
	}
	var extra any
	if e := d.Decode(&extra); e != io.EOF {
		return nil, errors.New("extra JSON content")
	}
	return raw, nil
}
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]any{"error": map[string]string{"code": code, "message": message}})
}
