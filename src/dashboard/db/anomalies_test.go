package db

import (
	"testing"
)

func TestParseAnomalies(t *testing.T) {
	tests := []struct {
		name     string
		run      Run
		expected AnomalySummary
	}{
		{
			name: "empty report",
			run: Run{
				Report: "",
			},
			expected: AnomalySummary{},
		},
		{
			name: "invalid json report",
			run: Run{
				Report: "not json",
			},
			expected: AnomalySummary{},
		},
		{
			name: "incident summary only",
			run: Run{
				Report: `{"pod_incident_summary": "1 incident"}`,
			},
			expected: AnomalySummary{
				HasIncidents: true,
				Incidents:    []string{"1 incident"},
			},
		},
		{
			name: "incident findings array",
			run: Run{
				Report: `{"pod_incident_findings": ["crash loop", "oom"]}`,
			},
			expected: AnomalySummary{
				HasIncidents: true,
				Incidents:    []string{"crash loop", "oom"},
			},
		},
		{
			name: "incident findings objects",
			run: Run{
				Report: `{"pod_incident_findings": [{"severity": "high", "type": "CrashLoopBackOff", "namespace": "default", "pod": "my-pod", "likely_cause": "OOMKilled"}]}`,
			},
			expected: AnomalySummary{
				HasIncidents: true,
				Incidents:    []string{"[HIGH] CrashLoopBackOff (default/my-pod) OOMKilled"},
			},
		},
		{
			name: "incident summary object",
			run: Run{
				Report: `{"pod_incident_summary": {"status": "Unhealthy", "message": "Cluster is on fire"}}`,
			},
			expected: AnomalySummary{
				HasIncidents: true,
				Incidents:    []string{"Unhealthy"},
			},
		},
		{
			name: "multiple anomalies",
			run: Run{
				Report: `{"drifts": ["drift 1"], "security_suspicion_summary": "hack"}`,
			},
			expected: AnomalySummary{
				HasDrift:    true,
				Drifts:      []string{"drift 1"},
				HasSecurity: true,
				Security:    []string{"hack"},
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			result := tc.run.ParseAnomalies()
			if result.HasIncidents != tc.expected.HasIncidents {
				t.Errorf("expected HasIncidents %v, got %v", tc.expected.HasIncidents, result.HasIncidents)
			}
			if len(result.Incidents) != len(tc.expected.Incidents) {
				t.Errorf("expected %v incidents, got %v", len(tc.expected.Incidents), len(result.Incidents))
			}
			if result.HasDrift != tc.expected.HasDrift {
				t.Errorf("expected HasDrift %v, got %v", tc.expected.HasDrift, result.HasDrift)
			}
			if len(result.Drifts) != len(tc.expected.Drifts) {
				t.Errorf("expected %v drifts, got %v", len(tc.expected.Drifts), len(result.Drifts))
			}
			if result.HasSecurity != tc.expected.HasSecurity {
				t.Errorf("expected HasSecurity %v, got %v", tc.expected.HasSecurity, result.HasSecurity)
			}
			if len(result.Security) != len(tc.expected.Security) {
				t.Errorf("expected %v security, got %v", len(tc.expected.Security), len(result.Security))
			}
		})
	}
}

func TestFilterRunsByAnomaly(t *testing.T) {
	runs := []Run{
		{ID: 1, Report: `{"pod_incident_findings": ["x"]}`},
		{ID: 2, Report: `{"drifts": ["y"]}`},
		{ID: 3, Report: `{}`},
	}

	res := FilterRunsByAnomaly(runs, "all")
	if len(res) != 3 {
		t.Errorf("expected 3, got %v", len(res))
	}

	res = FilterRunsByAnomaly(runs, "incidents")
	if len(res) != 1 || res[0].ID != 1 {
		t.Errorf("expected 1 run with ID 1, got %v", res)
	}

	res = FilterRunsByAnomaly(runs, "drift")
	if len(res) != 1 || res[0].ID != 2 {
		t.Errorf("expected 1 run with ID 2, got %v", res)
	}

	res = FilterRunsByAnomaly(runs, "security")
	if len(res) != 0 {
		t.Errorf("expected 0, got %v", len(res))
	}
}

func TestGetAnomalyCounts(t *testing.T) {
	runs := []Run{
		{ID: 1, Report: `{"pod_incident_findings": ["x"], "drifts": ["y"]}`},
		{ID: 2, Report: `{"drifts": ["y"]}`},
		{ID: 3, Report: `{"redis_recovery_summary": "z"}`},
		{ID: 4, Report: `{}`},
	}

	counts := GetAnomalyCounts(runs)
	if counts.TotalRuns != 4 {
		t.Errorf("expected 4 total, got %v", counts.TotalRuns)
	}
	if counts.Incidents != 1 {
		t.Errorf("expected 1 incident, got %v", counts.Incidents)
	}
	if counts.Drift != 2 {
		t.Errorf("expected 2 drift, got %v", counts.Drift)
	}
	if counts.Redis != 1 {
		t.Errorf("expected 1 redis, got %v", counts.Redis)
	}
	if counts.Security != 0 {
		t.Errorf("expected 0 security, got %v", counts.Security)
	}
}
