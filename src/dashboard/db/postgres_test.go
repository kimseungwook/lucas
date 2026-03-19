package db

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to allocate free port: %v", err)
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port
}

type postgresHarness struct {
	port    int
	datadir string
	logfile string
}

func startPostgresHarness(t *testing.T) *postgresHarness {
	t.Helper()
	h := &postgresHarness{port: freePort(t)}
	base := t.TempDir()
	h.datadir = filepath.Join(base, "data")
	h.logfile = filepath.Join(base, "postgres.log")
	if err := os.MkdirAll(h.datadir, 0o755); err != nil {
		t.Fatalf("failed to create data dir: %v", err)
	}

	if out, err := exec.Command("initdb", "-D", h.datadir, "-U", "lucas", "-A", "trust").CombinedOutput(); err != nil {
		t.Fatalf("initdb failed: %v\n%s", err, string(out))
	}

	conf := filepath.Join(h.datadir, "postgresql.conf")
	f, err := os.OpenFile(conf, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatalf("failed to open postgres config: %v", err)
	}
	defer f.Close()
	if _, err := f.WriteString(fmt.Sprintf("\nport = %d\nlisten_addresses = '127.0.0.1'\n", h.port)); err != nil {
		t.Fatalf("failed to write postgres config: %v", err)
	}

	if out, err := exec.Command("pg_ctl", "-D", h.datadir, "-l", h.logfile, "start").CombinedOutput(); err != nil {
		t.Fatalf("pg_ctl start failed: %v\n%s", err, string(out))
	}

	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		if err := exec.Command("pg_isready", "-h", "127.0.0.1", "-p", fmt.Sprintf("%d", h.port), "-U", "lucas", "-d", "postgres").Run(); err == nil {
			break
		}
		time.Sleep(time.Second)
	}
	if out, err := exec.Command("createdb", "-h", "127.0.0.1", "-p", fmt.Sprintf("%d", h.port), "-U", "lucas", "lucas").CombinedOutput(); err != nil {
		t.Fatalf("createdb failed: %v\n%s", err, string(out))
	}

	t.Cleanup(func() {
		exec.Command("pg_ctl", "-D", h.datadir, "stop", "-m", "immediate").Run()
	})
	return h
}

func TestNewPostgresFromEnvAndQueries(t *testing.T) {
	h := startPostgresHarness(t)
	t.Setenv("POSTGRES_HOST", "127.0.0.1")
	t.Setenv("POSTGRES_PORT", fmt.Sprintf("%d", h.port))
	t.Setenv("POSTGRES_DB", "lucas")
	t.Setenv("POSTGRES_USER", "lucas")
	t.Setenv("POSTGRES_PASSWORD", "")
	t.Setenv("POSTGRES_SSLMODE", "disable")

	database, err := NewPostgresFromEnv()
	if err != nil {
		t.Fatalf("NewPostgresFromEnv failed: %v", err)
	}
	defer database.Close()

	_, err = database.conn.Exec(`INSERT INTO runs (started_at, namespace, mode, status, pod_count, error_count, fix_count, report, log)
		VALUES (NOW(), 'all', 'report', 'issues_found', 12, 2, 0, 'report body', 'log body')`)
	if err != nil {
		t.Fatalf("insert run failed: %v", err)
	}
	_, err = database.conn.Exec(`INSERT INTO run_summaries (parent_run_id, started_at, ended_at, namespace, mode, status, pod_count, error_count, fix_count, summary)
		VALUES (1, NOW(), NOW(), 'default', 'report', 'issues_found', 10, 2, 0, '2 issues')`)
	if err != nil {
		t.Fatalf("insert run summary failed: %v", err)
	}

	namespaces, err := database.GetNamespaces()
	if err != nil {
		t.Fatalf("GetNamespaces failed: %v", err)
	}
	if len(namespaces) != 1 || namespaces[0].Namespace != "default" {
		t.Fatalf("unexpected namespaces: %#v", namespaces)
	}

	runs, err := database.GetRuns("default", 10)
	if err != nil {
		t.Fatalf("GetRuns failed: %v", err)
	}
	if len(runs) != 1 || !runs[0].SummaryOnly || runs[0].ParentRunID != 1 {
		t.Fatalf("unexpected runs: %#v", runs)
	}

	run, err := database.GetRun(runs[0].ID)
	if err != nil {
		t.Fatalf("GetRun failed: %v", err)
	}
	if !run.SummaryOnly || run.SummaryText != "2 issues" {
		t.Fatalf("unexpected run detail: %#v", run)
	}
}
