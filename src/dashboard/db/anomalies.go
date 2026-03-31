package db

import (
	"encoding/json"
	"strings"
)

type AnomalySummary struct {
	HasIncidents bool
	Incidents    []string

	HasDrift bool
	Drifts   []string

	HasRedis bool
	Redis    []string

	HasSecurity bool
	Security    []string
}

func (r Run) ParseAnomalies() AnomalySummary {
	var summary AnomalySummary

	// Report might be empty or in SummaryText
	content := r.Report
	if content == "" {
		content = r.SummaryText
	}

	if content == "" || !strings.HasPrefix(strings.TrimSpace(content), "{") {
		return summary
	}

	var data map[string]interface{}
	if err := json.Unmarshal([]byte(content), &data); err != nil {
		return summary
	}

	// Helper to extract list of strings
	extractStrings := func(key string) []string {
		var res []string
		if val, ok := data[key].([]interface{}); ok {
			for _, v := range val {
				if str, ok := v.(string); ok {
					res = append(res, str)
				} else if obj, ok := v.(map[string]interface{}); ok {
					s := formatAnomalyObj(obj)
					if s != "" {
						res = append(res, s)
					}
				}
			}
		}
		return res
	}

	extractSummary := func(key string) string {
		if val, ok := data[key]; ok {
			if str, ok := val.(string); ok {
				return str
			} else if obj, ok := val.(map[string]interface{}); ok {
				return formatAnomalyObj(obj)
			}
		}
		return ""
	}

	summary.Incidents = extractStrings("pod_incident_findings")
	if len(summary.Incidents) > 0 {
		summary.HasIncidents = true
	} else if v := extractSummary("pod_incident_summary"); v != "" {
		summary.HasIncidents = true
		summary.Incidents = []string{v}
	}

	summary.Drifts = extractStrings("drifts")
	if len(summary.Drifts) > 0 {
		summary.HasDrift = true
	} else if v := extractSummary("drift_summary"); v != "" {
		summary.HasDrift = true
		summary.Drifts = []string{v}
	}

	summary.Redis = extractStrings("redis_recovery_findings")
	if len(summary.Redis) > 0 {
		summary.HasRedis = true
	} else if v := extractSummary("redis_recovery_summary"); v != "" {
		summary.HasRedis = true
		summary.Redis = []string{v}
	}

	summary.Security = extractStrings("security_suspicion_findings")
	if len(summary.Security) > 0 {
		summary.HasSecurity = true
	} else if v := extractSummary("security_suspicion_summary"); v != "" {
		summary.HasSecurity = true
		summary.Security = []string{v}
	}

	return summary
}

func formatAnomalyObj(obj map[string]interface{}) string {
	var parts []string

	if sev, ok := obj["severity"].(string); ok && sev != "" {
		parts = append(parts, "["+strings.ToUpper(sev)+"]")
	}

	if typ, ok := obj["type"].(string); ok && typ != "" {
		parts = append(parts, typ)
	} else if cat, ok := obj["category"].(string); ok && cat != "" {
		parts = append(parts, cat)
	}

	var target []string
	for _, k := range []string{"namespace", "workload", "pod", "resource"} {
		if v, ok := obj[k].(string); ok && v != "" {
			target = append(target, v)
		}
	}
	if len(target) > 0 {
		parts = append(parts, "("+strings.Join(target, "/")+")")
	}

	var detail string
	for _, k := range []string{"likely_cause", "reason", "status", "action", "summary", "message"} {
		if v, ok := obj[k].(string); ok && v != "" {
			detail = v
			break
		}
	}
	if detail != "" {
		parts = append(parts, detail)
	}

	if len(parts) > 0 {
		return strings.Join(parts, " ")
	}

	var fallbacks []string
	for k, v := range obj {
		if str, ok := v.(string); ok && str != "" {
			fallbacks = append(fallbacks, k+":"+str)
		}
	}
	if len(fallbacks) > 0 {
		return strings.Join(fallbacks, ", ")
	}

	b, _ := json.Marshal(obj)
	return string(b)
}

func (r Run) HasAnomaly(filter string) bool {
	if filter == "" || filter == "all" {
		return true
	}
	a := r.ParseAnomalies()
	switch filter {
	case "incidents":
		return a.HasIncidents
	case "drift":
		return a.HasDrift
	case "redis":
		return a.HasRedis
	case "security":
		return a.HasSecurity
	}
	return true
}

type AnomalyCounts struct {
	TotalRuns int
	Incidents int
	Drift     int
	Redis     int
	Security  int
}

func GetAnomalyCounts(runs []Run) AnomalyCounts {
	var counts AnomalyCounts
	counts.TotalRuns = len(runs)
	for _, r := range runs {
		a := r.ParseAnomalies()
		if a.HasIncidents {
			counts.Incidents++
		}
		if a.HasDrift {
			counts.Drift++
		}
		if a.HasRedis {
			counts.Redis++
		}
		if a.HasSecurity {
			counts.Security++
		}
	}
	return counts
}

// Helper to filter runs
func FilterRunsByAnomaly(runs []Run, filter string) []Run {
	if filter == "" || filter == "all" {
		return runs
	}
	var filtered []Run
	for _, r := range runs {
		if r.HasAnomaly(filter) {
			filtered = append(filtered, r)
		}
	}
	return filtered
}
