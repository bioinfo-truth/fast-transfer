package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"
)

func sampleFixture() expectedSample {
	x := sha256.Sum256([]byte("3003"))
	e := expectedSample{Task: "job-" + strings.Repeat("a", 32), Account: "sha256:" + hex.EncodeToString(x[:]), Application: "Xtransfer", FSID: "4004", Path: "/apps/Xtransfer/mvp-validation/job-" + strings.Repeat("a", 32) + "/" + sampleName, Size: sampleSize, MD5: sampleMD5, SHA256: sampleSHA}
	e.Mapping = hashJSON(e.fields())
	return e
}
func planFixture(t *testing.T) (sharePlan, *os.File, *os.File, *os.File) {
	dir := t.TempDir()
	if e := os.Chmod(dir, 0700); e != nil {
		t.Fatal(e)
	}
	d, e := os.Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	r, w, e := os.Pipe()
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { d.Close(); r.Close(); w.Close() })
	return sharePlan{Sample: sampleFixture(), Period: 7, Code: "a1b2", AllowHistory: true, IntentFD: int(d.Fd()), ResultFD: int(w.Fd())}, d, r, w
}

type shareRT struct {
	base  *fakeRT
	t     *testing.T
	plan  sharePlan
	posts int
	mode  string
}

const fakeLink = "https://pan.baidu.com/s/SYNTHETIC_LINK_ONLY"

func (f *shareRT) RoundTrip(r *http.Request) (*http.Response, error) {
	if !strings.HasPrefix(r.URL.Path, "/share/") && r.URL.Path != "/api/list" {
		return f.base.RoundTrip(r)
	}
	if !permitted(r.Method, r.URL) || r.Header.Get("Cookie") != "BDUSS=SYNTHETIC_SESSION_ONLY" {
		f.t.Fatal("unsafe workflow request")
	}
	text := ""
	switch r.URL.Path {
	case "/api/list":
		md := sampleMD5
		if f.mode == "bad_object" {
			md = strings.Repeat("0", 32)
		}
		data, _ := json.Marshal(map[string]interface{}{"errno": 0, "list": []interface{}{map[string]interface{}{"fs_id": 4004, "path": f.plan.Sample.Path, "size": sampleSize, "isdir": 0, "md5": md}}})
		text = string(data)
	case "/share/pset":
		f.posts++
		data, _ := io.ReadAll(r.Body)
		if strings.Contains(string(data), "SYNTHETIC_PASSWORD") {
			f.t.Fatal("password reused")
		}
		if f.mode == "timeout" {
			return nil, rejected
		}
		if f.mode == "api_reject" {
			text = `{"errno":-6}`
			break
		}
		text = `{"errno":0,"shareid":5005,"link":"` + fakeLink + `"}`
	case "/share/record":
		id := 4004
		if f.mode == "wrong_mapping" {
			id = 9999
		}
		data, _ := json.Marshal(map[string]interface{}{"errno": 0, "list": []interface{}{map[string]interface{}{"shareId": 5005, "fsIds": []int{id}, "typicalPath": f.plan.Sample.Path, "shortlink": fakeLink, "public": 0, "expiredType": 7, "expiredTime": 604799}}})
		text = string(data)
	case "/share/surlinfoinrecord":
		pwd := f.plan.Code
		if f.mode == "wrong_password" {
			pwd = "z9z9"
		}
		text = `{"errno":0,"pwd":"` + pwd + `","shorturl":"unused"}`
	default:
		f.t.Fatal("unreviewed path")
	}
	return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(text)), Request: r}, nil
}
func shareSession(t *testing.T, p sharePlan, mode string) (*session, *shareRT) {
	s, b := fixture(t)
	f := &shareRT{base: b, t: t, plan: p, mode: mode}
	s.client.Transport = f
	return s, f
}
func TestWorkflowSameLoginExactObjectAndPrivateDelivery(t *testing.T) {
	p, d, r, w := planFixture(t)
	s, f := shareSession(t, p, "")
	in := credentials()
	in.Share = &p
	result := s.runShare(context.Background(), in)
	w.Close()
	raw, _ := io.ReadAll(r)
	if !result.PrivateReady || !result.RecordMatched || !result.PasswordConfirmed || !result.ExpiryBounded || f.posts != 1 || result.AuthPosts != 1 || result.ShareRequests != 1 || !result.ExpectedMatch || result.RecipientAccessVerified {
		t.Fatalf("bad workflow %+v", result)
	}
	if !strings.Contains(string(raw), fakeLink) || !strings.Contains(string(raw), p.Code) {
		t.Fatal("private result missing")
	}
	reportBytes, _ := json.Marshal(result)
	for _, secret := range []string{fakeLink, p.Code, "SYNTHETIC_SESSION_ONLY"} {
		if strings.Contains(string(reportBytes), secret) {
			t.Fatal("public result leaked")
		}
	}
	record, e := os.ReadFile(d.Name() + "/" + p.Sample.key() + ".json")
	if e != nil {
		t.Fatal(e)
	}
	for _, secret := range []string{fakeLink, p.Code, "SYNTHETIC_SESSION_ONLY", p.Sample.Path} {
		if strings.Contains(string(record), secret) {
			t.Fatal("intent stored secret/private path")
		}
	}
}
func TestWorkflowFailureOrderingAndNoUnverifiedDelivery(t *testing.T) {
	for _, mode := range []string{"bad_object", "timeout", "wrong_mapping", "wrong_password", "api_reject"} {
		p, _, r, w := planFixture(t)
		s, f := shareSession(t, p, mode)
		in := credentials()
		in.Share = &p
		result := s.runShare(context.Background(), in)
		w.Close()
		raw, _ := io.ReadAll(r)
		if result.PrivateReady || len(raw) != 0 {
			t.Fatal("unverified link delivered")
		}
		if mode == "bad_object" && f.posts != 0 {
			t.Fatal("wrong object shared")
		}
		if mode != "bad_object" && f.posts != 1 {
			t.Fatal("bad attempt count")
		}
		if mode == "timeout" && !result.CreationUnknown {
			t.Fatal("unknown lost")
		}
		if mode == "api_reject" && (result.CreationUnknown || result.Status != "share_creation_rejected") {
			t.Fatal("API denial misclassified")
		}
	}
}
func TestWorkflowConsumedIntentPreventsSecondLogin(t *testing.T) {
	p, _, _, _ := planFixture(t)
	s, _ := shareSession(t, p, "timeout")
	in := credentials()
	in.Share = &p
	s.runShare(context.Background(), in)
	next, f := shareSession(t, p, "")
	r := next.runShare(context.Background(), in)
	if r.Status != "share_intent_already_consumed_no_login" || len(f.base.calls) != 0 || f.posts != 0 {
		t.Fatal("relogin or replay")
	}
}
func TestWorkflowRequiresConsentAndTrustedJoinedExpectation(t *testing.T) {
	p, _, _, _ := planFixture(t)
	for _, kind := range []string{"history", "mapping", "path", "period", "code"} {
		bad := p
		switch kind {
		case "history":
			bad.AllowHistory = false
		case "mapping":
			bad.Sample.Mapping = strings.Repeat("0", 64)
		case "path":
			bad.Sample.Path = "/apps/Xtransfer/other"
		case "period":
			bad.Period = 0
		case "code":
			bad.Code = "ABCD"
		}
		s, f := shareSession(t, bad, "")
		in := credentials()
		in.Share = &bad
		r := s.runShare(context.Background(), in)
		if r.AuthPosts != 0 || len(f.base.calls) != 0 || r.Status != "share_plan_rejected_no_login" {
			t.Fatal("invalid preflight reached credentials")
		}
	}
}
func TestWorkflowLedgerLockAndExistingNonregularRecord(t *testing.T) {
	p, d, _, _ := planFixture(t)
	l, e := openLedger(p)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = openLedger(p); e == nil {
		t.Fatal("concurrent lock accepted")
	}
	l.close()
	if e = os.Symlink("/synthetic-no-read", d.Name()+"/"+p.Sample.key()+".json"); e != nil {
		t.Fatal(e)
	}
	if _, e = openLedger(p); e == nil {
		t.Fatal("symlink accepted")
	}
}
func TestWorkflowRecordRejectsDuplicateOrUnexpectedFileSet(t *testing.T) {
	p, _, _, _ := planFixture(t)
	valid := map[string]interface{}{"shareId": 5005, "fsIds": []int{4004}, "typicalPath": p.Sample.Path, "shortlink": fakeLink, "public": 0, "expiredType": 7, "expiredTime": 604799}
	for _, key := range []string{"fsIds", "shortlink", "public", "expiredTime"} {
		bad := map[string]interface{}{}
		for k, v := range valid {
			bad[k] = v
		}
		switch key {
		case "fsIds":
			bad[key] = []int{4004, 4005}
		case "shortlink":
			bad[key] = "https://other.invalid/x"
		case "public":
			bad[key] = 1
		case "expiredTime":
			bad[key] = 0
		}
		raw, _ := json.Marshal(map[string]interface{}{"errno": 0, "list": []interface{}{bad}})
		if matchRecord(raw, p, "5005", fakeLink, time.Second) {
			t.Fatal("bad mapping accepted")
		}
	}
	raw, _ := json.Marshal(map[string]interface{}{"errno": 0, "list": []interface{}{valid, valid}})
	if matchRecord(raw, p, "5005", fakeLink, time.Second) {
		t.Fatal("duplicate accepted")
	}
}
func TestWorkflowProcessLedgerChild(t *testing.T) {
	if os.Getenv("FT_SYNTHETIC_LEDGER_CHILD") != "1" {
		return
	}
	p := sharePlan{Sample: sampleFixture(), IntentFD: 3, ResultFD: 4}
	if _, e := openLedger(p); e != consumed {
		os.Exit(4)
	}
}
func TestWorkflowConsumedIntentSurvivesFreshProcess(t *testing.T) {
	p, d, _, w := planFixture(t)
	l, e := openLedger(p)
	if e != nil {
		t.Fatal(e)
	}
	if e = l.record(p, "creation_outcome_unknown", "", true); e != nil {
		t.Fatal(e)
	}
	l.close()
	exe, e := os.Executable()
	if e != nil {
		t.Fatal(e)
	}
	c := exec.Command(exe, "-test.run=^TestWorkflowProcessLedgerChild$")
	c.Env = []string{"FT_SYNTHETIC_LEDGER_CHILD=1"}
	c.ExtraFiles = []*os.File{d, w}
	if e = c.Run(); e != nil {
		t.Fatal("process restart did not preserve intent")
	}
}
