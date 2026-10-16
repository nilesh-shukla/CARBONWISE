package calculator

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/carbonwise/go-service/internal/appconfig"
)

func TestValidateRequest(t *testing.T) {
	tests := []struct {
		name, body string
		valid      bool
	}{{"electricity", `{"electricity_kwh_per_month":10}`, true}, {"explicit zeros", `{"electricity_kwh_per_month":0,"lpg_kg_per_month":0}`, true}, {"empty", `{}`, false}, {"negative", `{"lpg_kg_per_month":-1}`, false}, {"extra", `{"lpg_kg_per_month":2,"extra":1}`, false}, {"nan", `{"lpg_kg_per_month":1e9999}`, false}}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, e := ValidateRequest(json.RawMessage(tt.body))
			if (e == nil) != tt.valid {
				t.Fatalf("error=%v, valid=%v", e, tt.valid)
			}
		})
	}
}
func TestCalculatePreservesResponseAndRejectsFailures(t *testing.T) {
	response := `{"reporting_period":"monthly","gas_scope":"CO2","unit":"kgCO2/month","calculation_status":"complete_for_provided_inputs","total_is_partial":false,"calculated_categories":["electricity"],"excluded_categories":{},"not_provided_categories":["lpg","petrol","diesel"],"footprint_scope_note":"scope","total_emissions_kg_co2":7.16,"direct_emissions_kg_co2":0,"indirect_emissions_kg_co2":7.16,"categories":{"electricity":{"status":"calculated"},"lpg":{"status":"not_provided"},"petrol":{"status":"not_provided"},"diesel":{"status":"not_provided"}},"factor_ids":["factor"],"sources":["source"],"assumptions":["assumption"]}`
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/calculate" {
			t.Errorf("path = %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(response))
	}))
	defer server.Close()
	c := New(appconfig.Config{FastAPIURL: server.URL})
	result, raw, e := c.Calculate(context.Background(), json.RawMessage(`{"electricity_kwh_per_month":10}`))
	if e != nil {
		t.Fatal(e)
	}
	if result.Total != 7.16 || len(raw) == 0 {
		t.Fatalf("unexpected response: %#v", result)
	}
	failing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Error(w, "failed", 503) }))
	defer failing.Close()
	c = New(appconfig.Config{FastAPIURL: failing.URL})
	if _, _, e = c.Calculate(context.Background(), json.RawMessage(`{}`)); e == nil {
		t.Fatal("upstream failure accepted")
	}
}
