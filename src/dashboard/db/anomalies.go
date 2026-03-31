package db

import (
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
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

type AttentionItem struct {
	Namespace      string
	Pod            string
	Phase          string
	Reason         string
	Issue          string
	Severity       string
	Restarts       int
	Source         string
	Recommendation string
}

func (r Run) ParseAnomalies() AnomalySummary {
	var summary AnomalySummary

	data, ok := r.parseReportData()
	if !ok {
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

func (r Run) ParseAttentionItems() []AttentionItem {
	data, ok := r.parseReportData()
	if !ok {
		return nil
	}

	itemsByKey := map[string]*AttentionItem{}

	mergeItem := func(item AttentionItem) {
		key := attentionKey(item)
		if key == "" {
			return
		}
		existing, exists := itemsByKey[key]
		if !exists {
			copied := item
			itemsByKey[key] = &copied
			return
		}
		mergeAttentionItem(existing, item)
	}

	for _, item := range extractAttentionFromTopProblematicPods(data) {
		mergeItem(item)
	}
	for _, item := range extractAttentionFromDetails(data) {
		mergeItem(item)
	}
	for _, item := range extractAttentionFromPodIncidents(data) {
		mergeItem(item)
	}

	items := make([]AttentionItem, 0, len(itemsByKey))
	for _, item := range itemsByKey {
		items = append(items, *item)
	}

	sort.SliceStable(items, func(i, j int) bool {
		left := items[i]
		right := items[j]

		if severityRank(left.Severity) != severityRank(right.Severity) {
			return severityRank(left.Severity) > severityRank(right.Severity)
		}
		if left.Restarts != right.Restarts {
			return left.Restarts > right.Restarts
		}
		if (left.Issue != "") != (right.Issue != "") {
			return left.Issue != ""
		}
		if left.Namespace != right.Namespace {
			return left.Namespace < right.Namespace
		}
		return left.Pod < right.Pod
	})

	return items
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

func (r Run) parseReportData() (map[string]interface{}, bool) {
	content := r.Report
	if content == "" {
		content = r.SummaryText
	}
	if content == "" || !strings.HasPrefix(strings.TrimSpace(content), "{") {
		return nil, false
	}

	var data map[string]interface{}
	if err := json.Unmarshal([]byte(content), &data); err != nil {
		return nil, false
	}
	return data, true
}

func extractAttentionFromTopProblematicPods(data map[string]interface{}) []AttentionItem {
	var items []AttentionItem
	for _, obj := range extractObjects(data, "top_problematic_pods") {
		namespace, pod := splitNamespacePod(asString(obj["namespace"]), asString(obj["pod"]))
		if pod == "" {
			continue
		}
		items = append(items, AttentionItem{
			Namespace: namespace,
			Pod:       pod,
			Phase:     asString(obj["phase"]),
			Reason:    asString(obj["reason"]),
			Restarts:  asInt(obj["restarts"]),
			Source:    "top_problematic_pods",
		})
	}
	return items
}

func extractAttentionFromDetails(data map[string]interface{}) []AttentionItem {
	var items []AttentionItem
	for _, obj := range extractObjects(data, "details") {
		namespace, pod := splitNamespacePod("", asString(obj["pod"]))
		if pod == "" {
			continue
		}
		items = append(items, AttentionItem{
			Namespace:      namespace,
			Pod:            pod,
			Issue:          asString(obj["issue"]),
			Severity:       asString(obj["severity"]),
			Recommendation: firstNonEmpty(asString(obj["recommendation"]), asString(obj["likely_cause"])),
			Source:         "details",
		})
	}
	return items
}

func extractAttentionFromPodIncidents(data map[string]interface{}) []AttentionItem {
	var items []AttentionItem
	for _, obj := range extractObjects(data, "pod_incident_findings") {
		namespace := asString(obj["namespace"])
		pod := asString(obj["pod"])
		resource := asString(obj["resource"])
		resNamespace, resPod := parsePodResource(resource)
		if namespace == "" {
			namespace = resNamespace
		}
		if pod == "" {
			pod = resPod
		}
		namespace, pod = splitNamespacePod(namespace, pod)
		if pod == "" {
			continue
		}

		issue := firstNonEmpty(asString(obj["category"]), asString(obj["type"]))
		items = append(items, AttentionItem{
			Namespace:      namespace,
			Pod:            pod,
			Reason:         asString(obj["reason"]),
			Issue:          issue,
			Severity:       asString(obj["severity"]),
			Recommendation: firstNonEmpty(asString(obj["likely_cause"]), asString(obj["message"]), asString(obj["summary"])),
			Source:         "pod_incident_findings",
		})
	}
	return items
}

func extractObjects(data map[string]interface{}, key string) []map[string]interface{} {
	arr, ok := data[key].([]interface{})
	if !ok {
		return nil
	}
	res := make([]map[string]interface{}, 0, len(arr))
	for _, item := range arr {
		obj, ok := item.(map[string]interface{})
		if ok {
			res = append(res, obj)
		}
	}
	return res
}

func mergeAttentionItem(dst *AttentionItem, src AttentionItem) {
	if dst.Namespace == "" {
		dst.Namespace = src.Namespace
	}
	if dst.Pod == "" {
		dst.Pod = src.Pod
	}
	if dst.Phase == "" {
		dst.Phase = src.Phase
	}
	if dst.Reason == "" {
		dst.Reason = src.Reason
	}
	if dst.Issue == "" {
		dst.Issue = src.Issue
	}
	if severityRank(src.Severity) > severityRank(dst.Severity) {
		dst.Severity = src.Severity
	}
	if src.Restarts > dst.Restarts {
		dst.Restarts = src.Restarts
	}
	if dst.Recommendation == "" {
		dst.Recommendation = src.Recommendation
	}
	if dst.Source == "" {
		dst.Source = src.Source
	} else if src.Source != "" && !strings.Contains(dst.Source, src.Source) {
		dst.Source += ", " + src.Source
	}
}

func attentionKey(item AttentionItem) string {
	if item.Pod == "" {
		return ""
	}
	return strings.ToLower(strings.TrimSpace(item.Namespace) + "/" + strings.TrimSpace(item.Pod))
}

func severityRank(value string) int {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "critical":
		return 4
	case "high":
		return 3
	case "medium":
		return 2
	case "low":
		return 1
	default:
		return 0
	}
}

func asString(v interface{}) string {
	switch typed := v.(type) {
	case string:
		return strings.TrimSpace(typed)
	case fmt.Stringer:
		return strings.TrimSpace(typed.String())
	default:
		return ""
	}
}

func asInt(v interface{}) int {
	switch typed := v.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case string:
		n, err := strconv.Atoi(strings.TrimSpace(typed))
		if err == nil {
			return n
		}
	}
	return 0
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func splitNamespacePod(namespace string, pod string) (string, string) {
	namespace = strings.TrimSpace(namespace)
	pod = strings.TrimSpace(pod)
	if pod == "" {
		return namespace, ""
	}
	parts := strings.Split(pod, "/")
	if namespace == "" && len(parts) == 2 {
		return parts[0], parts[1]
	}
	if len(parts) > 1 {
		return namespace, parts[len(parts)-1]
	}
	return namespace, pod
}

func parsePodResource(resource string) (string, string) {
	resource = strings.TrimSpace(strings.ToLower(resource))
	if resource == "" {
		return "", ""
	}

	parts := strings.Split(resource, "/")
	switch len(parts) {
	case 2:
		if parts[0] == "pod" {
			return "", parts[1]
		}
	case 3:
		if parts[1] == "pod" {
			return parts[0], parts[2]
		}
	}
	return "", ""
}
