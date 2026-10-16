package main

import (
	"context"
	"database/sql"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/carbonwise/go-service/internal/appconfig"
	"github.com/carbonwise/go-service/internal/auth"
	"github.com/carbonwise/go-service/internal/calculator"
	"github.com/carbonwise/go-service/internal/httpapi"
	"github.com/carbonwise/go-service/internal/store"
	_ "github.com/jackc/pgx/v5/stdlib"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := appconfig.Load()
	if err != nil {
		logger.Error("invalid configuration", "error", err)
		os.Exit(1)
	}

	db, err := sql.Open("pgx", cfg.DatabaseURL)
	if err != nil {
		logger.Error("open database", "error", err)
		os.Exit(1)
	}
	defer db.Close()
	db.SetMaxOpenConns(cfg.DBMaxOpenConns)
	db.SetMaxIdleConns(cfg.DBMaxIdleConns)
	db.SetConnMaxLifetime(cfg.DBConnMaxLifetime)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err = db.PingContext(ctx); err != nil {
		logger.Error("database unavailable", "error", err)
		os.Exit(1)
	}
	if err = store.Migrate(ctx, db); err != nil {
		logger.Error("database migration failed", "error", err)
		os.Exit(1)
	}

	tokens := auth.NewManager(cfg)
	api := httpapi.New(cfg, logger, store.New(db), tokens, calculator.New(cfg))
	server := &http.Server{Addr: cfg.ListenAddress, Handler: api.Handler(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 1 << 20}
	go func() {
		logger.Info("Go API listening", "address", cfg.ListenAddress)
		if e := server.ListenAndServe(); e != nil && !errors.Is(e, http.ErrServerClosed) {
			logger.Error("http server failed", "error", e)
			os.Exit(1)
		}
	}()

	stop, stopCancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stopCancel()
	<-stop.Done()
	shutdown, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutdownCancel()
	if err := server.Shutdown(shutdown); err != nil {
		logger.Error("graceful shutdown failed", "error", err)
	}
}
