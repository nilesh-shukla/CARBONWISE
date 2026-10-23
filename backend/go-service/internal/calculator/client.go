package calculator

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"strings"
	"time"

	"github.com/carbonwise/go-service/internal/appconfig"
)

type Request struct {
	Electricity *float64 `json:"electricity_kwh_per_month,omitempty"`
	LPG         *float64 `json:"lpg_kg_per_month,omitempty"`
	Petrol      *float64 `json:"petrol_litres_per_month,omitempty"`
	Diesel      *float64 `json:"diesel_litres_per_month,omitempty"`
	Region      *string  `json:"region,omitempty"`
}
type Response struct {
	ReportingPeriod       string                     `json:"reporting_period"`
	GasScope              string                     `json:"gas_scope"`
	Unit                  string                     `json:"unit"`
	CalculationStatus     string                     `json:"calculation_status"`
	TotalIsPartial        bool                       `json:"total_is_partial"`
	CalculatedCategories  []string                   `json:"calculated_categories"`
	ExcludedCategories    map[string]string          `json:"excluded_categories"`
	NotProvidedCategories []string                   `json:"not_provided_categories"`
	FootprintScopeNote    string                     `json:"footprint_scope_note"`
	Total                 float64                    `json:"total_emissions_kg_co2"`
	Direct                float64                    `json:"direct_emissions_kg_co2"`
	Indirect              float64                    `json:"indirect_emissions_kg_co2"`
	Categories            map[string]json.RawMessage `json:"categories"`
	FactorIDs             []string                   `json:"factor_ids"`
	Sources               []string                   `json:"sources"`
	Assumptions           []string                   `json:"assumptions"`
}
type Client struct {
	base string
	http *http.Client
}

type UpstreamStatusError struct {
	StatusCode int
}

func (e *UpstreamStatusError) Error() string {
	return fmt.Sprintf("calculator returned HTTP %d", e.StatusCode)
}

func New(c appconfig.Config) *Client {
	return &Client{base: strings.TrimRight(c.FastAPIURL, "/"), http: &http.Client{Timeout: 8 * time.Second}}
}
func (c *Client) Calculate(ctx context.Context, input json.RawMessage) (Response, json.RawMessage, error) {
	req, e := http.NewRequestWithContext(ctx, http.MethodPost, c.base+"/api/v1/calculate", bytes.NewReader(input))
	if e != nil {
		return Response{}, nil, e
	}
	req.Header.Set("Content-Type", "application/json")
	resp, e := c.http.Do(req)
	if e != nil {
		return Response{}, nil, fmt.Errorf("calculator unavailable: %w", e)
	}
	defer resp.Body.Close()
	body, e := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if e != nil {
		return Response{}, nil, fmt.Errorf("read calculator response: %w", e)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		// Upstream error bodies can echo user-supplied values, so retain only the
		// status code for safe diagnostics.
		return Response{}, nil, &UpstreamStatusError{StatusCode: resp.StatusCode}
	}
	var result Response
	if e = json.Unmarshal(body, &result); e != nil {
		return Response{}, nil, errors.New("calculator returned invalid JSON")
	}
	if !validResponse(result) {
		return Response{}, nil, errors.New("calculator response does not match the calculation contract")
	}
	return result, body, nil
}

func validResponse(r Response) bool {
	if r.ReportingPeriod != "monthly" || r.GasScope != "CO2" || r.Unit != "kgCO2/month" || (r.CalculationStatus != "complete_for_provided_inputs" && r.CalculationStatus != "partial") || !finite(r.Total) || !finite(r.Direct) || !finite(r.Indirect) || r.Categories == nil || len(r.Categories) != 4 || r.CalculatedCategories == nil || r.ExcludedCategories == nil || r.NotProvidedCategories == nil || r.FootprintScopeNote == "" || r.FactorIDs == nil || r.Sources == nil || r.Assumptions == nil {
		return false
	}
	if (r.CalculationStatus == "partial") != r.TotalIsPartial || (!r.TotalIsPartial && len(r.ExcludedCategories) != 0) {
		return false
	}
	for _, category := range []string{"electricity", "lpg", "petrol", "diesel"} {
		var entry struct {
			Status string `json:"status"`
		}
		if raw, ok := r.Categories[category]; !ok || json.Unmarshal(raw, &entry) != nil || (entry.Status != "calculated" && entry.Status != "not_calculated" && entry.Status != "not_provided") {
			return false
		}
	}
	return true
}
func ValidateRequest(raw json.RawMessage) (Request, error) {
	var r Request
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if e := d.Decode(&r); e != nil {
		return r, e
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		return r, errors.New("request must contain exactly one JSON object")
	}
	if r.Electricity == nil && r.LPG == nil && r.Petrol == nil && r.Diesel == nil {
		return r, errors.New("at least one consumption activity must be provided")
	}
	for _, v := range []*float64{r.Electricity, r.LPG, r.Petrol, r.Diesel} {
		if v != nil && (!finite(*v) || *v < 0) {
			return r, errors.New("activities must be finite non-negative numbers")
		}
	}
	if r.Region != nil && (len(*r.Region) > 100 || strings.TrimSpace(*r.Region) == "") {
		return r, errors.New("region must be a non-empty string up to 100 characters")
	}
	return r, nil
}
func finite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }
