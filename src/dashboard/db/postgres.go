package db

import (
	"database/sql"
	"fmt"
	"os"

	_ "github.com/jackc/pgx/v5/stdlib"
)

func postgresDSNFromEnv() (string, error) {
	host := os.Getenv("POSTGRES_HOST")
	port := os.Getenv("POSTGRES_PORT")
	database := os.Getenv("POSTGRES_DB")
	user := os.Getenv("POSTGRES_USER")
	password := os.Getenv("POSTGRES_PASSWORD")
	sslmode := os.Getenv("POSTGRES_SSLMODE")

	if host == "" || port == "" || database == "" || user == "" {
		return "", fmt.Errorf("missing required postgres environment variables")
	}
	if sslmode == "" {
		sslmode = "disable"
	}

	return fmt.Sprintf("host=%s port=%s dbname=%s user=%s password=%s sslmode=%s", host, port, database, user, password, sslmode), nil
}

func NewPostgresFromEnv() (*DB, error) {
	dsn, err := postgresDSNFromEnv()
	if err != nil {
		return nil, err
	}

	conn, err := sql.Open("pgx", dsn)
	if err != nil {
		return nil, err
	}
	if err := conn.Ping(); err != nil {
		return nil, err
	}

	_, err = conn.Exec(`
		CREATE TABLE IF NOT EXISTS runs (
			id BIGSERIAL PRIMARY KEY,
			started_at TIMESTAMP NOT NULL,
			ended_at TIMESTAMP,
			namespace TEXT NOT NULL,
			mode TEXT NOT NULL DEFAULT 'autonomous',
			status TEXT NOT NULL DEFAULT 'running',
			pod_count INTEGER DEFAULT 0,
			error_count INTEGER DEFAULT 0,
			fix_count INTEGER DEFAULT 0,
			report TEXT,
			log TEXT
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = conn.Exec(`
		CREATE TABLE IF NOT EXISTS fixes (
			id BIGSERIAL PRIMARY KEY,
			run_id BIGINT REFERENCES runs(id),
			timestamp TIMESTAMP NOT NULL,
			namespace TEXT NOT NULL,
			pod_name TEXT NOT NULL,
			error_type TEXT NOT NULL,
			error_message TEXT,
			fix_applied TEXT,
			status TEXT DEFAULT 'pending'
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = conn.Exec(`
		CREATE TABLE IF NOT EXISTS token_usage (
			id BIGSERIAL PRIMARY KEY,
			run_id BIGINT REFERENCES runs(id),
			namespace TEXT NOT NULL,
			model TEXT NOT NULL,
			input_tokens INTEGER DEFAULT 0,
			output_tokens INTEGER DEFAULT 0,
			total_tokens INTEGER DEFAULT 0,
			cost DOUBLE PRECISION DEFAULT 0,
			created_at TIMESTAMP NOT NULL
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = conn.Exec(`
		CREATE TABLE IF NOT EXISTS run_summaries (
			id BIGSERIAL PRIMARY KEY,
			parent_run_id BIGINT NOT NULL REFERENCES runs(id),
			started_at TIMESTAMP NOT NULL,
			ended_at TIMESTAMP,
			namespace TEXT NOT NULL,
			mode TEXT NOT NULL DEFAULT 'report',
			status TEXT NOT NULL,
			pod_count INTEGER DEFAULT 0,
			error_count INTEGER DEFAULT 0,
			fix_count INTEGER DEFAULT 0,
			summary TEXT
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = conn.Exec(`
		CREATE TABLE IF NOT EXISTS slack_sessions (
			thread_ts TEXT PRIMARY KEY,
			session_id TEXT NOT NULL,
			channel TEXT NOT NULL,
			namespace TEXT,
			created_at TIMESTAMP NOT NULL,
			updated_at TIMESTAMP NOT NULL
		)
	`)
	if err != nil {
		return nil, err
	}

	_, err = conn.Exec(`
		CREATE TABLE IF NOT EXISTS recovery_actions (
			id BIGSERIAL PRIMARY KEY,
			namespace TEXT NOT NULL,
			workload_kind TEXT NOT NULL,
			workload_name TEXT NOT NULL,
			pod_name TEXT,
			action TEXT NOT NULL,
			status TEXT NOT NULL,
			reason TEXT,
			created_at TIMESTAMP NOT NULL
		)
	`)
	if err != nil {
		return nil, err
	}

	return &DB{conn: conn, dialect: "postgres"}, nil
}
