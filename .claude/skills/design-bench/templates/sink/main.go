// sink stands in for every outside dependency of the design under test (a
// customer's endpoint, a payment API, a game server fleet) and keeps the ledger
// of what reached it. It is the place where "on time", "not lost" and "not
// twice" are measured: at the receiver, where a client would observe them.
//
// Each request says how the sink should behave, so the mix of fast, slow, flaky
// and dead dependencies is part of the seeded workload, not of the sink:
//
//	/do?ms=150&p99=900     service time: median 150 ms, 99% within 900 ms (log-normal)
//	/do?fail=0.3&status=503  30% of calls are refused before the work is done
//	/do?drop=0.01          1% of calls do the work, then close without a reply
//	/do?hang=0.01          1% of calls never reply (held until the caller gives up)
//	/do?idem=1             behave as an idempotent receiver: a repeated key is not done twice
//
// Identity and timing come as query fields or headers:
//
//	key   / X-Bench-Key    the id the design promises to run once (a run, a ticket, a message)
//	due   / X-Bench-Due    when it was due, Unix milliseconds; delay = arrival - due
//	class / X-Bench-Class  a label to group by (priority, tenant)
//
// Read the ledger with GET /stats (optionally ?from=&to= in Unix ms, by arrival),
// GET /dump (CSV of every arrival) and clear it with POST /reset.
package main

import (
	"encoding/json"
	"fmt"
	"math"
	"math/rand/v2"
	"net/http"
	"os"
	"sort"
	"strconv"
	"sync"
	"time"
)

type arrival struct {
	at      int64 // Unix ms, taken when the request arrived
	due     int64 // Unix ms, 0 when not given
	key     string
	class   string
	outcome string // done, refused, dropped, hung, deduped
}

type ledger struct {
	mu       sync.Mutex
	arrivals []arrival
	effects  map[string]int // key -> times the work was done
	calls    map[string]int // key -> times it was called
}

var led = &ledger{effects: map[string]int{}, calls: map[string]int{}}

func field(r *http.Request, name, header string) string {
	if v := r.URL.Query().Get(name); v != "" {
		return v
	}
	return r.Header.Get(header)
}

func num(r *http.Request, name string, def float64) float64 {
	v, err := strconv.ParseFloat(r.URL.Query().Get(name), 64)
	if err != nil {
		return def
	}
	return v
}

// serviceTime draws from a log-normal with the given median and 99th percentile.
func serviceTime(median, p99 float64) time.Duration {
	if median <= 0 {
		return 0
	}
	ms := median
	if p99 > median {
		sigma := math.Log(p99/median) / 2.326
		ms = median * math.Exp(sigma*rand.NormFloat64())
	}
	if ms > 300000 {
		ms = 300000
	}
	return time.Duration(ms * float64(time.Millisecond))
}

func do(w http.ResponseWriter, r *http.Request) {
	a := arrival{at: time.Now().UnixMilli(), key: field(r, "key", "X-Bench-Key"), class: field(r, "class", "X-Bench-Class")}
	a.due, _ = strconv.ParseInt(field(r, "due", "X-Bench-Due"), 10, 64)
	record := func(outcome string) {
		a.outcome = outcome
		led.mu.Lock()
		led.arrivals = append(led.arrivals, a)
		if a.key != "" {
			led.calls[a.key]++
			if outcome == "done" || outcome == "dropped" {
				led.effects[a.key]++
			}
		}
		led.mu.Unlock()
	}

	if rand.Float64() < num(r, "fail", 0) {
		record("refused")
		http.Error(w, "refused", int(num(r, "status", 503)))
		return
	}
	if rand.Float64() < num(r, "hang", 0) {
		record("hung")
		select {
		case <-r.Context().Done():
		case <-time.After(5 * time.Minute):
		}
		return
	}
	if num(r, "idem", 0) > 0 && a.key != "" {
		led.mu.Lock()
		seen := led.effects[a.key] > 0
		led.mu.Unlock()
		if seen {
			record("deduped")
			fmt.Fprintln(w, "ok (already done)")
			return
		}
	}
	select {
	case <-time.After(serviceTime(num(r, "ms", 0), num(r, "p99", 0))):
	case <-r.Context().Done():
		// The caller gave up; the work is still done, as it would be at a real endpoint.
	}
	if rand.Float64() < num(r, "drop", 0) {
		record("dropped")
		if hj, ok := w.(http.Hijacker); ok {
			if c, _, err := hj.Hijack(); err == nil {
				c.Close()
			}
		}
		return
	}
	record("done")
	fmt.Fprintln(w, "ok")
}

func pct(sorted []int64, p float64) int64 {
	if len(sorted) == 0 {
		return 0
	}
	i := int(math.Ceil(p*float64(len(sorted)))) - 1
	if i < 0 {
		i = 0
	}
	return sorted[i]
}

type delays struct {
	N    int   `json:"n"`
	P50  int64 `json:"p50_ms"`
	P90  int64 `json:"p90_ms"`
	P95  int64 `json:"p95_ms"`
	P99  int64 `json:"p99_ms"`
	P999 int64 `json:"p999_ms"`
	Max  int64 `json:"max_ms"`
}

func summarize(d []int64) delays {
	sort.Slice(d, func(i, j int) bool { return d[i] < d[j] })
	return delays{len(d), pct(d, .50), pct(d, .90), pct(d, .95), pct(d, .99), pct(d, .999), pct(d, 1)}
}

func stats(w http.ResponseWriter, r *http.Request) {
	from, _ := strconv.ParseInt(r.URL.Query().Get("from"), 10, 64)
	to, _ := strconv.ParseInt(r.URL.Query().Get("to"), 10, 64)
	led.mu.Lock()
	defer led.mu.Unlock()

	outcomes := map[string]int{}
	byClass := map[string][]int64{}
	perSecond := map[int64]int{}
	var all []int64
	calls, effects := map[string]int{}, map[string]int{}
	n := 0
	for _, a := range led.arrivals {
		if (from > 0 && a.at < from) || (to > 0 && a.at >= to) {
			continue
		}
		n++
		outcomes[a.outcome]++
		perSecond[a.at/1000]++
		if a.key != "" {
			calls[a.key]++
			if a.outcome == "done" || a.outcome == "dropped" {
				effects[a.key]++
			}
		}
		// Delay is the first arrival of a key against its due time; retries are not late starts.
		if a.due > 0 && (a.key == "" || calls[a.key] == 1) {
			all = append(all, a.at-a.due)
			byClass[a.class] = append(byClass[a.class], a.at-a.due)
		}
	}
	dupEffects, keysDone, peak := 0, 0, 0
	for _, e := range effects {
		keysDone++
		dupEffects += e - 1
	}
	for _, c := range perSecond {
		if c > peak {
			peak = c
		}
	}
	classes := map[string]delays{}
	for c, d := range byClass {
		classes[c] = summarize(d)
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"calls":              n,
		"outcomes":           outcomes,
		"keys":               len(calls),
		"keys_done":          keysDone,
		"keys_never_done":    len(calls) - keysDone,
		"duplicate_effects":  dupEffects,
		"peak_calls_per_s":   peak,
		"seconds_with_calls": len(perSecond),
		"delay":              summarize(all),
		"delay_by_class":     classes,
	})
}

func dump(w http.ResponseWriter, r *http.Request) {
	led.mu.Lock()
	defer led.mu.Unlock()
	w.Header().Set("Content-Type", "text/csv")
	fmt.Fprintln(w, "arrived_ms,due_ms,key,class,outcome")
	for _, a := range led.arrivals {
		fmt.Fprintf(w, "%d,%d,%s,%s,%s\n", a.at, a.due, a.key, a.class, a.outcome)
	}
}

func reset(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	led.mu.Lock()
	led.arrivals, led.effects, led.calls = nil, map[string]int{}, map[string]int{}
	led.mu.Unlock()
	fmt.Fprintln(w, "reset")
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	http.HandleFunc("/do", do)
	http.HandleFunc("/do/", do)
	http.HandleFunc("/stats", stats)
	http.HandleFunc("/dump", dump)
	http.HandleFunc("/reset", reset)
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { fmt.Fprintln(w, "ok") })
	srv := &http.Server{Addr: ":" + port, ReadHeaderTimeout: 10 * time.Second}
	fmt.Println("sink listening on :" + port)
	if err := srv.ListenAndServe(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
